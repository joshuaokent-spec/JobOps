import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from jobops.approvals import ApprovalDecisionError, ApprovalQueue, InvalidApprovalTransitionError
from jobops.db import SqlAlchemyApprovalRepository, SqlAlchemyJobRepository
from jobops.db.base import Base
from jobops.models.application_question import HandlingRoute, QuestionCategory, ReviewBand
from jobops.models.approval import ApprovalCreate, ApprovalDecision, ApprovalReason, ApprovalStatus
from jobops.models.draft_verification import VerificationStatus
from jobops.models.job import JobPosting


def _factory() -> sessionmaker[Session]:
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
    return factory


def _create(**overrides) -> ApprovalCreate:
    values = {
        "approval_id": "approval-1",
        "job_id": "job-1",
        "family_id": "data-engineering",
        "question": "Tell us about a data pipeline you improved.",
        "category": QuestionCategory.NARRATIVE,
        "route": HandlingRoute.DRAFT_WITH_REVIEW,
        "review_band": ReviewBand.YELLOW,
        "reason": ApprovalReason.NARRATIVE_DRAFT,
        "proposed_answer": "I built a verified Python and SQL ETL pipeline.",
        "verification_status": VerificationStatus.PASS,
        "evidence_ids": ["project-etl"],
    }
    values.update(overrides)
    return ApprovalCreate(**values)


def test_queue_persists_and_approves_human_edit() -> None:
    factory = _factory()
    with factory() as session:
        repo = SqlAlchemyApprovalRepository(session)
        queue = ApprovalQueue(repo)
        created = queue.enqueue(_create())
        session.commit()
        assert created.status is ApprovalStatus.PENDING
        assert repo.count(status=ApprovalStatus.PENDING) == 1

        approved = queue.decide(
            created.approval_id,
            ApprovalDecision(
                status=ApprovalStatus.APPROVED,
                reviewer="Josh",
                note="Verified against my project history.",
                edited_answer="I built a Python and SQL ETL pipeline from verified project work.",
            ),
        )
        session.commit()
        assert approved.status is ApprovalStatus.APPROVED
        assert approved.final_answer == approved.edited_answer
        assert approved.approved_for_preparation is True
        assert approved.submitted is False


def test_exact_repeated_decision_is_idempotent() -> None:
    factory = _factory()
    decision = ApprovalDecision(
        status=ApprovalStatus.REJECTED,
        reviewer="Josh",
        note="Not a good answer for this role.",
    )
    with factory() as session:
        queue = ApprovalQueue(SqlAlchemyApprovalRepository(session))
        item = queue.enqueue(_create())
        first = queue.decide(item.approval_id, decision)
        second = queue.decide(item.approval_id, decision)
        assert second == first


def test_conflicting_second_decision_is_rejected() -> None:
    factory = _factory()
    with factory() as session:
        queue = ApprovalQueue(SqlAlchemyApprovalRepository(session))
        item = queue.enqueue(_create())
        queue.decide(
            item.approval_id,
            ApprovalDecision(
                status=ApprovalStatus.REJECTED,
                reviewer="Josh",
                note="Reject this draft.",
            ),
        )
        with pytest.raises(InvalidApprovalTransitionError, match="already rejected"):
            queue.decide(
                item.approval_id,
                ApprovalDecision(
                    status=ApprovalStatus.APPROVED,
                    reviewer="Josh",
                    note="Conflicting decision.",
                ),
            )


def test_approval_requires_answer_text() -> None:
    factory = _factory()
    with factory() as session:
        queue = ApprovalQueue(SqlAlchemyApprovalRepository(session))
        item = queue.enqueue(_create(proposed_answer=None))
        with pytest.raises(ApprovalDecisionError, match="requires a proposed answer"):
            queue.decide(
                item.approval_id,
                ApprovalDecision(
                    status=ApprovalStatus.APPROVED,
                    reviewer="Josh",
                    note="Manual answer is still needed.",
                ),
            )


def test_blocked_verification_cannot_enter_queue() -> None:
    with pytest.raises(ValidationError, match="blocked verification results"):
        _create(verification_status=VerificationStatus.BLOCK)
