from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from jobops.api.dependencies import get_session
from jobops.api.main import app
from jobops.db.base import Base
from jobops.db.repositories import SqlAlchemyJobRepository
from jobops.models.job import JobPosting, WorkMode


def _client() -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    jobs = [
        JobPosting(
            job_id="eligible",
            company="GoodCo",
            title="Senior Data Engineer",
            work_mode=WorkMode.REMOTE,
            salary_min=70000,
            salary_max=90000,
            salary_currency="USD",
            salary_interval="year",
            source="lever",
            required_skills=["Python", "SQL"],
        ),
        JobPosting(
            job_id="low-floor",
            company="RangeCo",
            title="Data Engineer",
            work_mode=WorkMode.REMOTE,
            salary_min=60000,
            salary_max=90000,
            salary_currency="USD",
            salary_interval="year",
            source="greenhouse",
        ),
        JobPosting(
            job_id="hybrid",
            company="OfficeCo",
            title="Data Engineer",
            work_mode=WorkMode.HYBRID,
            salary_min=80000,
            salary_max=100000,
            salary_currency="USD",
            salary_interval="year",
            source="lever",
        ),
        JobPosting(
            job_id="wrong-role",
            company="AnalystCo",
            title="Data Analyst",
            work_mode=WorkMode.REMOTE,
            salary_min=100000,
            salary_max=120000,
            salary_currency="USD",
            salary_interval="year",
            source="greenhouse",
        ),
    ]
    with factory() as session:
        repo = SqlAlchemyJobRepository(session)
        for job in jobs:
            repo.save(job)
        session.commit()

    def override_session():
        session: Session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


def test_flagship_search_profile_persists_and_previews_hard_constraints() -> None:
    client = _client()
    created = client.post(
        "/v1/search-profiles",
        json={
            "candidate_id": "me",
            "name": "Remote Data Engineering >=65k",
            "role_queries": ["Data Engineer"],
            "allowed_work_modes": ["remote"],
            "minimum_salary": 65000,
            "salary_currency": "USD",
        },
    )
    assert created.status_code == 201
    profile = created.json()
    profile_id = profile["profile_id"]
    assert profile["minimum_salary"] == 65000

    fetched = client.get(f"/v1/search-profiles/{profile_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Remote Data Engineering >=65k"

    preview = client.post(
        f"/v1/search-profiles/{profile_id}/preview",
        json={
            "candidate": {
                "candidate_id": "me",
                "target_roles": ["Data Engineer"],
                "skills": ["Python", "SQL"],
                "years_experience": 3,
                "preferred_work_modes": ["remote"],
                "minimum_salary": 65000,
            }
        },
    )
    assert preview.status_code == 200
    payload = preview.json()
    assert payload["total_examined"] == 4
    assert payload["total_eligible"] == 1
    assert payload["total_rejected"] == 3
    assert [item["job"]["job_id"] for item in payload["ranked"]] == ["eligible"]
    assert payload["rejection_summary"] == {
        "role": 1,
        "salary_floor": 1,
        "work_mode": 1,
    }
    app.dependency_overrides.clear()


def test_search_profile_update_and_delete() -> None:
    client = _client()
    created = client.post(
        "/v1/search-profiles",
        json={"candidate_id": "me", "name": "Initial"},
    )
    profile_id = created.json()["profile_id"]

    updated = client.patch(
        f"/v1/search-profiles/{profile_id}",
        json={
            "name": "Updated",
            "allowed_work_modes": ["remote"],
            "minimum_salary": 65000,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated"
    assert updated.json()["minimum_salary"] == 65000

    deleted = client.delete(f"/v1/search-profiles/{profile_id}")
    assert deleted.status_code == 204
    assert client.get(f"/v1/search-profiles/{profile_id}").status_code == 404
    app.dependency_overrides.clear()
