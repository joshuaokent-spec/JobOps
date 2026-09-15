from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jobops.db.models import ApprovalRecord
from jobops.models.application_question import HandlingRoute, QuestionCategory, ReviewBand
from jobops.models.approval import ApprovalCreate, ApprovalItem, ApprovalStatus
from jobops.models.draft_verification import VerificationFinding, VerificationStatus


class ApprovalRepository(Protocol):
    def create(self, item: ApprovalCreate) -> ApprovalItem: ...

    def get(self, approval_id: str) -> ApprovalItem | None: ...

    def list(
        self,
        *,
        status: ApprovalStatus | None = None,
        job_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[ApprovalItem]: ...

    def count(
        self,
        *,
        status: ApprovalStatus | None = None,
        job_id: str | None = None,
    ) -> int: ...

    def apply_decision(
        self,
        approval_id: str,
        *,
        status: ApprovalStatus,
        reviewer: str,
        decision_note: str,
        edited_answer: str | None,
        final_answer: str | None,
        reviewed_at: datetime,
    ) -> ApprovalItem | None: ...


class SqlAlchemyApprovalRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, item: ApprovalCreate) -> ApprovalItem:
        record = ApprovalRecord(
            approval_id=item.approval_id,
            job_id=item.job_id,
            family_id=item.family_id,
            question=item.question,
            category=item.category.value,
            route=item.route.value,
            review_band=item.review_band.value,
            reason=item.reason.value,
            status=ApprovalStatus.PENDING.value,
            proposed_answer=item.proposed_answer,
            verification_status=(
                item.verification_status.value if item.verification_status is not None else None
            ),
            verification_findings=[
                finding.model_dump(mode="json") for finding in item.verification_findings
            ],
            evidence_ids=list(item.evidence_ids),
        )
        self.session.add(record)
        self.session.flush()
        return self._to_domain(record)

    def get(self, approval_id: str) -> ApprovalItem | None:
        record = self.session.get(ApprovalRecord, approval_id)
        return None if record is None else self._to_domain(record)

    def list(
        self,
        *,
        status: ApprovalStatus | None = None,
        job_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[ApprovalItem]:
        statement = select(ApprovalRecord)
        statement = self._apply_filters(statement, status=status, job_id=job_id)
        statement = (
            statement.order_by(ApprovalRecord.created_at.asc(), ApprovalRecord.approval_id)
            .limit(limit)
            .offset(offset)
        )
        return [self._to_domain(record) for record in self.session.scalars(statement).all()]

    def count(
        self,
        *,
        status: ApprovalStatus | None = None,
        job_id: str | None = None,
    ) -> int:
        statement = select(func.count()).select_from(ApprovalRecord)
        statement = self._apply_filters(statement, status=status, job_id=job_id)
        return int(self.session.scalar(statement) or 0)

    def apply_decision(
        self,
        approval_id: str,
        *,
        status: ApprovalStatus,
        reviewer: str,
        decision_note: str,
        edited_answer: str | None,
        final_answer: str | None,
        reviewed_at: datetime,
    ) -> ApprovalItem | None:
        record = self.session.get(ApprovalRecord, approval_id)
        if record is None:
            return None
        record.status = status.value
        record.reviewer = reviewer
        record.decision_note = decision_note
        record.edited_answer = edited_answer
        record.final_answer = final_answer
        record.reviewed_at = reviewed_at
        self.session.flush()
        return self._to_domain(record)

    @staticmethod
    def _apply_filters(statement, *, status: ApprovalStatus | None, job_id: str | None):
        if status is not None:
            statement = statement.where(ApprovalRecord.status == status.value)
        if job_id:
            statement = statement.where(ApprovalRecord.job_id == job_id.strip())
        return statement

    @staticmethod
    def _to_domain(record: ApprovalRecord) -> ApprovalItem:
        status = ApprovalStatus(record.status)
        verification_status = (
            VerificationStatus(record.verification_status)
            if record.verification_status is not None
            else None
        )
        findings = [
            VerificationFinding.model_validate(item)
            for item in (record.verification_findings or [])
        ]
        return ApprovalItem(
            approval_id=record.approval_id,
            job_id=record.job_id,
            family_id=record.family_id,
            question=record.question,
            category=QuestionCategory(record.category),
            route=HandlingRoute(record.route),
            review_band=ReviewBand(record.review_band),
            reason=record.reason,
            status=status,
            proposed_answer=record.proposed_answer,
            edited_answer=record.edited_answer,
            final_answer=record.final_answer,
            verification_status=verification_status,
            verification_findings=findings,
            evidence_ids=list(record.evidence_ids or []),
            reviewer=record.reviewer,
            decision_note=record.decision_note,
            created_at=_as_utc(record.created_at),
            updated_at=_as_utc(record.updated_at),
            reviewed_at=_as_utc(record.reviewed_at) if record.reviewed_at else None,
            approved_for_preparation=status is ApprovalStatus.APPROVED,
            submitted=False,
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
