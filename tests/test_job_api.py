from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from jobops.api.jobs import get_session
from jobops.api.main import app
from jobops.db.base import Base
from jobops.db.repositories import SqlAlchemyJobRepository
from jobops.models.job import JobPosting, WorkMode


def client_with_jobs() -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        repo = SqlAlchemyJobRepository(session)
        repo.save(
            JobPosting(
                job_id="1",
                company="Acme",
                title="Data Engineer",
                work_mode=WorkMode.REMOTE,
                salary_max=120000,
                source="lever",
                source_scope="acme",
                required_skills=["Python", "SQL"],
            )
        )
        repo.save(
            JobPosting(
                job_id="2",
                company="Acme",
                title="Data Analyst",
                work_mode=WorkMode.HYBRID,
                salary_max=80000,
                source="greenhouse",
                source_scope="acme",
            )
        )
        session.commit()

    def override_session():
        session: Session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


def test_job_list_filters() -> None:
    client = client_with_jobs()
    response = client.get(
        "/v1/jobs",
        params={"work_mode": "remote", "min_salary": 100000},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["job_id"] == "1"
    app.dependency_overrides.clear()


def test_rank_endpoint_orders_by_baseline_score() -> None:
    client = client_with_jobs()
    response = client.post(
        "/v1/jobs/rank",
        json={
            "candidate": {
                "candidate_id": "me",
                "target_roles": ["Data Engineer"],
                "skills": ["Python", "SQL"],
                "years_experience": 2,
            },
            "filters": {"active": True},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["job"]["job_id"] == "1"
    assert payload["items"][0]["score"]["overall"] >= payload["items"][1]["score"]["overall"]
    app.dependency_overrides.clear()
