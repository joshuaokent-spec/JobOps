import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from jobops.api.dependencies import get_session
from jobops.api.main import app
from jobops.api.search_profiles import get_discovery_providers
from jobops.db.base import Base
from jobops.db.onboarding_repository import SqlAlchemyCandidateOnboardingRepository
from jobops.db.repositories import SqlAlchemyJobRepository
from jobops.db.search_profile_repository import SqlAlchemySearchProfileRepository
from jobops.models.job import JobPosting, WorkMode
from jobops.models.onboarding import CandidateOnboardingPayload
from jobops.models.search_profile import SearchProfile
from jobops.onboarding_cli import load_payload, load_search_profiles


def _client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        session: Session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_discovery_providers] = lambda: {}
    return TestClient(app), factory


def _payload_dict() -> dict[str, object]:
    return {
        "candidate": {
            "candidate_id": "me",
            "target_roles": ["Data Engineer", "AI Engineer"],
            "skills": ["Python", "SQL", "scikit-learn"],
            "years_experience": 3,
            "preferred_work_modes": ["remote"],
            "minimum_salary": 65000,
            "facts": [
                {
                    "key": "work_authorized_us",
                    "value": True,
                    "evidence": ["resume:general"],
                    "verified": True,
                    "risk": "high",
                }
            ],
        },
        "resume_evidence": {
            "candidate_id": "me",
            "sources": [
                {
                    "source_id": "resume-general",
                    "kind": "document",
                    "label": "General technical resume",
                },
                {
                    "source_id": "project-overview",
                    "kind": "document",
                    "label": "Data project experience overview",
                },
            ],
            "items": [
                {
                    "evidence_id": "loom-data",
                    "kind": "experience",
                    "claim": (
                        "Cleaned, validated, and standardized user datasets with "
                        "Python and pandas for analysis and reporting."
                    ),
                    "organization": "Michigan State University",
                    "title": "Data Analyst / Research Assistant",
                    "skills": ["Python", "pandas", "Tableau", "data cleaning"],
                    "role_families": ["data_engineering", "analytics"],
                    "source_refs": ["resume-general", "project-overview"],
                    "verified": True,
                },
                {
                    "evidence_id": "adaptive-ml",
                    "kind": "project",
                    "claim": (
                        "Built an adaptive ML learning system with scikit-learn, "
                        "learner modeling, SQLite persistence, testing, and analytics."
                    ),
                    "skills": ["Python", "scikit-learn", "SQLite", "machine learning"],
                    "role_families": ["ai_ml", "data_science"],
                    "source_refs": ["resume-general", "project-overview"],
                    "verified": True,
                },
            ],
            "families": [
                {
                    "family_id": "data-engineer",
                    "name": "Data Engineering / Analytics",
                    "role_families": ["data_engineering", "analytics"],
                    "priority_skills": ["Python", "SQL", "pandas"],
                    "pinned_evidence_ids": ["loom-data"],
                },
                {
                    "family_id": "ai-ml",
                    "name": "AI / Machine Learning",
                    "role_families": ["ai_ml", "data_science"],
                    "priority_skills": ["Python", "scikit-learn", "machine learning"],
                    "pinned_evidence_ids": ["adaptive-ml"],
                },
            ],
        },
        "resume_assets": [
            {
                "family_id": "data-engineer",
                "label": "Data resume",
                "file_path": "data/private/resumes/data-engineer.pdf",
            },
            {
                "family_id": "ai-ml",
                "label": "AI Engineer resume",
                "file_path": "data/private/resumes/ai-engineer.pdf",
            },
        ],
        "run_defaults": {
            "discovery": {"providers": []},
            "candidate_pool": 100,
            "max_jobs": 10,
            "fallback_family_id": "data-engineer",
        },
    }


def _profile() -> SearchProfile:
    return SearchProfile(
        profile_id="profile-1",
        candidate_id="me",
        name="Remote Data / AI >=65k",
        role_queries=["Data Engineer", "AI Engineer"],
        allowed_work_modes=[WorkMode.REMOTE],
        minimum_salary=65000,
    )


