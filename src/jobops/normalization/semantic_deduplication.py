import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from itertools import combinations

from pydantic import BaseModel, Field

from jobops.embeddings import EmbeddingProvider
from jobops.models.job import JobPosting
from jobops.normalization.deduplication import DeterministicDuplicateDetector
from jobops.normalization.job_normalizer import clean_display_text, text_key


class DuplicateMatchType(StrEnum):
    DETERMINISTIC = "deterministic"
    SEMANTIC = "semantic"


class DuplicateCandidate(BaseModel):
    left_job_id: str
    right_job_id: str
    match_type: DuplicateMatchType
    similarity: float = Field(ge=-1.0, le=1.0)
    threshold: float | None = Field(default=None, ge=-1.0, le=1.0)
    model_name: str | None = None
    reasons: list[str] = Field(default_factory=list)


class DuplicateScanResult(BaseModel):
    jobs_scanned: int
    company_blocks: int
    pairs_considered: int
    semantic_pairs_scored: int
    deterministic_matches: int
    semantic_matches: int
    candidates: list[DuplicateCandidate] = Field(default_factory=list)


@dataclass(slots=True)
class JobEmbeddingTextBuilder:
    max_description_chars: int = 4000

    def build(self, job: JobPosting) -> str:
        fields = [
            ("company", clean_display_text(job.company)),
            ("title", clean_display_text(job.title)),
            ("location", clean_display_text(job.location)),
            ("work_mode", job.work_mode.value),
            ("employment_type", clean_display_text(job.employment_type)),
        ]
        lines = [f"{name}: {value}" for name, value in fields if value]
        if job.required_skills:
            skills = sorted(job.required_skills, key=str.casefold)
            lines.append(f"required_skills: {', '.join(skills)}")
        if job.preferred_skills:
            skills = sorted(job.preferred_skills, key=str.casefold)
            lines.append(f"preferred_skills: {', '.join(skills)}")
        description = clean_display_text(job.description)
        if description:
            lines.append(f"description: {description[: self.max_description_chars]}")
        return "\n".join(lines)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions must match")
    if not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (left_norm * right_norm)))


@dataclass(slots=True)
class EmbeddingNearDuplicateComparator:
    provider: EmbeddingProvider
    text_builder: JobEmbeddingTextBuilder = field(default_factory=JobEmbeddingTextBuilder)

    def similarity(self, left: JobPosting, right: JobPosting) -> float:
        vectors = self.provider.embed(
            [self.text_builder.build(left), self.text_builder.build(right)]
        )
        if len(vectors) != 2:
            raise ValueError("embedding provider returned an unexpected vector count")
        return cosine_similarity(vectors[0], vectors[1])


@dataclass(slots=True)
class HybridDuplicateDetector:
    provider: EmbeddingProvider
    threshold: float = 0.84
    cross_source_only: bool = True
    text_builder: JobEmbeddingTextBuilder = field(default_factory=JobEmbeddingTextBuilder)
    deterministic: DeterministicDuplicateDetector = field(
        default_factory=DeterministicDuplicateDetector
    )

    def __post_init__(self) -> None:
        if not -1.0 <= self.threshold <= 1.0:
            raise ValueError("threshold must be between -1 and 1")

    def scan(self, jobs: Iterable[JobPosting]) -> DuplicateScanResult:
        job_list = sorted(jobs, key=lambda job: job.job_id)
        blocks: dict[str, list[JobPosting]] = defaultdict(list)
        for job in job_list:
            blocks[text_key(job.company)].append(job)

        pairs: list[tuple[JobPosting, JobPosting]] = []
        exact_candidates: list[DuplicateCandidate] = []
        semantic_pairs: list[tuple[JobPosting, JobPosting]] = []

        for block in blocks.values():
            for left, right in combinations(block, 2):
                if self.cross_source_only and self._same_known_source(left, right):
                    continue
                pairs.append((left, right))
                if self.deterministic.is_duplicate(left, right):
                    exact_candidates.append(self._deterministic_candidate(left, right))
                else:
                    semantic_pairs.append((left, right))

        semantic_candidates = self._semantic_candidates(semantic_pairs)
        candidates = exact_candidates + semantic_candidates
        candidates.sort(
            key=lambda item: (
                item.match_type is DuplicateMatchType.SEMANTIC,
                -item.similarity,
                item.left_job_id,
                item.right_job_id,
            )
        )
        return DuplicateScanResult(
            jobs_scanned=len(job_list),
            company_blocks=len(blocks),
            pairs_considered=len(pairs),
            semantic_pairs_scored=len(semantic_pairs),
            deterministic_matches=len(exact_candidates),
            semantic_matches=len(semantic_candidates),
            candidates=candidates,
        )

    @staticmethod
    def _same_known_source(left: JobPosting, right: JobPosting) -> bool:
        return bool(left.source and right.source and left.source == right.source)

    def _semantic_candidates(
        self,
        pairs: list[tuple[JobPosting, JobPosting]],
    ) -> list[DuplicateCandidate]:
        if not pairs:
            return []
        jobs_by_id: dict[str, JobPosting] = {}
        for left, right in pairs:
            jobs_by_id[left.job_id] = left
            jobs_by_id[right.job_id] = right
        ordered_jobs = [jobs_by_id[job_id] for job_id in sorted(jobs_by_id)]
        vectors = self.provider.embed(
            [self.text_builder.build(job) for job in ordered_jobs]
        )
        if len(vectors) != len(ordered_jobs):
            raise ValueError("embedding provider returned an unexpected vector count")
        embeddings = {
            job.job_id: vector
            for job, vector in zip(ordered_jobs, vectors, strict=True)
        }

        candidates: list[DuplicateCandidate] = []
        for left, right in pairs:
            similarity = cosine_similarity(
                embeddings[left.job_id],
                embeddings[right.job_id],
            )
            if similarity < self.threshold:
                continue
            candidates.append(
                DuplicateCandidate(
                    left_job_id=left.job_id,
                    right_job_id=right.job_id,
                    match_type=DuplicateMatchType.SEMANTIC,
                    similarity=round(similarity, 6),
                    threshold=self.threshold,
                    model_name=self.provider.model_name,
                    reasons=[
                        "same normalized company block",
                        (
                            f"embedding cosine similarity {similarity:.3f} "
                            f">= threshold {self.threshold:.3f}"
                        ),
                    ],
                )
            )
        return candidates

    @staticmethod
    def _deterministic_candidate(
        left: JobPosting,
        right: JobPosting,
    ) -> DuplicateCandidate:
        reason = (
            "matching canonical job identity"
            if left.job_id == right.job_id
            else "matching deterministic dedupe fingerprint"
        )
        return DuplicateCandidate(
            left_job_id=left.job_id,
            right_job_id=right.job_id,
            match_type=DuplicateMatchType.DETERMINISTIC,
            similarity=1.0,
            reasons=[reason],
        )
