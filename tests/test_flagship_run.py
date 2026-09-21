from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from jobops.api.dependencies import get_session
from jobops.api.main import app
from jobops.api.search_profiles import get_discovery_providers
from jobops.db.base import Base
from jobops.db.repositories import SqlAlchemyJobRepository
from jobops.ingestion.models import SourceJobPosting
from jobops.models.discovery import DiscoveryProviderName
from jobops.models.job import JobPosting, WorkMode


class FakeProvider:
    provider_name = "jobicy"

    def __init__(self, jobs: list[SourceJobPosting]):
        self.jobs = jobs

    def supports(self, profile):
        return True, None

    async def discover(self, profile, *, limit, client):
        return self.jobs[:limit], 1


def _resume_evidence(candidate_id: str = "me") -> dict:
    return {
        "candidate_id": candidate_id,
        "sources": [
            {
                "source_id": "source-project",
                "kind": "project_artifact",
                "label": "Pipeline project",
            }
        ],
        "items": [
            {
                "evidence_id": "project-pipeline",
                "kind": "project",
                "claim": "Built Python and SQL data pipelines.",
                "skills": ["Python", "SQL", "ETL"],
                "role_families": ["data_engineering"],
                "source_refs": ["source-project"],
                "verified": True,
            }
        ],
        "families": [
            {
                "family_id": "data-engineer",
                "name": "Data Engineering",
                "role_families": ["data_engineering"],
                "priority_skills": ["Python", "SQL"],
                "pinned_evidence_ids": ["project-pipeline"],
            }
        ],
    }


def _candidate(candidate_id: str = "me") -> dict:
    return {
        "candidate_id": candidate_id,
        "target_roles": ["Data Engineer"],
        "skills": ["Python", "SQL", "ETL"],
        "years_experience": 3,
        "preferred_work_modes": ["remote"],
        "minimum_salary": 65000,
    }


def _client() -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as session:
        SqlAlchemyJobRepository(session).save(
            JobPosting(
                job_id="legacy-onsite",
                company="LegacyCo",
                title="Data Engineer",
                location="Detroit, MI",
                work_mode=WorkMode.ONSITE,
                salary_min=90000,
                salary_max=110000,
                salary_currency="USD",
                salary_interval="year",
                source="greenhouse",
            )
        )
        session.commit()

    def override_session():
        session: Session = factory()
        try:
            yield session
        finally:
            session.close()

    eligible = SourceJobPosting(
        source="jobicy",
        source_scope="public-remote",
        source_job_id="eligible",
        company="GoodCo",
        title="Data Engineer",
        location="Remote",
        workplace_type="remote",
        salary_min=90000,
        salary_max=110000,
        salary_currency="USD",
        salary_interval="year",
        required_skills=["Python", "SQL"],
    )
    below_floor = SourceJobPosting(
        source="jobicy",
        source_scope="public-remote",
        source_job_id="below-floor",
        company="LowCo",
        title="Data Engineer",
        location="Remote",
        workplace_type="remote",
        salary_min=60000,
        salary_max=90000,
        salary_currency="USD",
        salary_interval="year",
        required_skills=["Python", "SQL"],
    )

    def override_providers():
        return {
            DiscoveryProviderName.JOBICY: FakeProvider([eligible, below_floor])
        }

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_discovery_providers] = override_providers
    return TestClient(app)


def _create_profile(client: TestClient) -> str:
    response = client.post(
        "/v1/search-profiles",
        json={
            "candidate_id": "me",
            "name": "Remote Data Engineering",
            "role_queries": ["Data Engineer"],
            "allowed_work_modes": ["remote"],
            "minimum_salary": 65000,
            "salary_currency": "USD",
            "minimum_fit_score": 70,
        },
    )
    assert response.status_code == 201
    return response.json()["profile_id"]


def test_flagship_run_composes_discovery_ranking_resume_and_evidence() -> None:
    client = _client()
    try:
        profile_id = _create_profile(client)
        response = client.post(
            f"/v1/search-profiles/{profile_id}/run",
            json={
                "candidate": _candidate(),
                "resume_evidence": _resume_evidence(),
                "discovery": {
                    "providers": ["jobicy"],
                    "limit_per_provider": 20,
                },
                "candidate_pool": 100,
                "max_jobs": 10,
                "evidence_limit": 3,
            },
        )

        assert response.status_code == 200
        payload = response.json()

        assert payload["discovery"]["fetched"] == 2
        assert payload["discovery"]["eligible"] == 1
        assert payload["discovery"]["rejected"] == 1
        assert payload["discovery"]["persisted"] == 1
        assert payload["discovery"]["rejection_summary"] == {"salary_floor": 1}

        assert payload["total_examined"] == 2
        assert payload["total_hard_eligible"] == 1
        assert payload["total_hard_rejected"] == 1
        assert payload["total_fit_eligible"] == 1
        assert payload["total_fit_rejected"] == 0
        assert payload["rejection_summary"] == {"work_mode": 1}

        assert payload["prepared_count"] == 1
        assert payload["ready_count"] == 1
        assert payload["review_required_count"] == 0

        prepared = payload["prepared_jobs"][0]
        assert prepared["rank"] == 1
        assert prepared["job"]["company"] == "GoodCo"
        assert prepared["resume_selection"]["chosen_family_id"] == "data-engineer"
        assert prepared["evidence"]["hits"][0]["evidence"]["evidence_id"] == (
            "project-pipeline"
        )
        assert prepared["readiness"] == "ready"
    finally:
        app.dependency_overrides.clear()


def test_flagship_run_rejects_candidate_from_another_profile_owner() -> None:
    client = _client()
    try:
        profile_id = _create_profile(client)
        response = client.post(
            f"/v1/search-profiles/{profile_id}/run",
            json={
                "candidate": _candidate("other"),
                "resume_evidence": _resume_evidence("other"),
                "discovery": {
                    "providers": ["jobicy"],
                    "limit_per_provider": 1,
                },
            },
        )
        assert response.status_code == 422
        assert response.json()["detail"] == (
            "candidate does not match search profile owner"
        )
    finally:
        app.dependency_overrides.clear()
