from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from jobops.api.dependencies import get_session
from jobops.api.main import app
from jobops.api.search_profiles import get_discovery_providers
from jobops.db.base import Base
from jobops.db.models import FlagshipRunRecord
from jobops.ingestion.models import SourceJobPosting
from jobops.models.discovery import DiscoveryProviderName


class FakeProvider:
    provider_name = "jobicy"

    def __init__(self, jobs: list[SourceJobPosting]):
        self.jobs = jobs

    def supports(self, profile):
        return True, None

    async def discover(self, profile, *, limit, client):
        return self.jobs[:limit], 1


def _build_client() -> tuple[TestClient, sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    jobs = [
        SourceJobPosting(
            source="jobicy",
            source_scope="public-remote",
            source_job_id="data-1",
            company="GoodData",
            title="Data Engineer",
            location="Remote",
            workplace_type="remote",
            salary_min=90000,
            salary_max=110000,
            salary_currency="USD",
            salary_interval="year",
            required_skills=["Python", "SQL"],
        ),
        SourceJobPosting(
            source="jobicy",
            source_scope="public-remote",
            source_job_id="ai-1",
            company="GoodAI",
            title="AI Engineer",
            location="Remote",
            workplace_type="remote",
            salary_min=100000,
            salary_max=130000,
            salary_currency="USD",
            salary_interval="year",
            required_skills=["Python", "Machine Learning"],
        ),
    ]

    def override_session():
        session: Session = factory()
        try:
            yield session
        finally:
            session.close()

    def override_providers():
        return {DiscoveryProviderName.JOBICY: FakeProvider(jobs)}

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_discovery_providers] = override_providers
    return TestClient(app), factory


def _request() -> dict:
    return {
        "candidate": {
            "candidate_id": "me",
            "target_roles": ["Data Engineer", "AI Engineer"],
            "skills": ["Python", "SQL", "Machine Learning"],
            "years_experience": 3,
            "preferred_work_modes": ["remote"],
            "minimum_salary": 65000,
        },
        "resume_evidence": {
            "candidate_id": "me",
            "sources": [
                {
                    "source_id": "data-source",
                    "kind": "project_artifact",
                    "label": "Data pipeline project",
                }
            ],
            "items": [
                {
                    "evidence_id": "data-project",
                    "kind": "project",
                    "claim": "Built Python and SQL data pipelines.",
                    "skills": ["Python", "SQL"],
                    "role_families": ["data_engineering"],
                    "source_refs": ["data-source"],
                    "verified": True,
                }
            ],
            "families": [
                {
                    "family_id": "data-engineer",
                    "name": "Data Engineering",
                    "role_families": ["data_engineering"],
                    "priority_skills": ["Python", "SQL"],
                    "pinned_evidence_ids": ["data-project"],
                },
                {
                    "family_id": "ai-engineer",
                    "name": "AI Engineering",
                    "role_families": ["ai_ml"],
                    "priority_skills": ["Python", "Machine Learning"],
                },
            ],
        },
        "discovery": {"providers": ["jobicy"], "limit_per_provider": 20},
        "candidate_pool": 100,
        "max_jobs": 10,
        "evidence_limit": 3,
    }


def _profile(client: TestClient) -> str:
    response = client.post(
        "/v1/search-profiles",
        json={
            "candidate_id": "me",
            "name": "Remote Data + AI",
            "role_queries": ["Data Engineer", "AI Engineer"],
            "allowed_work_modes": ["remote"],
            "minimum_salary": 65000,
        },
    )
    assert response.status_code == 201
    return response.json()["profile_id"]


def test_latest_readiness_and_exception_inbox_are_actionable_and_durable() -> None:
    client, factory = _build_client()
    try:
        profile_id = _profile(client)

        first = client.post(
            f"/v1/search-profiles/{profile_id}/run",
            json=_request(),
        )
        assert first.status_code == 200

        readiness = client.get(
            f"/v1/search-profiles/{profile_id}/readiness"
        )
        assert readiness.status_code == 200
        first_summary = readiness.json()
        assert first_summary["prepared_count"] == 2
        assert first_summary["ready_count"] == 1
        assert first_summary["review_required_count"] == 1

        ready_job = next(
            job for job in first_summary["jobs"] if job["readiness"] == "ready"
        )
        review_job = next(
            job
            for job in first_summary["jobs"]
            if job["readiness"] == "review_required"
        )
        assert ready_job["company"] == "GoodData"
        assert review_job["company"] == "GoodAI"
        assert review_job["readiness_reasons"] == [
            "No verified evidence is available for the selected resume family."
        ]

        approval = client.post(
            "/v1/approvals",
            json={
                "job_id": ready_job["job_id"],
                "family_id": ready_job["family_id"],
                "question": "Confirm preferred work arrangement.",
                "category": "preference",
                "route": "draft_with_review",
                "review_band": "yellow",
                "reason": "preference",
                "proposed_answer": "Remote",
                "evidence_ids": ready_job["evidence_ids"],
            },
        )
        assert approval.status_code == 201

        inbox = client.get(
            f"/v1/search-profiles/{profile_id}/exceptions"
        )
        assert inbox.status_code == 200
        payload = inbox.json()
        assert payload["ready_count"] == 1
        assert payload["review_required_count"] == 1
        assert payload["pending_approval_count"] == 1
        assert payload["total_exceptions"] == 2
        assert {item["kind"] for item in payload["items"]} == {
            "approval",
            "readiness",
        }
        assert {item["company"] for item in payload["items"]} == {
            "GoodData",
            "GoodAI",
        }

        first_run_id = first_summary["run_id"]
        second = client.post(
            f"/v1/search-profiles/{profile_id}/run",
            json=_request(),
        )
        assert second.status_code == 200
        latest = client.get(
            f"/v1/search-profiles/{profile_id}/readiness"
        ).json()
        assert latest["run_id"] != first_run_id

        with factory() as session:
            run_count = session.scalar(
                select(func.count()).select_from(FlagshipRunRecord)
            )
            assert run_count == 2
    finally:
        app.dependency_overrides.clear()


def test_readiness_requires_a_completed_flagship_run() -> None:
    client, _ = _build_client()
    try:
        profile_id = _profile(client)
        response = client.get(
            f"/v1/search-profiles/{profile_id}/readiness"
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "no flagship runs found"
    finally:
        app.dependency_overrides.clear()
