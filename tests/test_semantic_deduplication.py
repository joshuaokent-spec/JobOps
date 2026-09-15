from collections.abc import Sequence

import pytest

from jobops.models.job import JobPosting, WorkMode
from jobops.normalization.semantic_deduplication import (
    DuplicateMatchType,
    EmbeddingNearDuplicateComparator,
    HybridDuplicateDetector,
    JobEmbeddingTextBuilder,
    cosine_similarity,
)


class FakeProvider:
    model_name = "fake-v1"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            if "Data Engineer" in text or "Data Platform Engineer" in text:
                vectors.append([1.0, 0.05])
            elif "Product Manager" in text:
                vectors.append([0.0, 1.0])
            else:
                vectors.append([0.5, 0.5])
        return vectors


def job(
    job_id: str,
    title: str,
    source: str,
    company: str = "Acme",
) -> JobPosting:
    return JobPosting(
        job_id=job_id,
        company=company,
        title=title,
        source=source,
        work_mode=WorkMode.REMOTE,
        description=f"Responsibilities for {title}",
    )


def test_embedding_text_is_stable_and_source_neutral() -> None:
    builder = JobEmbeddingTextBuilder(max_description_chars=20)
    posting = JobPosting(
        job_id="1",
        company="Acme",
        title="Data Engineer",
        description="Build robust production pipelines for analytics teams.",
        source="lever",
        required_skills=["SQL", "Python"],
    )
    text = builder.build(posting)
    assert "source:" not in text
    assert "required_skills: Python, SQL" in text
    assert "description: Build robust product" in text


def test_cosine_similarity_handles_normal_and_zero_vectors() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
    with pytest.raises(ValueError):
        cosine_similarity([1.0], [1.0, 2.0])


def test_embedding_comparator_implements_pair_similarity() -> None:
    comparator = EmbeddingNearDuplicateComparator(FakeProvider())
    similarity = comparator.similarity(
        job("1", "Data Engineer", "lever"),
        job("2", "Data Platform Engineer", "greenhouse"),
    )
    assert similarity > 0.99


def test_hybrid_detector_blocks_by_company_and_cross_source() -> None:
    detector = HybridDuplicateDetector(FakeProvider(), threshold=0.9)
    result = detector.scan(
        [
            job("1", "Data Engineer", "lever"),
            job("2", "Data Platform Engineer", "greenhouse"),
            job("3", "Product Manager", "greenhouse"),
            job("4", "Data Engineer", "greenhouse", company="OtherCo"),
            job("5", "Data Platform Engineer", "lever"),
        ]
    )
    assert result.pairs_considered == 4
    assert result.semantic_pairs_scored == 4
    assert len(result.candidates) == 2
    assert all(
        candidate.match_type is DuplicateMatchType.SEMANTIC
        for candidate in result.candidates
    )


def test_deterministic_match_remains_authoritative() -> None:
    left = job("1", "Data Engineer", "lever")
    right = job("2", "Different Title", "greenhouse")
    left.dedupe_key = right.dedupe_key = "same-fingerprint"
    result = HybridDuplicateDetector(FakeProvider(), threshold=0.99).scan(
        [left, right]
    )
    assert result.deterministic_matches == 1
    assert result.semantic_pairs_scored == 0
    assert result.candidates[0].match_type is DuplicateMatchType.DETERMINISTIC
    assert result.candidates[0].similarity == 1.0
