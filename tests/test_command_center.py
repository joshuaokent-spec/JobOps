from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from jobops.api.dependencies import get_session
from jobops.api.main import app
from jobops.db.base import Base
from jobops.db.models import (\n    ApprovalRecord,\n    FlagshipPreparedJobRecord,\n    FlagshipRunRecord,\n)
from jobops.db.repositories import SqlAlchemyJobRepository
from jobops.db.search_profile_repository import SqlAlchemySearchProfileRepository
from jobops.models.application_question import HandlingRoute, QuestionCategory, ReviewBand
from jobops.models.approval import ApprovalReason
from jobops.models.flagship_run import FlagshipReadiness
from jobops.models.job import JobPosting, WorkMode
from jobops.models.search_profile import SearchProfile


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
    return TestClient(app), factory


def _profile() -> SearchProfile:
    return SearchProfile(
        profile_id="profile-1",
        candidate_id="me",
        name="Remote Data >=65k",
        role_queries=["Data Engineer"],
        allowed_work_modes=[WorkMode.REMOTE],
        minimum_salary=65000,
    )


def test_command_center_handles_profile_with_no_run() -> None:
    client, factory = _client()
    with factory() as session:
        SqlAlchemySearchProfileRepository(session).save(_profile())
        session.commit()

    response = client.get("/v1/command-center/profile-1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["has_run"] is False
    assert payload["metrics"] is None
    assert payload["ready_jobs"] == []
    assert payload["review_required_jobs"] == []
    assert payload["pending_approvals"] == []
    assert payload["actions"]["run"] == "/v1/search-profiles/profile-1/run"
    app.dependency_overrides.clear()


def test_command_center_joins_latest_jobs_and_minimizes_approval_content() -> None:
    client, factory = _client()
    now = datetime(2026, 9, 21, 20, 50, tzinfo=UTC)

    with factory() as session:
        SqlAlchemySearchProfileRepository(session).save(_profile())
        jobs = SqlAlchemyJobRepository(session)
        jobs.save(
            JobPosting(
                job_id="job-ready",
                company="Ready Co",
                title="Senior Data Engineer",
                location="Remote",
                work_mode=WorkMode.REMOTE,
                salary_min=80000,
                salary_max=100000,
                salary_currency="USD",
                source="lever",
                source_url="https://jobs.example/ready",
                apply_url="https://jobs.example/ready/apply",
            )
        )
        jobs.save(
            JobPosting(
                job_id="job-review",
                company="Review Co",
                title="Data Engineer",
                location="Remote",
                work_mode=WorkMode.REMOTE,
                salary_min=70000,
                salary_max=90000,
                salary_currency="USD",
                source="greenhouse",
                source_url="https://jobs.example/review",
            )
        )
        session.add(
            FlagshipRunRecord(
                run_id="run-1",
                profile_id="profile-1",
                candidate_id="me",
                started_at=now,
                completed_at=now,
                total_examined=8,
                total_hard_eligible=3,
                total_hard_rejected=5,
                total_fit_eligible=2,
                total_fit_rejected=1,
                prepared_count=2,
                ready_count=1,
                review_required_count=1,
                rejection_summary={"salary_floor": 3, "work_mode": 2},
            )
        )
        session.add_all(
            [
                FlagshipPreparedJobRecord(
                    run_id="run-1",
                    job_id="job-ready",
                    rank=1,
                    score=91.5,
                    resume_family_id="data-engineer",
                    resume_selection_score=88.0,
                    resume_low_confidence=False,
                    readiness=FlagshipReadiness.READY.value,
                    readiness_reasons=[],
                    evidence_ids=["evidence-1"],
                ),
                FlagshipPreparedJobRecord(
                    run_id="run-1",
                    job_id="job-review",
                    rank=2,
                    score=84.0,
                    resume_family_id="data-engineer",
                    resume_selection_score=61.0,
                    resume_low_confidence=True,
                    readiness=FlagshipReadiness.REVIEW_REQUIRED.value,
                    readiness_reasons=["Resume-family selection requires review."],
                    evidence_ids=[],
                ),
            ]
        )
        session.add(
            ApprovalRecord(
                approval_id="approval-1",
                job_id="job-review",
                family_id="data-engineer",
                question="Tell us about a relevant project.",
                category=QuestionCategory.NARRATIVE.value,
                route=HandlingRoute.DRAFT_WITH_REVIEW.value,
                review_band=ReviewBand.YELLOW.value,
                reason=ApprovalReason.NARRATIVE_DRAFT.value,
                status="pending",
                proposed_answer="PRIVATE PROPOSED ANSWER",
                final_answer="PRIVATE FINAL ANSWER",
                verification_findings=[],
                evidence_ids=[],
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    response = client.get("/v1/command-center/profile-1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["has_run"] is True
    assert payload["metrics"]["ready_count"] == 1
    assert payload["metrics"]["rejection_summary"]["salary_floor"] == 3
    assert payload["ready_jobs"][0]["job_id"] == "job-ready"
    assert payload["ready_jobs"][0]["apply_url"].endswith("/apply")
    assert payload["review_required_jobs"][0]["job_id"] == "job-review"
    assert payload["pending_approvals"][0]["approval_id"] == "approval-1"
    serialized = response.text
    assert "PRIVATE PROPOSED ANSWER" not in serialized
    assert "PRIVATE FINAL ANSWER" not in serialized
    app.dependency_overrides.clear()


def test_command_center_dashboard_is_zero_build_html() -> None:
    client, _ = _client()
    response = client.get("/command-center")
    assert response.status_code == 200
    assert "JobOps Command Center" in response.text
    assert "/v1/command-center/" in response.text
    assert "<script>" in response.text
    app.dependency_overrides.clear()
