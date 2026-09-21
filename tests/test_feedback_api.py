from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from jobops.api.dependencies import get_session
from jobops.api.main import app
from jobops.db import Base, SqlAlchemyJobRepository
from jobops.models.job import JobPosting


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
            JobPosting(job_id="job-1", company="Synthetic Co", title="Data Engineer")
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


def _payload(*, event_id: str = "event-1") -> dict[str, object]:
    return {
        "event_id": event_id,
        "event_type": "application_submitted",
        "job_id": "job-1",
        "application_id": "app-1",
        "candidate_id": "candidate-1",
        "resume_family_id": "data-engineering",
        "occurred_at": datetime(2026, 9, 20, 12, 0, tzinfo=UTC).isoformat(),
        "source": "browser",
        "actor": "jobops",
        "idempotency_key": "submit-app-1",
        "schema_version": 1,
        "metadata": {"ats": "greenhouse"},
        "model_name": "resume-selector",
        "model_version": "v0",
        "experiment_id": "exp-1",
    }


def test_feedback_api_create_replay_list_and_get() -> None:
    client = _client()
    try:
        created = client.post("/v1/feedback/events", json=_payload())
        assert created.status_code == 201
        body = created.json()
        assert body["event_id"] == "event-1"
        assert body["event_type"] == "application_submitted"
        assert body["observed_at"]
        assert body["metadata"] == {"ats": "greenhouse"}

        replay = client.post(
            "/v1/feedback/events",
            json=_payload(event_id="event-retry"),
        )
        assert replay.status_code == 201
        assert replay.json()["event_id"] == "event-1"

        page = client.get(
            "/v1/feedback/events",
            params={
                "job_id": "job-1",
                "application_id": "app-1",
                "event_type": "application_submitted",
            },
        )
        assert page.status_code == 200
        assert page.json()["total"] == 1
        assert page.json()["items"][0]["event_id"] == "event-1"

        fetched = client.get("/v1/feedback/events/event-1")
        assert fetched.status_code == 200
        assert fetched.json()["experiment_id"] == "exp-1"
    finally:
        app.dependency_overrides.clear()


def test_feedback_api_rejects_conflicting_idempotency_and_sensitive_metadata() -> None:
    client = _client()
    try:
        assert client.post("/v1/feedback/events", json=_payload()).status_code == 201

        conflict = _payload(event_id="event-2")
        conflict["event_type"] = "rejected"
        response = client.post("/v1/feedback/events", json=conflict)
        assert response.status_code == 409

        sensitive = _payload(event_id="event-3")
        sensitive["idempotency_key"] = "sensitive-event"
        sensitive["metadata"] = {"recruiter_message": "private message"}
        response = client.post("/v1/feedback/events", json=sensitive)
        assert response.status_code == 422

        unknown = _payload(event_id="event-4")
        unknown["idempotency_key"] = "unknown-job"
        unknown["job_id"] = "missing-job"
        assert client.post("/v1/feedback/events", json=unknown).status_code == 404
    finally:
        app.dependency_overrides.clear()
