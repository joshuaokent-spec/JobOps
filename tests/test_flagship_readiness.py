from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from jobops.approvals import ApprovalQueue
from jobops.db.approval_repository import SqlAlchemyApprovalRepository
from jobops.db.base import Base
from jobops.db.flagship_repository import SqlAlchemyFlagshipReadinessRepository
from jobops.db.repositories import SqlAlchemyJobRepository
from jobops.db.search_profile_repository import SqlAlchemySearchProfileRepository
from jobops.flagship.readiness import FlagshipReadinessService
from jobops.models.application_question import HandlingRoute, QuestionCategory, ReviewBand
from jobops.models.approval import ApprovalCreate, ApprovalReason
from jobops.models.discovery import DiscoveryRunResult
from jobops.models.evidence_retrieval import (
    EvidenceRetrievalFeatures,
    EvidenceRetrievalHit,
    EvidenceRetrievalResult,
)
from jobops.models.flagship_run import (
    FlagshipPreparedJob,
    FlagshipReadiness,
    FlagshipRunResult,
)
from jobops.models.job import JobPosting, WorkMode
from jobops.models.resume_evidence import EvidenceKind, ResumeEvidenceItem
from jobops.models.resume_selection import ResumeFamilySelection
from jobops.models.scoring import ScoreBreakdown
from jobops.models.search_profile import SearchProfile


def _score(overall: float) -> ScoreBreakdown:
    return ScoreBreakdown(
        overall=overall,
        title_fit=1,
        required_skill_fit=1,
        preferred_skill_fit=1,
        experience_fit=1,
        compensation_fit=1,
        work_mode_fit=1,
    )


def _selection(*, low_confidence: bool = False) -> ResumeFamilySelection:
    return ResumeFamilySelection(
        chosen_family_id="data-engineer",
        chosen_score=82,
        minimum_confidence=0.35,
        low_confidence=low_confidence,
        candidates=[],
    )


def _evidence(job_id: str, *, with_hit: bool) -> EvidenceRetrievalResult:
    hits = []
    if with_hit:
        hits = [
            EvidenceRetrievalHit(
                evidence=ResumeEvidenceItem(
                    evidence_id=f"evidence-{job_id}",
                    kind=EvidenceKind.PROJECT,
                    claim="Built a verified data pipeline.",
                    skills=["Python", "SQL"],
                ),
                score=90,
                features=EvidenceRetrievalFeatures(
                    lexical_fit=1,
                    skill_fit=1,
                    family_fit=1,
                    specificity=1,
                ),
            )
        ]
    return EvidenceRetrievalResult(
        job_id=job_id,
        family_id="data-engineer",
        limit=6,
        candidates_considered=len(hits),
        hits=hits,
    )


def _prepared(
    job: JobPosting,
    *,
    rank: int,
    readiness: FlagshipReadiness,
) -> FlagshipPreparedJob:
    review = readiness is FlagshipReadiness.REVIEW_REQUIRED
    return FlagshipPreparedJob(
        rank=rank,
        job=job,
        score=_score(90 - rank),
        resume_selection=_selection(low_confidence=review),
        evidence=_evidence(job.job_id, with_hit=not review),
        readiness=readiness,
        readiness_reasons=(
            ["Resume-family selection requires review."] if review else []
        ),
    )


def _run_result(
    profile_id: str,
    *,
    completed_at: datetime,
    prepared_jobs: list[FlagshipPreparedJob],
) -> FlagshipRunResult:
    ready_count = sum(
        item.readiness is FlagshipReadiness.READY for item in prepared_jobs
    )
    discovery = DiscoveryRunResult(
        profile_id=profile_id,
        started_at=completed_at - timedelta(seconds=2),
        completed_at=completed_at - timedelta(seconds=1),
        providers_requested=1,
        providers_succeeded=1,
        providers_failed=0,
        providers_skipped=0,
        fetched=len(prepared_jobs),
        normalized=len(prepared_jobs),
        eligible=len(prepared_jobs),
        rejected=0,
        persisted=len(prepared_jobs),
        duplicates=0,
        persisted_job_ids=[item.job.job_id for item in prepared_jobs],
    )
    return FlagshipRunResult(
        profile_id=profile_id,
        started_at=completed_at - timedelta(seconds=3),
        completed_at=completed_at,
        discovery=discovery,
        total_examined=len(prepared_jobs),
        total_hard_eligible=len(prepared_jobs),
        total_hard_rejected=0,
        total_fit_eligible=len(prepared_jobs),
        total_fit_rejected=0,
        prepared_count=len(prepared_jobs),
        ready_count=ready_count,
        review_required_count=len(prepared_jobs) - ready_count,
        prepared_jobs=prepared_jobs,
    )


