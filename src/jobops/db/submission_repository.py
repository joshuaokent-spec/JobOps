from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobops.db.models import SubmissionAttemptRecord, SubmitAuthorizationRecord
from jobops.models.browser_audit import BrowserAuditVendor
from jobops.models.submission import (
    SubmissionAttempt,
    SubmissionAttemptStatus,
    SubmissionAuthorizationStatus,
    SubmissionExecutionOutcome,
    SubmitAuthorization,
)


class SqlAlchemySubmissionRepository:
    """Transactional persistence for one-shot submit authorizations and receipts."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_authorization(self, item: SubmitAuthorization) -> SubmitAuthorization:
        record = SubmitAuthorizationRecord(
            authorization_id=item.authorization_id,
            application_id=item.application_id,
            job_id=item.job_id,
            vendor=item.vendor.value,
            state_fingerprint=item.state_fingerprint,
            prepared_payload_sha256=item.prepared_payload_sha256,
            submit_selector=item.submit_selector,
            submit_control_sha256=item.submit_control_sha256,
            audit_run_id=item.audit_run_id,
            authorized_by=item.authorized_by,
            note=item.note,
            status=item.status.value,
            attempt_id=item.attempt_id,
            created_at=item.created_at,
            expires_at=item.expires_at,
            consumed_at=item.consumed_at,
            revoked_at=item.revoked_at,
        )
        self.session.add(record)
        self.session.flush()
        return self._authorization_to_domain(record)

    def get_authorization(self, authorization_id: str) -> SubmitAuthorization | None:
        record = self.session.get(SubmitAuthorizationRecord, authorization_id)
        return None if record is None else self._authorization_to_domain(record)

    def claim_authorization(
        self,
        authorization_id: str,
        *,
        attempt_id: str,
        consumed_at: datetime,
    ) -> SubmitAuthorization | None:
        record = self.session.scalar(
            select(SubmitAuthorizationRecord)
            .where(SubmitAuthorizationRecord.authorization_id == authorization_id)
            .with_for_update()
        )
        if record is None:
            return None
        if record.status != SubmissionAuthorizationStatus.ACTIVE.value:
            return self._authorization_to_domain(record)
        if _as_utc(record.expires_at) <= _as_utc(consumed_at):
            record.status = SubmissionAuthorizationStatus.EXPIRED.value
            self.session.flush()
            return self._authorization_to_domain(record)

        record.status = SubmissionAuthorizationStatus.CONSUMED.value
        record.consumed_at = consumed_at
        record.attempt_id = attempt_id
        self.session.flush()
        return self._authorization_to_domain(record)

    def revoke_authorization(
        self,
        authorization_id: str,
        *,
        revoked_at: datetime,
    ) -> SubmitAuthorization | None:
        record = self.session.scalar(
            select(SubmitAuthorizationRecord)
            .where(SubmitAuthorizationRecord.authorization_id == authorization_id)
            .with_for_update()
        )
        if record is None:
            return None
        if record.status != SubmissionAuthorizationStatus.ACTIVE.value:
            return self._authorization_to_domain(record)
        record.status = SubmissionAuthorizationStatus.REVOKED.value
        record.revoked_at = revoked_at
        self.session.flush()
        return self._authorization_to_domain(record)

    def get_successful_attempt(self, application_id: str) -> SubmissionAttempt | None:
        record = self.session.scalar(
            select(SubmissionAttemptRecord).where(
                SubmissionAttemptRecord.successful_submission_key == application_id
            )
        )
        return None if record is None else self._attempt_to_domain(record)

    def get_attempt(self, attempt_id: str) -> SubmissionAttempt | None:
        record = self.session.get(SubmissionAttemptRecord, attempt_id)
        return None if record is None else self._attempt_to_domain(record)

    def create_attempt(self, attempt: SubmissionAttempt) -> SubmissionAttempt:
        record = SubmissionAttemptRecord(
            attempt_id=attempt.attempt_id,
            authorization_id=attempt.authorization_id,
            application_id=attempt.application_id,
            job_id=attempt.job_id,
            vendor=attempt.vendor.value,
            state_fingerprint=attempt.state_fingerprint,
            submit_selector=attempt.submit_selector,
            submit_control_sha256=attempt.submit_control_sha256,
            audit_run_id=attempt.audit_run_id,
            status=attempt.status.value,
            submit_invoked=attempt.submit_invoked,
            receipt_metadata=dict(attempt.receipt_metadata),
            error_code=attempt.error_code,
            error_detail=attempt.error_detail,
            started_at=attempt.started_at,
            completed_at=attempt.completed_at,
            successful_submission_key=(
                attempt.application_id
                if attempt.status is SubmissionAttemptStatus.SUCCEEDED
                else None
            ),
        )
        self.session.add(record)
        self.session.flush()
        return self._attempt_to_domain(record)

    def finalize_attempt(
        self,
        attempt_id: str,
        *,
        outcome: SubmissionExecutionOutcome,
        completed_at: datetime,
    ) -> SubmissionAttempt | None:
        record = self.session.scalar(
            select(SubmissionAttemptRecord)
            .where(SubmissionAttemptRecord.attempt_id == attempt_id)
            .with_for_update()
        )
        if record is None:
            return None
        if record.status != SubmissionAttemptStatus.EXECUTING.value:
            return self._attempt_to_domain(record)

        record.status = outcome.status.value
        record.submit_invoked = outcome.submit_invoked
        record.receipt_metadata = dict(outcome.receipt_metadata)
        record.error_code = outcome.error_code
        record.error_detail = outcome.error_detail
        record.completed_at = completed_at
        record.successful_submission_key = (
            record.application_id
            if outcome.status is SubmissionAttemptStatus.SUCCEEDED
            else None
        )
        self.session.flush()
        return self._attempt_to_domain(record)

    @staticmethod
    def _authorization_to_domain(record: SubmitAuthorizationRecord) -> SubmitAuthorization:
        return SubmitAuthorization(
            authorization_id=record.authorization_id,
            application_id=record.application_id,
            job_id=record.job_id,
            vendor=BrowserAuditVendor(record.vendor),
            state_fingerprint=record.state_fingerprint,
            prepared_payload_sha256=record.prepared_payload_sha256,
            submit_selector=record.submit_selector,
            submit_control_sha256=record.submit_control_sha256,
            audit_run_id=record.audit_run_id,
            authorized_by=record.authorized_by,
            note=record.note,
            status=SubmissionAuthorizationStatus(record.status),
            created_at=_as_utc(record.created_at),
            expires_at=_as_utc(record.expires_at),
            consumed_at=_as_utc(record.consumed_at) if record.consumed_at else None,
            revoked_at=_as_utc(record.revoked_at) if record.revoked_at else None,
            attempt_id=record.attempt_id,
        )

    @staticmethod
    def _attempt_to_domain(record: SubmissionAttemptRecord) -> SubmissionAttempt:
        return SubmissionAttempt(
            attempt_id=record.attempt_id,
            authorization_id=record.authorization_id,
            application_id=record.application_id,
            job_id=record.job_id,
            vendor=BrowserAuditVendor(record.vendor),
            state_fingerprint=record.state_fingerprint,
            submit_selector=record.submit_selector,
            submit_control_sha256=record.submit_control_sha256,
            audit_run_id=record.audit_run_id,
            status=SubmissionAttemptStatus(record.status),
            submit_invoked=record.submit_invoked,
            receipt_metadata=dict(record.receipt_metadata or {}),
            error_code=record.error_code,
            error_detail=record.error_detail,
            started_at=_as_utc(record.started_at),
            completed_at=_as_utc(record.completed_at) if record.completed_at else None,
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
