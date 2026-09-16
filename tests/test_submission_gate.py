from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from jobops.models.browser_audit import BrowserAuditVendor
from jobops.models.submission import (
    PreparedSubmissionState,
    SubmissionAttempt,
    SubmissionAttemptStatus,
    SubmissionAuthorizationStatus,
    SubmissionExecutionOutcome,
    SubmissionExecutionRequest,
    SubmissionReadinessBlocker,
    SubmitAuthorization,
    SubmitAuthorizationCreate,
)
from jobops.submissions import (
    DuplicateSubmissionError,
    SubmissionAuthorizationInvalidError,
    SubmissionGate,
    SubmissionNotReadyError,
)

_HASH_A = "a" * 64
_HASH_B = "b" * 64
_NOW = datetime(2026, 9, 16, 16, 0, tzinfo=UTC)


class MemorySubmissionRepository:
    def __init__(self) -> None:
        self.authorizations: dict[str, SubmitAuthorization] = {}
        self.attempts: dict[str, SubmissionAttempt] = {}

    def create_authorization(self, item: SubmitAuthorization) -> SubmitAuthorization:
        self.authorizations[item.authorization_id] = item.model_copy(deep=True)
        return item.model_copy(deep=True)

    def get_authorization(self, authorization_id: str) -> SubmitAuthorization | None:
        item = self.authorizations.get(authorization_id)
        return None if item is None else item.model_copy(deep=True)

    def claim_authorization(
        self,
        authorization_id: str,
        *,
        attempt_id: str,
        consumed_at: datetime,
    ) -> SubmitAuthorization | None:
        current = self.authorizations.get(authorization_id)
        if current is None or current.status is not SubmissionAuthorizationStatus.ACTIVE:
            return None
        updated = current.model_copy(
            update={
                "status": SubmissionAuthorizationStatus.CONSUMED,
                "consumed_at": consumed_at,
                "attempt_id": attempt_id,
            },
            deep=True,
        )
        self.authorizations[authorization_id] = updated
        return updated.model_copy(deep=True)

    def revoke_authorization(
        self,
        authorization_id: str,
        *,
        revoked_at: datetime,
    ) -> SubmitAuthorization | None:
        current = self.authorizations.get(authorization_id)
        if current is None or current.status is not SubmissionAuthorizationStatus.ACTIVE:
            return None
        updated = current.model_copy(
            update={
                "status": SubmissionAuthorizationStatus.REVOKED,
                "revoked_at": revoked_at,
            },
            deep=True,
        )
        self.authorizations[authorization_id] = updated
        return updated.model_copy(deep=True)

    def get_successful_attempt(self, application_id: str) -> SubmissionAttempt | None:
        for attempt in self.attempts.values():
            if (
                attempt.application_id == application_id
                and attempt.status is SubmissionAttemptStatus.SUCCEEDED
            ):
                return attempt.model_copy(deep=True)
        return None

    def create_attempt(self, attempt: SubmissionAttempt) -> SubmissionAttempt:
        self.attempts[attempt.attempt_id] = attempt.model_copy(deep=True)
        return attempt.model_copy(deep=True)

    def finalize_attempt(
        self,
        attempt_id: str,
        *,
        outcome: SubmissionExecutionOutcome,
        completed_at: datetime,
    ) -> SubmissionAttempt | None:
        current = self.attempts.get(attempt_id)
        if current is None:
            return None
        updated = current.model_copy(
            update={
                "status": outcome.status,
                "submit_invoked": outcome.submit_invoked,
                "receipt_metadata": deepcopy(outcome.receipt_metadata),
                "error_code": outcome.error_code,
                "error_detail": outcome.error_detail,
                "completed_at": completed_at,
            },
            deep=True,
        )
        self.attempts[attempt_id] = updated
        return updated.model_copy(deep=True)


class SuccessExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def execute(
        self,
        authorization: SubmitAuthorization,
        state: PreparedSubmissionState,
    ) -> SubmissionExecutionOutcome:
        self.calls += 1
        assert authorization.application_id == state.application_id
        return SubmissionExecutionOutcome(
            status=SubmissionAttemptStatus.SUCCEEDED,
            submit_invoked=True,
            receipt_metadata={"synthetic_receipt": "ok"},
        )


class ExplodingExecutor:
    def execute(
        self,
        authorization: SubmitAuthorization,
        state: PreparedSubmissionState,
    ) -> SubmissionExecutionOutcome:
        raise RuntimeError("synthetic timeout after submit boundary")


def _state(**updates: object) -> PreparedSubmissionState:
    payload = {
        "application_id": "app-123",
        "job_id": "job-123",
        "vendor": BrowserAuditVendor.GREENHOUSE,
        "prepared_payload_sha256": _HASH_A,
        "audit_run_id": "audit-123",
        "submit_selector": "#submit-application",
        "submit_control_sha256": _HASH_B,
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
        "audit_created_at": _NOW - timedelta(minutes=1),
    }
    payload.update(updates)
    return PreparedSubmissionState.model_validate(payload)


def _authorize(
    gate: SubmissionGate,
    state: PreparedSubmissionState | None = None,
    *,
    now: datetime = _NOW,
    ttl_seconds: int = 300,
) -> SubmitAuthorization:
    return gate.authorize(
        SubmitAuthorizationCreate(
            state=state or _state(),
            authorized_by="Josh",
            note="I reviewed this exact synthetic application state and authorize submit.",
            ttl_seconds=ttl_seconds,
        ),
        now=now,
    )


def test_readiness_fails_closed_for_consequential_blockers() -> None:
    gate = SubmissionGate(MemorySubmissionRepository())
    result = gate.evaluate(
        _state(
            required_unresolved=1,
            pending_review=2,
            unanswered_red=1,
            unconfirmed_consent=1,
            submit_control_count=2,
            ats_context_matches=False,
        ),
        now=_NOW,
    )

    assert result.ready is False
    assert set(result.blockers) == {
        SubmissionReadinessBlocker.UNRESOLVED_REQUIRED_FIELDS,
        SubmissionReadinessBlocker.PENDING_REVIEW,
        SubmissionReadinessBlocker.UNANSWERED_RED_FIELDS,
        SubmissionReadinessBlocker.UNCONFIRMED_CONSENT,
        SubmissionReadinessBlocker.SUBMIT_CONTROL_NOT_UNIQUE,
        SubmissionReadinessBlocker.ATS_CONTEXT_MISMATCH,
    }


def test_old_audit_state_cannot_be_authorized() -> None:
    gate = SubmissionGate(MemorySubmissionRepository())

    with pytest.raises(SubmissionNotReadyError) as exc_info:
        _authorize(gate, _state(audit_created_at=_NOW - timedelta(minutes=20)))

    assert SubmissionReadinessBlocker.AUDIT_TOO_OLD in exc_info.value.readiness.blockers


def test_authorization_is_bound_to_exact_prepared_state() -> None:
    repo = MemorySubmissionRepository()
    gate = SubmissionGate(repo)
    state = _state()
    authorization = _authorize(gate, state)

    changed = state.model_copy(update={"prepared_payload_sha256": "c" * 64})
    with pytest.raises(SubmissionAuthorizationInvalidError, match="state changed"):
        gate.execute(
            SubmissionExecutionRequest(
                authorization_id=authorization.authorization_id,
                state=changed,
            ),
            SuccessExecutor(),
            now=_NOW + timedelta(seconds=1),
        )

    assert repo.get_authorization(authorization.authorization_id).status is SubmissionAuthorizationStatus.ACTIVE