def test_readiness_snapshot_and_exception_inbox_track_latest_run_only() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    ready_job = JobPosting(
        job_id="job-ready",
        company="Ready Co",
        title="Data Engineer",
        work_mode=WorkMode.REMOTE,
    )
    review_job = JobPosting(
        job_id="job-review",
        company="Review Co",
        title="Data Engineer",
        work_mode=WorkMode.REMOTE,
    )
    profile = SearchProfile(
        profile_id="profile-1",
        candidate_id="me",
        name="Remote Data",
        role_queries=["Data Engineer"],
        allowed_work_modes=[WorkMode.REMOTE],
    )

    with Session(engine) as session:
        jobs = SqlAlchemyJobRepository(session)
        jobs.save(ready_job)
        jobs.save(review_job)
        SqlAlchemySearchProfileRepository(session).save(profile)

        readiness_repo = SqlAlchemyFlagshipReadinessRepository(session)
        approvals = SqlAlchemyApprovalRepository(session)
        service = FlagshipReadinessService(readiness_repo, approvals)

        first_completed = datetime(2026, 9, 21, 20, 0, tzinfo=UTC)
        first = readiness_repo.save(
            candidate_id="me",
            result=_run_result(
                profile.profile_id,
                completed_at=first_completed,
                prepared_jobs=[
                    _prepared(
                        ready_job,
                        rank=1,
                        readiness=FlagshipReadiness.READY,
                    ),
                    _prepared(
                        review_job,
                        rank=2,
                        readiness=FlagshipReadiness.REVIEW_REQUIRED,
                    ),
                ],
            ),
        )
        ApprovalQueue(approvals).enqueue(
            ApprovalCreate(
                approval_id="approval-1",
                job_id=review_job.job_id,
                family_id="data-engineer",
                question="Tell us about a project.",
                category=QuestionCategory.NARRATIVE,
                route=HandlingRoute.DRAFT_WITH_REVIEW,
                review_band=ReviewBand.YELLOW,
                reason=ApprovalReason.NARRATIVE_DRAFT,
                proposed_answer="A grounded draft.",
                evidence_ids=[f"evidence-{review_job.job_id}"],
            )
        )
        session.commit()

        latest = service.latest(profile.profile_id)
        assert latest is not None
        assert latest.run_id == first.run_id
        assert latest.ready_count == 1
        assert latest.review_required_count == 1
        assert [item.job_id for item in latest.prepared_jobs] == [
            "job-ready",
            "job-review",
        ]

        inbox = service.exceptions(profile.profile_id)
        assert inbox is not None
        assert [item.job_id for item in inbox.review_required_jobs] == ["job-review"]
        assert [item.approval_id for item in inbox.pending_approvals] == ["approval-1"]
        assert inbox.total_exceptions == 2

        second = readiness_repo.save(
            candidate_id="me",
            result=_run_result(
                profile.profile_id,
                completed_at=first_completed + timedelta(hours=1),
                prepared_jobs=[
                    _prepared(
                        ready_job,
                        rank=1,
                        readiness=FlagshipReadiness.READY,
                    )
                ],
            ),
        )
        session.commit()

        assert readiness_repo.count_runs(profile.profile_id) == 2
        newest = service.latest(profile.profile_id)
        assert newest is not None
        assert newest.run_id == second.run_id
        assert newest.ready_count == 1
        assert newest.review_required_count == 0

        newest_inbox = service.exceptions(profile.profile_id)
        assert newest_inbox is not None
        assert newest_inbox.review_required_jobs == []
        assert newest_inbox.pending_approvals == []
        assert newest_inbox.total_exceptions == 0


def test_readiness_snapshot_respects_foreign_keys_when_parent_and_children_are_new() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)

    job = JobPosting(
        job_id="job-fk-order",
        company="FK Co",
        title="Data Engineer",
        work_mode=WorkMode.REMOTE,
    )
    profile = SearchProfile(
        profile_id="profile-fk-order",
        candidate_id="me",
        name="Remote Data",
        role_queries=["Data Engineer"],
        allowed_work_modes=[WorkMode.REMOTE],
    )

    with Session(engine) as session:
        SqlAlchemyJobRepository(session).save(job)
        SqlAlchemySearchProfileRepository(session).save(profile)

        saved = SqlAlchemyFlagshipReadinessRepository(session).save(
            candidate_id="me",
            result=_run_result(
                profile.profile_id,
                completed_at=datetime(2026, 9, 21, 22, 45, tzinfo=UTC),
                prepared_jobs=[
                    _prepared(
                        job,
                        rank=1,
                        readiness=FlagshipReadiness.READY,
                    )
                ],
            ),
        )
        session.commit()

        assert saved.profile_id == profile.profile_id
        assert [item.job_id for item in saved.prepared_jobs] == [job.job_id]
