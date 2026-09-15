from datetime import UTC, datetime

from jobops.db.approval_repository import ApprovalRepository
from jobops.models.approval import (
    ApprovalCreate,
    ApprovalDecision,
    ApprovalItem,
    ApprovalStatus,
)


class ApprovalQueueError(RuntimeError):
    pass


class ApprovalNotFoundError(ApprovalQueueError):
    pass


class InvalidApprovalTransitionError(ApprovalQueueError):
    pass


class ApprovalDecisionError(ApprovalQueueError):
    pass


class ApprovalQueue:
    """Human-in-the-loop state machine for application-preparation approval."""

    def __init__(self, repository: ApprovalRepository):
        self.repository = repository

    def enqueue(self, item: ApprovalCreate) -> ApprovalItem:
        return self.repository.create(item)

    def decide(self, approval_id: str, decision: ApprovalDecision) -> ApprovalItem:
        current = self.repository.get(approval_id)
        if current is None:
            raise ApprovalNotFoundError(f"approval item not found: {approval_id}")

        if current.status is not ApprovalStatus.PENDING:
            if self._is_same_decision(current, decision):
                return current
            raise InvalidApprovalTransitionError(
                f"approval item is already {current.status.value}"
            )

        edited_answer = (
            decision.edited_answer.strip() if decision.edited_answer is not None else None
        )
        final_answer: str | None = None
        if decision.status is ApprovalStatus.APPROVED:
            final_answer = edited_answer or (
                current.proposed_answer.strip() if current.proposed_answer else None
            )
            if not final_answer:
                raise ApprovalDecisionError(
                    "approval requires a proposed answer or an explicit human-edited answer"
                )

        updated = self.repository.apply_decision(
            approval_id,
            status=decision.status,
            reviewer=decision.reviewer.strip(),
            decision_note=decision.note.strip(),
            edited_answer=edited_answer,
            final_answer=final_answer,
            reviewed_at=datetime.now(UTC),
        )
        if updated is None:
            raise ApprovalNotFoundError(f"approval item not found: {approval_id}")
        return updated

    @staticmethod
    def _is_same_decision(current: ApprovalItem, decision: ApprovalDecision) -> bool:
        edited_answer = (
            decision.edited_answer.strip() if decision.edited_answer is not None else None
        )
        return (
            current.status is decision.status
            and current.reviewer == decision.reviewer.strip()
            and current.decision_note == decision.note.strip()
            and current.edited_answer == edited_answer
        )
