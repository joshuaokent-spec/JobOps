import re
from typing import Final

from jobops.knowledge.resume_evidence_store import ResumeEvidenceStore
from jobops.models.job import JobPosting
from jobops.models.resume_evidence import ResumeFamilyDefinition, RoleFamily
from jobops.models.resume_selection import (
    ResumeFamilyFeatures,
    ResumeFamilyScore,
    ResumeFamilySelection,
)

_TOKEN_RE: Final = re.compile(r"[a-z0-9+#.]+")

_ROLE_ALIASES: Final[dict[RoleFamily, tuple[str, ...]]] = {
    RoleFamily.DATA_ENGINEERING: (
        "data engineer",
        "data engineering",
        "etl engineer",
        "data platform engineer",
        "analytics engineer",
    ),
    RoleFamily.DATA_SCIENCE: (
        "data scientist",
        "decision scientist",
        "research scientist",
        "quantitative scientist",
    ),
    RoleFamily.AI_ML: (
        "machine learning engineer",
        "ml engineer",
        "ai engineer",
        "artificial intelligence engineer",
        "mlops engineer",
        "applied scientist",
    ),
    RoleFamily.ANALYTICS: (
        "data analyst",
        "business intelligence analyst",
        "bi analyst",
        "analytics analyst",
        "reporting analyst",
    ),
    RoleFamily.SOFTWARE: (
        "software engineer",
        "backend engineer",
        "application developer",
        "software developer",
    ),
    RoleFamily.GENERAL: ("general",),
}


class ExplainableResumeFamilySelector:
    """Transparent baseline for choosing a resume family for a job posting."""

    weights: Final[dict[str, float]] = {
        "title_role_fit": 0.40,
        "priority_skill_fit": 0.25,
        "evidence_skill_coverage": 0.20,
        "evidence_depth": 0.15,
    }

    def __init__(
        self,
        store: ResumeEvidenceStore,
        *,
        minimum_confidence: float = 0.35,
        fallback_family_id: str | None = None,
        evidence_depth_target: int = 4,
    ):
        if not 0 <= minimum_confidence <= 1:
            raise ValueError("minimum_confidence must be between 0 and 1")
        if evidence_depth_target < 1:
            raise ValueError("evidence_depth_target must be positive")
        if fallback_family_id is not None and store.family(fallback_family_id) is None:
            raise ValueError(f"unknown fallback resume family: {fallback_family_id}")

        self.store = store
        self.minimum_confidence = minimum_confidence
        self.fallback_family_id = fallback_family_id
        self.evidence_depth_target = evidence_depth_target

    def select(self, job: JobPosting) -> ResumeFamilySelection:
        if not self.store.base.families:
            raise ValueError("resume evidence base has no resume families")

        candidates = [self.score_family(job, family) for family in self.store.base.families]
        candidates.sort(key=lambda item: (-item.score, item.family_id))
        best = candidates[0]
        threshold = self.minimum_confidence * 100
        low_confidence = best.score < threshold
        chosen = best
        used_fallback = False

        if low_confidence and self.fallback_family_id is not None:
            chosen = next(
                item for item in candidates if item.family_id == self.fallback_family_id
            )
            used_fallback = chosen.family_id != best.family_id

        return ResumeFamilySelection(
            chosen_family_id=chosen.family_id,
            chosen_score=chosen.score,
            minimum_confidence=self.minimum_confidence,
            low_confidence=low_confidence,
            used_fallback=used_fallback,
            candidates=candidates,
        )

    def score_family(
        self,
        job: JobPosting,
        family: ResumeFamilyDefinition,
    ) -> ResumeFamilyScore:
        evidence = self.store.for_family(family.family_id)
        features = ResumeFamilyFeatures(
            title_role_fit=self._title_role_fit(job, family),
            priority_skill_fit=self._priority_skill_fit(job, family),
            evidence_depth=min(len(evidence) / self.evidence_depth_target, 1.0),
            evidence_skill_coverage=self._evidence_skill_coverage(job, evidence),
        )
        values = features.model_dump()
        weighted = sum(values[name] * weight for name, weight in self.weights.items())
        score = round(weighted * 100, 1)

        return ResumeFamilyScore(
            family_id=family.family_id,
            family_name=family.name,
            score=score,
            features=features,
            evidence_ids=[item.evidence_id for item in evidence],
            reasons=[
                f"Title/role alignment: {features.title_role_fit:.0%}.",
                f"Family priority-skill match: {features.priority_skill_fit:.0%}.",
                f"Verified evidence depth: {features.evidence_depth:.0%}.",
                f"Job-skill coverage in evidence: {features.evidence_skill_coverage:.0%}.",
            ],
        )

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return set(_TOKEN_RE.findall(value.casefold()))

    def _title_role_fit(self, job: JobPosting, family: ResumeFamilyDefinition) -> float:
        if not family.role_families:
            return 0.25

        title_tokens = self._tokens(job.title)
        scores: list[float] = []
        for role in family.role_families:
            if role is RoleFamily.GENERAL:
                scores.append(0.25)
                continue
            for alias in _ROLE_ALIASES.get(role, ()):
                alias_tokens = self._tokens(alias)
                union = title_tokens | alias_tokens
                score = len(title_tokens & alias_tokens) / len(union) if union else 0.0
                scores.append(score)
        return max(scores, default=0.0)

    def _priority_skill_fit(
        self,
        job: JobPosting,
        family: ResumeFamilyDefinition,
    ) -> float:
        if not family.priority_skills:
            return 0.5

        explicit_skills = {
            skill.strip().casefold()
            for skill in [*job.required_skills, *job.preferred_skills]
            if skill.strip()
        }
        job_tokens = self._tokens(f"{job.title} {job.description}")
        matched = 0
        for skill in family.priority_skills:
            normalized = skill.strip().casefold()
            skill_tokens = self._tokens(skill)
            if normalized in explicit_skills or (skill_tokens and skill_tokens <= job_tokens):
                matched += 1
        return matched / len(family.priority_skills)

    @staticmethod
    def _evidence_skill_coverage(job: JobPosting, evidence: list) -> float:
        desired = {
            skill.strip().casefold()
            for skill in [*job.required_skills, *job.preferred_skills]
            if skill.strip()
        }
        if not desired:
            return 0.5

        demonstrated = {
            skill.strip().casefold()
            for item in evidence
            for skill in item.skills
            if skill.strip()
        }
        return len(desired & demonstrated) / len(desired)
