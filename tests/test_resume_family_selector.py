import json
from pathlib import Path

from jobops.knowledge import ResumeEvidenceStore, parse_resume_evidence_yaml
from jobops.matching import ExplainableResumeFamilySelector
from jobops.models.job import JobPosting
from jobops.models.resume_evidence import ResumeEvidenceBase, ResumeFamilyDefinition, RoleFamily


def _store() -> ResumeEvidenceStore:
    content = Path("data/examples/resume-evidence.example.yaml").read_text(encoding="utf-8")
    return ResumeEvidenceStore(parse_resume_evidence_yaml(content))


def _jobs() -> dict[str, JobPosting]:
    payload = json.loads(Path("tests/fixtures/resume_selector_jobs.json").read_text())
    jobs = [JobPosting.model_validate(item) for item in payload]
    return {job.job_id: job for job in jobs}


def test_selector_chooses_data_engineering_family() -> None:
    result = ExplainableResumeFamilySelector(_store()).select(
        _jobs()["selector-data-engineer"]
    )
    assert result.chosen_family_id == "data-engineer"
    assert result.candidates[0].features.title_role_fit > 0
    assert "project-data-lake-etl" in result.candidates[0].evidence_ids


def test_selector_chooses_data_science_family() -> None:
    result = ExplainableResumeFamilySelector(_store()).select(
        _jobs()["selector-data-scientist"]
    )
    assert result.chosen_family_id == "data-scientist"


def test_selector_chooses_ai_engineering_family() -> None:
    result = ExplainableResumeFamilySelector(_store()).select(
        _jobs()["selector-ml-engineer"]
    )
    assert result.chosen_family_id == "ai-engineer"


def test_selector_chooses_analytics_family() -> None:
    result = ExplainableResumeFamilySelector(_store()).select(_jobs()["selector-analytics"])
    assert result.chosen_family_id == "analytics"


def test_selector_exposes_only_verified_evidence_candidates() -> None:
    store = _store()
    result = ExplainableResumeFamilySelector(store).select(_jobs()["selector-data-engineer"])
    chosen = next(item for item in result.candidates if item.family_id == result.chosen_family_id)
    assert chosen.evidence_ids
    assert all(store.get(item_id).verified for item_id in chosen.evidence_ids)
    assert "draft-cloud-claim" not in chosen.evidence_ids


def test_selector_uses_stable_family_id_tie_breaking() -> None:
    store = ResumeEvidenceStore(
        ResumeEvidenceBase(
            candidate_id="sample",
            families=[
                ResumeFamilyDefinition(
                    family_id="beta",
                    name="Beta",
                    role_families=[RoleFamily.GENERAL],
                ),
                ResumeFamilyDefinition(
                    family_id="alpha",
                    name="Alpha",
                    role_families=[RoleFamily.GENERAL],
                ),
            ],
        )
    )
    result = ExplainableResumeFamilySelector(store).select(
        JobPosting(job_id="tie", company="Example", title="Technical Specialist")
    )
    assert result.chosen_family_id == "alpha"


def test_low_confidence_selection_can_use_configured_fallback() -> None:
    result = ExplainableResumeFamilySelector(
        _store(),
        minimum_confidence=0.95,
        fallback_family_id="analytics",
    ).select(_jobs()["selector-ambiguous"])
    assert result.low_confidence is True
    assert result.chosen_family_id == "analytics"
    assert result.used_fallback is True


def test_score_breakdown_is_reproducible() -> None:
    selector = ExplainableResumeFamilySelector(_store())
    job = _jobs()["selector-data-engineer"]
    first = selector.select(job)
    second = selector.select(job)
    assert first == second