def test_onboarding_repository_persists_and_reports_readiness() -> None:
    _, factory = _client()
    payload = CandidateOnboardingPayload.model_validate(_payload_dict())

    with factory() as session:
        repo = SqlAlchemyCandidateOnboardingRepository(session)
        saved = repo.save(payload)
        session.commit()

        loaded = repo.get("me")
        status = repo.status("me")

        assert loaded is not None
        assert loaded.candidate.candidate_id == "me"
        assert loaded.resume_asset("ai-ml") is not None
        assert saved.resume_evidence.families[0].family_id == "data-engineer"
        assert status.onboarded is True
        assert status.ready_to_run is True
        assert status.ready_for_application_execution is True
        assert status.verified_evidence_count == 2
        assert status.resume_family_ids == ["ai-ml", "data-engineer"]
    app.dependency_overrides.clear()


def test_onboarding_rejects_unknown_resume_asset_family() -> None:
    payload = _payload_dict()
    payload["resume_assets"] = [
        {
            "family_id": "does-not-exist",
            "label": "Bad mapping",
            "file_path": "resume.pdf",
        }
    ]
    with pytest.raises(ValidationError, match="unknown families"):
        CandidateOnboardingPayload.model_validate(payload)


def test_onboarding_api_round_trip_and_minimized_status() -> None:
    client, _ = _client()
    response = client.put("/v1/candidates/me/onboarding", json=_payload_dict())
    assert response.status_code == 200

    full = client.get("/v1/candidates/me/onboarding")
    assert full.status_code == 200
    assert full.json()["candidate"]["candidate_id"] == "me"

    status = client.get("/v1/candidates/me/onboarding/status")
    assert status.status_code == 200
    body = status.json()
    assert body["ready_to_run"] is True
    assert body["verified_evidence_count"] == 2
    assert "facts" not in body

    asset = client.get("/v1/candidates/me/onboarding/resume-assets/ai-ml")
    assert asset.status_code == 200
    assert asset.json()["file_path"].endswith("ai-engineer.pdf")
    app.dependency_overrides.clear()


def test_onboarding_cli_loader_accepts_yaml_and_json(tmp_path) -> None:
    payload = _payload_dict()
    json_path = tmp_path / "onboarding.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")
    loaded_json = load_payload(json_path)
    assert loaded_json.candidate.candidate_id == "me"

    import yaml

    yaml_path = tmp_path / "onboarding.yaml"
    yaml_path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    loaded_yaml = load_payload(yaml_path)
    assert loaded_yaml.resume_evidence.candidate_id == "me"


def test_onboarding_cli_bundle_loads_owned_search_profiles(tmp_path) -> None:
    import yaml

    bundle = {
        "onboarding": _payload_dict(),
        "search_profiles": [
            _profile().model_dump(mode="json", exclude_none=True)
        ],
    }
    path = tmp_path / "bundle.yaml"
    path.write_text(yaml.safe_dump(bundle), encoding="utf-8")

    payload = load_payload(path)
    profiles = load_search_profiles(path)
    assert payload.candidate.candidate_id == "me"
    assert [profile.profile_id for profile in profiles] == ["profile-1"]
    assert profiles[0].minimum_salary == 65000


def test_run_onboarded_uses_persisted_candidate_and_evidence() -> None:
    client, factory = _client()

    with factory() as session:
        SqlAlchemySearchProfileRepository(session).save(_profile())
        SqlAlchemyCandidateOnboardingRepository(session).save(
            CandidateOnboardingPayload.model_validate(_payload_dict())
        )
        SqlAlchemyJobRepository(session).save(
            JobPosting(
                job_id="job-1",
                company="Data Co",
                title="Data Engineer",
                description="Build Python SQL data pipelines and analytics systems.",
                location="Remote",
                work_mode=WorkMode.REMOTE,
                salary_min=80000,
                salary_max=100000,
                salary_currency="USD",
                salary_interval="year",
                required_skills=["Python", "SQL", "pandas"],
            )
        )
        session.commit()

    command_center = client.get("/v1/command-center/profile-1")
    assert command_center.status_code == 200
    assert command_center.json()["onboarding"]["ready_to_run"] is True
    assert command_center.json()["onboarding"][
        "ready_for_application_execution"
    ] is True

    response = client.post("/v1/search-profiles/profile-1/run-onboarded")
    assert response.status_code == 200
    body = response.json()
    assert body["profile_id"] == "profile-1"
    assert body["prepared_count"] == 1
    assert body["prepared_jobs"][0]["job"]["job_id"] == "job-1"

    readiness = client.get("/v1/search-profiles/profile-1/readiness")
    assert readiness.status_code == 200
    assert readiness.json()["prepared_count"] == 1
    app.dependency_overrides.clear()