def test_authorization_for_job_a_cannot_submit_job_b() -> None:
    repo = MemorySubmissionRepository()
    gate = SubmissionGate(repo)
    authorization = _authorize(gate)

    wrong_job = _state(job_id="job-999")
    with pytest.raises(SubmissionAuthorizationInvalidError):
        gate.execute(
            SubmissionExecutionRequest(
                authorization_id=authorization.authorization_id,
                state=wrong_job,
            ),
            SuccessExecutor(),
            now=_NOW + timedelta(seconds=1),
        )


def test_expired_authorization_cannot_submit() -> None:
    repo = MemorySubmissionRepository()
    gate = SubmissionGate(repo)
    authorization = _authorize(gate, ttl_seconds=30)

    with pytest.raises(SubmissionAuthorizationInvalidError, match="expired"):
        gate.execute(
            SubmissionExecutionRequest(
                authorization_id=authorization.authorization_id,
                state=_state(),
            ),
            SuccessExecutor(),
            now=_NOW + timedelta(seconds=31),
        )


def test_valid_authorization_executes_once_and_cannot_be_replayed() -> None:
    repo = MemorySubmissionRepository()
    gate = SubmissionGate(repo)
    executor = SuccessExecutor()
    authorization = _authorize(gate)
    request = SubmissionExecutionRequest(
        authorization_id=authorization.authorization_id,
        state=_state(),
    )

    attempt = gate.execute(request, executor, now=_NOW + timedelta(seconds=1))

    assert attempt.status is SubmissionAttemptStatus.SUCCEEDED
    assert attempt.submit_invoked is True
    assert executor.calls == 1
    consumed = repo.get_authorization(authorization.authorization_id)
    assert consumed is not None
    assert consumed.status is SubmissionAuthorizationStatus.CONSUMED
    assert consumed.attempt_id == attempt.attempt_id

    with pytest.raises(SubmissionAuthorizationInvalidError, match="consumed"):
        gate.execute(request, executor, now=_NOW + timedelta(seconds=2))
    assert executor.calls == 1


def test_executor_exception_becomes_indeterminate_and_is_not_retried() -> None:
    repo = MemorySubmissionRepository()
    gate = SubmissionGate(repo)
    authorization = _authorize(gate)
    request = SubmissionExecutionRequest(
        authorization_id=authorization.authorization_id,
        state=_state(),
    )

    attempt = gate.execute(request, ExplodingExecutor(), now=_NOW + timedelta(seconds=1))

    assert attempt.status is SubmissionAttemptStatus.INDETERMINATE
    assert attempt.submit_invoked is True
    assert attempt.error_code == "executor_exception"
    with pytest.raises(SubmissionAuthorizationInvalidError, match="consumed"):
        gate.execute(request, SuccessExecutor(), now=_NOW + timedelta(seconds=2))


def test_successful_application_blocks_new_authorization() -> None:
    repo = MemorySubmissionRepository()
    gate = SubmissionGate(repo)
    authorization = _authorize(gate)
    gate.execute(
        SubmissionExecutionRequest(
            authorization_id=authorization.authorization_id,
            state=_state(),
        ),
        SuccessExecutor(),
        now=_NOW + timedelta(seconds=1),
    )

    with pytest.raises(DuplicateSubmissionError, match="already has a successful submission"):
        _authorize(gate, now=_NOW + timedelta(seconds=2))


def test_revoked_authorization_cannot_submit() -> None:
    repo = MemorySubmissionRepository()
    gate = SubmissionGate(repo)
    authorization = _authorize(gate)
    revoked = gate.revoke(authorization.authorization_id, now=_NOW + timedelta(seconds=1))
    assert revoked.status is SubmissionAuthorizationStatus.REVOKED

    with pytest.raises(SubmissionAuthorizationInvalidError, match="revoked"):
        gate.execute(
            SubmissionExecutionRequest(
                authorization_id=authorization.authorization_id,
                state=_state(),
            ),
            SuccessExecutor(),
            now=_NOW + timedelta(seconds=2),
        )
