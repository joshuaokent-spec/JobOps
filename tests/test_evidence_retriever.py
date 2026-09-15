from pathlib import Path

from jobops.knowledge import EvidenceRetriever, ResumeEvidenceStore, parse_resume_evidence_yaml
from jobops.models.job import JobPosting
from jobops.models.resume_evidence import (
    EvidenceKind,
    EvidenceSource,
    EvidenceSourceKind,
    ResumeEvidenceBase,
    ResumeEvidenceItem,
    ResumeFamilyDefinition,
    RoleFamily,
)


class KeywordEmbeddingProvider:
    model_name = "keyword-test"

    def embed(self, texts):
        return [
            [1.0, 0.0] if "semantic-anchor" in text.casefold() else [0.0, 1.0]
            for text in texts
        ]


def _store() -> ResumeEvidenceStore:
    content = Path("data/examples/resume-evidence.example.yaml").read_text(encoding="utf-8")
    return ResumeEvidenceStore(parse_resume_evidence_yaml(content))


def test_retrieval_ranks_data_engineering_project_first() -> None:
    result = EvidenceRetriever(_store()).retrieve(
        JobPosting(
            job_id="job-de",
            company="Example",
            title="Senior Data Engineer",
            required_skills=["Python", "SQL", "ETL", "Data Pipelines"],
        ),
        "data-engineer",
    )
    assert result.hits[0].evidence.evidence_id == "project-data-lake-etl"
    assert result.hits[0].score > result.hits[-1].score


def test_retrieval_preserves_verified_evidence_and_provenance() -> None:
    store = _store()
    result = EvidenceRetriever(store).retrieve(
        JobPosting(job_id="job-ai", company="Example", title="AI Engineer"),
        "ai-engineer",
    )
    assert result.hits
    assert all(hit.evidence.verified for hit in result.hits)
    assert all(hit.evidence.source_refs for hit in result.hits)
    assert all(store.get(hit.evidence.evidence_id) is not None for hit in result.hits)
    assert all(hit.evidence.evidence_id != "draft-cloud-claim" for hit in result.hits)


def test_semantic_provider_can_blend_into_ranking() -> None:
    source = EvidenceSource(
        source_id="source-1",
        kind=EvidenceSourceKind.DOCUMENT,
        label="Evidence",
    )
    target = ResumeEvidenceItem(
        evidence_id="semantic-target",
        kind=EvidenceKind.PROJECT,
        claim="Demonstrated semantic-anchor work.",
        role_families=[RoleFamily.AI_ML],
        source_refs=["source-1"],
        verified=True,
    )
    other = ResumeEvidenceItem(
        evidence_id="other",
        kind=EvidenceKind.PROJECT,
        claim="Worked on unrelated reporting.",
        role_families=[RoleFamily.AI_ML],
        source_refs=["source-1"],
        verified=True,
    )
    store = ResumeEvidenceStore(
        ResumeEvidenceBase(
            candidate_id="sample",
            sources=[source],
            items=[other, target],
            families=[
                ResumeFamilyDefinition(
                    family_id="ai",
                    name="AI",
                    role_families=[RoleFamily.AI_ML],
                )
            ],
        )
    )
    result = EvidenceRetriever(
        store,
        provider=KeywordEmbeddingProvider(),
        semantic_weight=1.0,
    ).retrieve(
        JobPosting(
            job_id="semantic-job",
            company="Example",
            title="AI Engineer",
            description="semantic-anchor",
        ),
        "ai",
    )
    assert result.semantic_model == "keyword-test"
    assert result.hits[0].evidence.evidence_id == "semantic-target"
    assert result.hits[0].features.semantic_similarity == 1.0


def test_kind_diversity_prevents_one_kind_from_filling_first_pass() -> None:
    source = EvidenceSource(
        source_id="source-1",
        kind=EvidenceSourceKind.DOCUMENT,
        label="Evidence",
    )
    items = [
        ResumeEvidenceItem(
            evidence_id="skill-python",
            kind=EvidenceKind.SKILL,
            claim="Uses Python.",
            skills=["Python"],
            role_families=[RoleFamily.DATA_ENGINEERING],
            source_refs=["source-1"],
            verified=True,
        ),
        ResumeEvidenceItem(
            evidence_id="skill-sql",
            kind=EvidenceKind.SKILL,
            claim="Uses SQL.",
            skills=["SQL"],
            role_families=[RoleFamily.DATA_ENGINEERING],
            source_refs=["source-1"],
            verified=True,
        ),
        ResumeEvidenceItem(
            evidence_id="project-pipeline",
            kind=EvidenceKind.PROJECT,
            claim="Built a Python SQL pipeline.",
            skills=["Python", "SQL"],
            role_families=[RoleFamily.DATA_ENGINEERING],
            source_refs=["source-1"],
            verified=True,
        ),
    ]
    store = ResumeEvidenceStore(
        ResumeEvidenceBase(
            candidate_id="sample",
            sources=[source],
            items=items,
            families=[
                ResumeFamilyDefinition(
                    family_id="de",
                    name="Data Engineering",
                    role_families=[RoleFamily.DATA_ENGINEERING],
                )
            ],
        )
    )
    result = EvidenceRetriever(store, max_per_kind=1).retrieve(
        JobPosting(
            job_id="job",
            company="Example",
            title="Data Engineer",
            required_skills=["Python", "SQL"],
        ),
        "de",
        limit=2,
    )
    assert {hit.evidence.kind for hit in result.hits} == {
        EvidenceKind.PROJECT,
        EvidenceKind.SKILL,
    }


def test_retrieval_is_reproducible_and_bounded() -> None:
    retriever = EvidenceRetriever(_store())
    job = JobPosting(
        job_id="job-ds",
        company="Example",
        title="Data Scientist",
        required_skills=["Python", "Machine Learning"],
    )
    first = retriever.retrieve(job, "data-scientist", limit=2)
    second = retriever.retrieve(job, "data-scientist", limit=2)
    assert first == second
    assert len(first.hits) <= 2
