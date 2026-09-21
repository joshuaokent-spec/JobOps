from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from jobops.api.dependencies import get_session
from jobops.api.main import app
from jobops.db import SqlAlchemyJobRepository
from jobops.db.base import Base
from jobops.models.job import JobPosting

_HASH_A = "a" * 64
_HASH_B = "b" * 64
_HASH_C = "c" * 64


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
            JobPosting(job_id="job-submit-1", company="Synthetic Co", title="Data Engineer")
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


def _state_payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "application_id": "application-submit-1",
        "job_id": "job-submit-1",
        "vendor": "generic",
        "prepared_payload_sha256": _HASH_A,
        "audit_run_id": "audit-submit-1",
        "audit_created_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        "browser_session_id": "browser-session-submit-1",
        "document_url_sha256": _HASH_B,
        "submit_selector": "#submit-application",
        "submit_control_sha256": _HASH_C,
        "required_unresolved": 0,
        "ambiguous_mappings": 0,
        "blocked_verification": 0,
        "pending_review": 0,
        "unanswered_red": 0,
        "unconfirmed_consent": 0,
        "submit_control_count": 1,
        "submit_control_enabled": True,
        "ats_context_matches": True,
        "browser_state_matches": True,
    }
    payload.update(updates)
    return payload


def test_readiness_authorization_lookup_and_revoke_are_separate_actions() -> None:
    client = _client()
    try:
        state = _state_payload()
        readiness = client.post("/v1/submissions/readiness", json=state)
        assert readiness.status_code == 200
        assert readiness.json()["ready"] is True

        created = client.post(
            "/v1/submissions/authorizations",
            json={
                "state": state,
                "authorized_by": "Josh",
                "note": "I reviewed this exact synthetic application state.",
                "ttl_seconds": 300,
            },
        )
        assert created.status_code == 201
        body = created.json()
        assert body["status"] == "active"
        assert body["browser_session_id"] == "browser-session-submit-1"
        authorization_id = body["authorization_id"]

        fetched = client.get(f"/v1/submissions/authorizations/{authorization_id}")
        assert fetched.status_code == 200
        assert fetched.json()["state_fingerprint"] == body["state_fingerprint"]

        revoked = client.post(
            f"/v1/submissions/authorizations/{authorization_id}/revoke",
            json={
                "revoked_by": "Josh",
                "note": "Do not submit this application state.",
            },
        )
        assert revoked.status_code == 200
        assert revoked.json()["status"] == "revoked"
        assert revoked.json()["revoked_by"] == "Josh"

        repeated = client.post(
            f"/v1/submissions/authorizations/{authorization_id}/revoke",
            json={"revoked_by": "Josh", "note": "Second revoke."},
        )
        assert repeated.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_authorization_fails_closed_for_blockers_and_unknown_jobs() -> None:
    client = _client()
    try:
        blocked = client.post(
            "/v1/submissions/authorizations",
            json={
                "state": _state_payload(unanswered_red=1),
                "authorized_by": "Josh",
                "note": "This should fail closed.",
            },
        )
        assert blocked.status_code == 409
        assert "unanswered_red_fields" in blocked.json()["detail"]["blockers"]

        missing_job = client.post(
            "/v1/submissions/authorizations",
            json={
                "state": _state_payload(job_id="missing-job"),
                "authorized_by": "Josh",
                "note": "Unknown job should fail.",
            },
        )
        assert missing_job.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_submission_attempt_lookup_is_read_only_and_no_stateless_submit_route_exists() -> None:
    client = _client()
    try:
        missing = client.get("/v1/submissions/attempts/missing-attempt")
        assert missing.status_code == 404

        no_bypass = client.post("/v1/submissions/execute", json={})
        assert no_bypass.status_code == 404
    finally:
        app.dependency_overrides.clear()
