from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from jobops.api.dependencies import get_session
from jobops.api.main import app
from jobops.db import SqlAlchemyJobRepository
from jobops.db.base import Base
from jobops.models.application_question import HandlingRoute, QuestionCategory, ReviewBand
from jobops.models.approval import ApprovalCreate, ApprovalReason
from jobops.models.draft_verification import VerificationStatus
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
            JobPosting(job_id="job-1", company="Acme", title="Data Engineer")
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


def _payload() -> dict[str, object]:
    return ApprovalCreate(
        approval_id="approval-1",
        job_id="job-1",
        family_id="data-engineering",
        question="Tell us about a data pipeline you improved.",
        category=QuestionCategory.NARRATIVE,
        route=HandlingRoute.DRAFT_WITH_REVIEW,
        review_band=ReviewBand.YELLOW,
        reason=ApprovalReason.NARRATIVE_DRAFT,
        proposed_answer="I built a verified Python and SQL ETL pipeline.",
        verification_status=VerificationStatus.PASS,
        evidence_ids=["project-etl"],
    ).model_dump(mode="json")


def test_create_list_get_and_decide() -> None:
    client = _client()
    try:
        created = client.post("/v1/approvals", json=_payload())
        assert created.status_code == 201
        assert created.json()["status"] == "pending"
        assert created.json()["submitted"] is False

        page = client.get(
            "/v1/approvals",
            params={"status": "pending", "job_id": "job-1"},
        )
        assert page.status_code == 200
        assert page.json()["total"] == 1

        item = client.get("/v1/approvals/approval-1")
        assert item.status_code == 200
        assert item.json()["evidence_ids"] == ["project-etl"]

        decision = {
            "status": "approved",
            "reviewer": "Josh",
            "note": "Reviewed for accuracy.",
            "edited_answer": "I built a verified Python and SQL ETL pipeline.",
        }
        approved = client.post("/v1/approvals/approval-1/decision", json=decision)
        assert approved.status_code == 200
        assert approved.json()["approved_for_preparation"] is True
        assert approved.json()["submitted"] is False

        repeated = client.post("/v1/approvals/approval-1/decision", json=decision)
        assert repeated.status_code == 200

        conflicting = client.post(
            "/v1/approvals/approval-1/decision",
            json={
                "status": "rejected",
                "reviewer": "Josh",
                "note": "Conflicting decision.",
            },
        )
        assert conflicting.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_unknown_job_and_blocked_verification_are_rejected() -> None:
    client = _client()
    try:
        unknown = _payload()
        unknown["job_id"] = "missing-job"
        assert client.post("/v1/approvals", json=unknown).status_code == 404

        blocked = _payload()
        blocked["verification_status"] = "block"
        assert client.post("/v1/approvals", json=blocked).status_code == 422
    finally:
        app.dependency_overrides.clear()
