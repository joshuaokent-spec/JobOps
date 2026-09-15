from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from jobops.knowledge import ResumeEvidenceStore, parse_resume_evidence_yaml
from jobops.models.resume_evidence import (
    EvidenceKind,
    EvidenceQuery,
    EvidenceSource,
    EvidenceSourceKind,
    ResumeEvidenceBase,
    ResumeEvidenceItem,
    RoleFamily,
)


def _load_example() -> ResumeEvidenceBase:
    content = Path("data/examples/resume-evidence.example.yaml").read_text(encoding="utf-8")
    return parse_resume_evidence_yaml(content)


def test_verified_evidence_requires_provenance() -> None:
    with pytest.raises(ValidationError, match="source reference"):
        ResumeEvidenceItem(
            evidence_id="claim-1",
            kind=EvidenceKind.SKILL,
            claim="Uses Python for analytics.",
            verified=True,
        )


def test_evidence_base_rejects_unknown_source_reference() -> None:
    with pytest.raises(ValidationError, match="unknown sources"):
        ResumeEvidenceBase(
            candidate_id="sample",
            sources=[],
            items=[
                ResumeEvidenceItem(
                    evidence_id="claim-1",
                    kind=EvidenceKind.PROJECT,
                    claim="Built a pipeline.",
                    source_refs=["missing-source"],
                )
            ],
        )


def test_evidence_base_rejects_duplicate_ids() -> None:
    source = EvidenceSource(
        source_id="source-1",
        kind=EvidenceSourceKind.DOCUMENT,
        label="Evidence document",
    )
    item = ResumeEvidenceItem(
        evidence_id="claim-1",
        kind=EvidenceKind.SKILL,
        claim="Uses SQL.",
        source_refs=["source-1"],
        verified=True,
    )
    with pytest.raises(ValidationError, match="duplicate evidence_id"):
        ResumeEvidenceBase(
            candidate_id="sample",
            sources=[source],
            items=[item, item.model_copy()],
        )


def test_retrieval_text_contains_canonical_features() -> None:
    evidence = _load_example().items[0]
    text = evidence.retrieval_text()
    assert "kind: project" in text
    assert "Python" in text
    assert "data_engineering" in text
    assert evidence.claim in text


def test_store_filters_by_role_skill_and_verification() -> None:
    store = ResumeEvidenceStore(_load_example())
    matches = store.query(
        EvidenceQuery(
            role_families=[RoleFamily.DATA_ENGINEERING],
            skills=["python"],
        )
    )
    ids = {item.evidence_id for item in matches}
    assert "project-data-lake-etl" in ids
    assert "skill-python" in ids
    assert "draft-cloud-claim" not in ids


def test_recency_filter_excludes_old_dated_evidence_but_keeps_evergreen_items() -> None:
    source = EvidenceSource(
        source_id="source-1",
        kind=EvidenceSourceKind.DOCUMENT,
        label="Evidence document",
    )
    old_project = ResumeEvidenceItem(
        evidence_id="old-project",
        kind=EvidenceKind.PROJECT,
        claim="Built an older pipeline.",
        end_date=date(2020, 1, 1),
        source_refs=["source-1"],
        verified=True,
    )
    evergreen_skill = ResumeEvidenceItem(
        evidence_id="skill-python",
        kind=EvidenceKind.SKILL,
        claim="Uses Python.",
        skills=["Python"],
        source_refs=["source-1"],
        verified=True,
    )
    store = ResumeEvidenceStore(
        ResumeEvidenceBase(
            candidate_id="sample",
            sources=[source],
            items=[old_project, evergreen_skill],
        )
    )

    matches = store.query(EvidenceQuery(since=date(2024, 1, 1)))
    assert [item.evidence_id for item in matches] == ["skill-python"]


def test_family_pool_respects_pins_exclusions_and_verification() -> None:
    store = ResumeEvidenceStore(_load_example())
    items = store.for_family("data-engineer")
    ids = [item.evidence_id for item in items]
    assert ids[0] == "project-data-lake-etl"
    assert "draft-cloud-claim" not in ids


def test_verified_payload_rejects_unverified_evidence() -> None:
    store = ResumeEvidenceStore(_load_example())
    with pytest.raises(ValueError, match="unverified evidence"):
        store.verified_payload(["draft-cloud-claim"])


def test_verified_payload_rejects_family_exclusion() -> None:
    store = ResumeEvidenceStore(_load_example())
    with pytest.raises(ValueError, match="excludes evidence"):
        store.verified_payload(
            ["draft-cloud-claim"],
            family_id="data-engineer",
        )


def test_verified_payload_preserves_evidence_ids() -> None:
    store = ResumeEvidenceStore(_load_example())
    payload = store.verified_payload(
        ["project-data-lake-etl", "skill-python"],
        family_id="data-engineer",
    )
    assert payload.candidate_id == "sample-candidate"
    assert payload.evidence_ids == ["project-data-lake-etl", "skill-python"]
