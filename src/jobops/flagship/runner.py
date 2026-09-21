from collections import Counter
from datetime import UTC, datetime

import httpx

from jobops.db.repositories import JobRepository
from jobops.discovery.runner import DiscoveryService
from jobops.knowledge import EvidenceRetriever, ResumeEvidenceStore
from jobops.matching import (
    BaselineJobScorer,
    ExplainableResumeFamilySelector,
    HardConstraintMatcher,
)
from jobops.models.flagship_run import (
    FlagshipPreparedJob,
    FlagshipReadiness,
    FlagshipRunRequest,
    FlagshipRunResult,
)
from jobops.models.query import JobSearchFilters
from jobops.models.search_profile import SearchProfile


class FlagshipRunError(ValueError):
    """Raised when a Flagship run cannot satisfy its ownership/readiness contract."""


class FlagshipRunService:
    """Compose discovery, filtering, ranking, resume selection, and evidence retrieval."""

    def __init__(
        self,
        repository: JobRepository,
        discovery: DiscoveryService,
        *,
        matcher: HardConstraintMatcher | None = None,
        scorer: BaselineJobScorer | None = None,
    ) -> None:
        self.repository = repository
        self.discovery = discovery
        self.matcher = matcher or HardConstraintMatcher()
        self.scorer = scorer or BaselineJobScorer()

    async def run(
        self,
        profile: SearchProfile,
        request: FlagshipRunRequest,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> FlagshipRunResult:
        self._validate_ownership(profile, request)
        started_at = datetime.now(UTC)

        discovery_result = await self.discovery.run(
            profile,
            request.discovery,
            client=client,
        )

        jobs = list(
            self.repository.search(
                JobSearchFilters(active=True),
                limit=request.candidate_pool,
                offset=0,
            )
        )

        rejection_counts: Counter[str] = Counter()
        ranked = []
        hard_eligible = 0
        fit_rejected = 0

        for job in jobs:
            constraint = self.matcher.evaluate(profile, job)
            if not constraint.eligible:
                rejection_counts.update(set(constraint.violation_codes))
                continue

            hard_eligible += 1
            score = self.scorer.score(request.candidate, job)
            if (
                profile.minimum_fit_score is not None
                and score.overall < profile.minimum_fit_score
            ):
                rejection_counts["fit_score"] += 1
                fit_rejected += 1
                continue
            ranked.append((job, score))

        ranked.sort(key=lambda item: (-item[1].overall, item[0].job_id))

        store = ResumeEvidenceStore(request.resume_evidence)
        if not store.base.families:
            raise FlagshipRunError("resume evidence base has no resume families")

        try:
            selector = ExplainableResumeFamilySelector(
                store,
                minimum_confidence=request.resume_minimum_confidence,
                fallback_family_id=request.fallback_family_id,
            )
        except ValueError as exc:
            raise FlagshipRunError(str(exc)) from exc

        retriever = EvidenceRetriever(store)
        prepared_jobs: list[FlagshipPreparedJob] = []

        for rank, (job, score) in enumerate(ranked[: request.max_jobs], start=1):
            selection = selector.select(job)
            evidence = retriever.retrieve(
                job,
                selection.chosen_family_id,
                limit=request.evidence_limit,
            )
            readiness_reasons: list[str] = []
            if selection.low_confidence and request.fallback_family_id is None:
                readiness_reasons.append(
                    "Resume-family selection is below the configured confidence threshold."
                )
            if not evidence.hits:
                readiness_reasons.append(
                    "No verified evidence is available for the selected resume family."
                )

            readiness = (
                FlagshipReadiness.REVIEW_REQUIRED
                if readiness_reasons
                else FlagshipReadiness.READY
            )
            prepared_jobs.append(
                FlagshipPreparedJob(
                    rank=rank,
                    job=job,
                    score=score,
                    resume_selection=selection,
                    evidence=evidence,
                    readiness=readiness,
                    readiness_reasons=readiness_reasons,
                )
            )

        ready_count = sum(
            item.readiness is FlagshipReadiness.READY for item in prepared_jobs
        )
        completed_at = datetime.now(UTC)

        return FlagshipRunResult(
            profile_id=profile.profile_id,
            started_at=started_at,
            completed_at=completed_at,
            discovery=discovery_result,
            total_examined=len(jobs),
            total_hard_eligible=hard_eligible,
            total_hard_rejected=len(jobs) - hard_eligible,
            total_fit_eligible=len(ranked),
            total_fit_rejected=fit_rejected,
            prepared_count=len(prepared_jobs),
            ready_count=ready_count,
            review_required_count=len(prepared_jobs) - ready_count,
            rejection_summary=dict(sorted(rejection_counts.items())),
            prepared_jobs=prepared_jobs,
        )

    @staticmethod
    def _validate_ownership(
        profile: SearchProfile,
        request: FlagshipRunRequest,
    ) -> None:
        if not profile.active:
            raise FlagshipRunError("search profile is inactive")
        if request.candidate.candidate_id != profile.candidate_id:
            raise FlagshipRunError("candidate does not match search profile owner")
        if request.resume_evidence.candidate_id != profile.candidate_id:
            raise FlagshipRunError("resume evidence does not match search profile owner")
