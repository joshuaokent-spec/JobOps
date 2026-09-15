import re
from typing import Final

from jobops.embeddings import EmbeddingProvider
from jobops.knowledge.resume_evidence_store import ResumeEvidenceStore
from jobops.models.evidence_retrieval import (
    EvidenceRetrievalFeatures,
    EvidenceRetrievalHit,
    EvidenceRetrievalResult,
)
from jobops.models.job import JobPosting
from jobops.models.resume_evidence import ResumeEvidenceItem
from jobops.normalization.semantic_deduplication import JobEmbeddingTextBuilder, cosine_similarity

_TOKEN_RE: Final = re.compile(r"[a-z0-9+#.]+")


class EvidenceRetriever:
    """Rank verified resume evidence into a bounded, provenance-preserving context."""

    deterministic_weights: Final[dict[str, float]] = {
        "lexical_fit": 0.30,
        "skill_fit": 0.40,
        "family_fit": 0.20,
        "specificity": 0.10,
    }

    def __init__(
        self,
        store: ResumeEvidenceStore,
        *,
        provider: EmbeddingProvider | None = None,
        semantic_weight: float = 0.35,
        max_per_kind: int = 2,
    ):
        if not 0 <= semantic_weight <= 1:
            raise ValueError("semantic_weight must be between 0 and 1")
        if max_per_kind < 1:
            raise ValueError("max_per_kind must be positive")
        self.store = store
        self.provider = provider
        self.semantic_weight = semantic_weight
        self.max_per_kind = max_per_kind
        self._job_text_builder = JobEmbeddingTextBuilder()

    def retrieve(
        self,
        job: JobPosting,
        family_id: str,
        *,
        limit: int = 6,
    ) -> EvidenceRetrievalResult:
        if limit < 1:
            raise ValueError("limit must be positive")
        family = self.store.family(family_id)
        if family is None:
            raise ValueError(f"unknown resume family: {family_id}")

        evidence = self.store.for_family(family_id, verified_only=True)
        semantic = self._semantic_scores(job, evidence)
        hits = [
            self._score(
                job,
                family_id,
                item,
                semantic.get(item.evidence_id),
            )
            for item in evidence
        ]
        hits.sort(key=lambda hit: (-hit.score, hit.evidence.evidence_id))
        selected = self._diverse_top_k(hits, limit)

        return EvidenceRetrievalResult(
            job_id=job.job_id,
            family_id=family_id,
            limit=limit,
            candidates_considered=len(hits),
            semantic_model=self.provider.model_name if self.provider is not None else None,
            hits=selected,
        )

    def _score(
        self,
        job: JobPosting,
        family_id: str,
        item: ResumeEvidenceItem,
        semantic_similarity: float | None,
    ) -> EvidenceRetrievalHit:
        features = EvidenceRetrievalFeatures(
            lexical_fit=self._lexical_fit(job, item),
            skill_fit=self._skill_fit(job, item),
            family_fit=self._family_fit(family_id, item),
            specificity=self._specificity(item),
            semantic_similarity=semantic_similarity,
        )
        values = features.model_dump()
        deterministic = sum(
            float(values[name]) * weight
            for name, weight in self.deterministic_weights.items()
        )
        if semantic_similarity is None:
            final = deterministic
        else:
            semantic_fit = max(0.0, min(1.0, semantic_similarity))
            final = (
                deterministic * (1.0 - self.semantic_weight)
                + semantic_fit * self.semantic_weight
            )

        reasons = [
            f"Lexical job/evidence fit: {features.lexical_fit:.0%}.",
            f"Explicit job-skill coverage: {features.skill_fit:.0%}.",
            f"Resume-family alignment: {features.family_fit:.0%}.",
            f"Evidence specificity: {features.specificity:.0%}.",
        ]
        if semantic_similarity is not None:
            reasons.append(f"Embedding cosine similarity: {semantic_similarity:.3f}.")

        return EvidenceRetrievalHit(
            evidence=item,
            score=round(final * 100, 1),
            features=features,
            reasons=reasons,
        )

    def _semantic_scores(
        self,
        job: JobPosting,
        evidence: list[ResumeEvidenceItem],
    ) -> dict[str, float]:
        if self.provider is None or not evidence:
            return {}

        texts = [self._job_text_builder.build(job), *[item.retrieval_text() for item in evidence]]
        vectors = self.provider.embed(texts)
        if len(vectors) != len(texts):
            raise ValueError("embedding provider returned an unexpected vector count")

        query_vector = vectors[0]
        return {
            item.evidence_id: cosine_similarity(query_vector, vector)
            for item, vector in zip(evidence, vectors[1:], strict=True)
        }

    def _lexical_fit(self, job: JobPosting, item: ResumeEvidenceItem) -> float:
        desired = self._tokens(
            " ".join([job.title, *job.required_skills, *job.preferred_skills])
        )
        if not desired:
            desired = self._tokens(job.description)
        if not desired:
            return 0.0
        evidence_tokens = self._tokens(item.retrieval_text())
        return len(desired & evidence_tokens) / len(desired)

    @staticmethod
    def _skill_fit(job: JobPosting, item: ResumeEvidenceItem) -> float:
        desired = {
            skill.strip().casefold()
            for skill in [*job.required_skills, *job.preferred_skills]
            if skill.strip()
        }
        if not desired:
            return 0.5
        demonstrated = {skill.strip().casefold() for skill in item.skills if skill.strip()}
        return len(desired & demonstrated) / len(desired)

    def _family_fit(self, family_id: str, item: ResumeEvidenceItem) -> float:
        family = self.store.family(family_id)
        assert family is not None
        family_roles = set(family.role_families)
        item_roles = set(item.role_families)
        if not family_roles or not item_roles:
            return 0.5
        return 1.0 if family_roles & item_roles else 0.0

    @staticmethod
    def _specificity(item: ResumeEvidenceItem) -> float:
        signals = len(item.skills) + len(item.metrics)
        signals += int(bool(item.organization)) + int(bool(item.title))
        return min(signals / 5.0, 1.0)

    def _diverse_top_k(
        self,
        ranked: list[EvidenceRetrievalHit],
        limit: int,
    ) -> list[EvidenceRetrievalHit]:
        selected: list[EvidenceRetrievalHit] = []
        deferred: list[EvidenceRetrievalHit] = []
        kind_counts: dict[str, int] = {}

        for hit in ranked:
            kind = hit.evidence.kind.value
            if kind_counts.get(kind, 0) >= self.max_per_kind:
                deferred.append(hit)
                continue
            selected.append(hit)
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
            if len(selected) == limit:
                return selected

        for hit in deferred:
            selected.append(hit)
            if len(selected) == limit:
                break
        return selected

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return set(_TOKEN_RE.findall(value.casefold()))
