import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import uuid4

from jobops.browser.audit_redaction import sanitize_text, sanitize_url
from jobops.models.submission import (
    PreparedSubmissionState,
    SubmissionAttempt,
    SubmissionAttemptStatus,
    SubmissionAuthorizationStatus,
    SubmissionExecutionOutcome,
    SubmissionExecutionRequest,
    SubmissionReadinessBlocker,
    SubmissionReadinessResult,
    SubmitAuthorization,
    SubmitAuthorizationCreate,
    SubmitAuthorizationRevoke,
)

_SENSITIVE_RECEIPT_KEY = re.compile(
    r"(?:answer|value|token|auth|secret|password|passwd|session|cookie|credential|"
    r"api[-_]?key|authorization|ssn|social[-_]?security)",
    re.IGNORECASE,
)
_URL_KEY = re.compile(r"(?:^url$|_url$|^href$|^location$)", re.IGNORECASE)
_OMITTED = "[OMITTED]"


class SubmissionGateError(RuntimeError):
    pass


class SubmissionNotReadyError(SubmissionGateError):
    def __init__(self, readiness: SubmissionReadinessResult):
        self.readiness = readiness
        blockers = ", ".join(blocker.value for blocker in readiness.blockers)
        super().__init__(f"submission is not ready: {blockers}")


class SubmissionAuthorizationNotFoundError(SubmissionGateError):
    pass


class SubmissionAuthorizationInvalidError(SubmissionGateError):
    pass


class DuplicateSubmissionError(SubmissionGateError):
    pass


class SubmissionExecutor(Protocol):
    def execute(
        self,
        authorization: SubmitAuthorization,
        state: PreparedSubmissionState,
    ) -> SubmissionExecutionOutcome: ...


class SubmissionRepository(Protocol):
    def create_authorization(self, item: SubmitAuthorization) -> SubmitAuthorization: ...

    def get_authorization(self, authorization_id: str) -> SubmitAuthorization | None: ...

    def claim_authorization(
        self,
        authorization_id: str,
        *,
        attempt_id: str,
        consumed_at: datetime,
    ) -> SubmitAuthorization | None: ...

    def revoke_authorization(
        self,
        authorization_id: str,
        *,
        revoked_at: datetime,
        revoked_by: str,
        revoke_note: str,
    ) -> SubmitAuthorization | None: ...

    def get_successful_attempt(self, application_id: str) -> SubmissionAttempt | None: ...

    def get_blocking_attempt(self, application_id: str) -> SubmissionAttempt | None: ...

    def create_attempt(self, attempt: SubmissionAttempt) -> SubmissionAttempt | None: ...

    def persist_execution_claim(self) -> None: ...

    def persist_execution_result(self) -> None: ...

    def finalize_attempt(
        self,
        attempt_id: str,
        *,
        outcome: SubmissionExecutionOutcome,
        completed_at: datetime,
    ) -> SubmissionAttempt | None: ...


class SubmissionReadinessEvaluator:
    def __init__(self, *, max_audit_age: timedelta = timedelta(minutes=15)) -> None:
        if max_audit_age <= timedelta(0):
            raise ValueError("max_audit_age must be positive")
        self.max_audit_age = max_audit_age

    def evaluate(
        self,
        state: PreparedSubmissionState,
        *,
        now: datetime | None = None,
    ) -> SubmissionReadinessResult:
        evaluated_at = _as_utc(now or datetime.now(UTC))
        blockers: list[SubmissionReadinessBlocker] = []

        if (
            state.audit_run_id is None
            or state.audit_created_at is None
            or state.browser_session_id is None
            or state.document_url_sha256 is None
        ):
            blockers.append(SubmissionReadinessBlocker.MISSING_AUDIT_CONTEXT)
        if state.required_unresolved:
            blockers.append(SubmissionReadinessBlocker.UNRESOLVED_REQUIRED_FIELDS)
        if state.ambiguous_mappings:
            blockers.append(SubmissionReadinessBlocker.AMBIGUOUS_MAPPINGS)
        if state.blocked_verification:
            blockers.append(SubmissionReadinessBlocker.BLOCKED_VERIFICATION)
        if state.pending_review:
            blockers.append(SubmissionReadinessBlocker.PENDING_REVIEW)
        if state.unanswered_red:
            blockers.append(SubmissionReadinessBlocker.UNANSWERED_RED_FIELDS)
        if state.unconfirmed_consent:
            blockers.append(SubmissionReadinessBlocker.UNCONFIRMED_CONSENT)
        if state.submit_control_count != 1:
            blockers.append(SubmissionReadinessBlocker.SUBMIT_CONTROL_NOT_UNIQUE)
        if not state.submit_control_enabled:
            blockers.append(SubmissionReadinessBlocker.SUBMIT_CONTROL_DISABLED)
        if not state.ats_context_matches:
            blockers.append(SubmissionReadinessBlocker.ATS_CONTEXT_MISMATCH)
        if not state.browser_state_matches:
            blockers.append(SubmissionReadinessBlocker.BROWSER_STATE_MISMATCH)
        if state.audit_created_at is not None:
            audit_created_at = _as_utc(state.audit_created_at)
            if evaluated_at - audit_created_at > self.max_audit_age:
                blockers.append(SubmissionReadinessBlocker.AUDIT_TOO_OLD)

        return SubmissionReadinessResult(
            application_id=state.application_id,
            job_id=state.job_id,
            state_fingerprint=self.fingerprint(state),
            ready=not blockers,
            blockers=blockers,
            evaluated_at=evaluated_at,
        )

    @staticmethod
    def fingerprint(state: PreparedSubmissionState) -> str:
        payload = state.model_dump(mode="json")
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class SubmissionGate:
    """Explicit, one-shot human authorization boundary for final submission."""

    def __init__(
        self,
        repository: SubmissionRepository,
        *,
        readiness: SubmissionReadinessEvaluator | None = None,
    ) -> None:
        self.repository = repository
        self.readiness = readiness or SubmissionReadinessEvaluator()

    def evaluate(
        self,
        state: PreparedSubmissionState,
        *,
        now: datetime | None = None,
    ) -> SubmissionReadinessResult:
        return self.readiness.evaluate(state, now=now)

    def authorize(
        self,
        request: SubmitAuthorizationCreate,
        *,
        now: datetime | None = None,
    ) -> SubmitAuthorization:
        created_at = _as_utc(now or datetime.now(UTC))
        result = self.readiness.evaluate(request.state, now=created_at)
        if not result.ready:
            raise SubmissionNotReadyError(result)
        self._assert_no_blocking_attempt(request.state.application_id)

        assert request.state.audit_run_id is not None
        assert request.state.browser_session_id is not None
        assert request.state.document_url_sha256 is not None
        authorization = SubmitAuthorization(
            application_id=request.state.application_id,
            job_id=request.state.job_id,
            vendor=request.state.vendor,
            state_fingerprint=result.state_fingerprint,
            prepared_payload_sha256=request.state.prepared_payload_sha256,
            audit_run_id=request.state.audit_run_id,
            browser_session_id=request.state.browser_session_id,
            document_url_sha256=request.state.document_url_sha256,
            submit_selector=request.state.submit_selector,
            submit_control_sha256=request.state.submit_control_sha256,
            authorized_by=request.authorized_by.strip(),
            note=request.note.strip(),
            status=SubmissionAuthorizationStatus.ACTIVE,
            created_at=created_at,
            expires_at=created_at + timedelta(seconds=request.ttl_seconds),
        )
        return self.repository.create_authorization(authorization)

    def revoke(
        self,
        authorization_id: str,
        request: SubmitAuthorizationRevoke,
        *,
        now: datetime | None = None,
    ) -> SubmitAuthorization:
        current = self.repository.get_authorization(authorization_id)
        if current is None:
            raise SubmissionAuthorizationNotFoundError(
                f"submit authorization not found: {authorization_id}"
            )
        if current.status is not SubmissionAuthorizationStatus.ACTIVE:
            raise SubmissionAuthorizationInvalidError(
                f"submit authorization is already {current.status.value}"
            )
        revoked = self.repository.revoke_authorization(
            authorization_id,
            revoked_at=_as_utc(now or datetime.now(UTC)),
            revoked_by=request.revoked_by.strip(),
            revoke_note=request.note.strip(),
        )
        if revoked is None:
            raise SubmissionAuthorizationNotFoundError(
                f"submit authorization not found: {authorization_id}"
            )
        return revoked

    def execute(
        self,
        request: SubmissionExecutionRequest,
        executor: SubmissionExecutor,
        *,
        now: datetime | None = None,
    ) -> SubmissionAttempt:
        started_at = _as_utc(now or datetime.now(UTC))
        authorization = self.repository.get_authorization(request.authorization_id)
        if authorization is None:
            raise SubmissionAuthorizationNotFoundError(
                f"submit authorization not found: {request.authorization_id}"
            )
        self._validate_authorization(authorization, request.state, now=started_at)
        self._assert_no_blocking_attempt(request.state.application_id)

        attempt_id = str(uuid4())
        claimed = self.repository.claim_authorization(
            authorization.authorization_id,
            attempt_id=attempt_id,
            consumed_at=started_at,
        )
        if claimed is None or claimed.status is not SubmissionAuthorizationStatus.CONSUMED:
            raise SubmissionAuthorizationInvalidError(
                "submit authorization could not be consumed; it may have expired, "
                "been revoked, or been used"
            )

        attempt = self.repository.create_attempt(
            SubmissionAttempt(
                attempt_id=attempt_id,
                authorization_id=claimed.authorization_id,
                application_id=claimed.application_id,
                job_id=claimed.job_id,
                vendor=claimed.vendor,
                state_fingerprint=claimed.state_fingerprint,
                browser_session_id=claimed.browser_session_id,
                document_url_sha256=claimed.document_url_sha256,
                submit_selector=claimed.submit_selector,
                submit_control_sha256=claimed.submit_control_sha256,
                audit_run_id=claimed.audit_run_id,
                status=SubmissionAttemptStatus.EXECUTING,
                submit_invoked=False,
                started_at=started_at,
            )
        )
        if attempt is None:
            raise DuplicateSubmissionError(
                "another submission attempt acquired the application execution lock"
            )
        self.repository.persist_execution_claim()

        try:
            outcome = _sanitize_outcome(executor.execute(claimed, request.state))
        except Exception:
            outcome = SubmissionExecutionOutcome(
                status=SubmissionAttemptStatus.INDETERMINATE,
                submit_invoked=True,
                error_code="executor_exception",
                error_detail=(
                    "submission executor raised an exception after authorization was consumed; "
                    "manual reconciliation is required"
                ),
            )

        completed_at = datetime.now(UTC)
        finalized = self.repository.finalize_attempt(
            attempt.attempt_id,
            outcome=outcome,
            completed_at=completed_at,
        )
        if finalized is None:
            raise SubmissionGateError(f"submission attempt disappeared: {attempt.attempt_id}")
        self.repository.persist_execution_result()
        return finalized

    def _assert_no_blocking_attempt(self, application_id: str) -> None:
        blocking = self.repository.get_blocking_attempt(application_id)
        if blocking is None:
            return
        if blocking.status is SubmissionAttemptStatus.SUCCEEDED:
            raise DuplicateSubmissionError(
                f"application already has a successful submission: {application_id}"
            )
        raise DuplicateSubmissionError(
            "application already has an executing or indeterminate submission attempt: "
            f"{application_id}"
        )

    def _validate_authorization(
        self,
        authorization: SubmitAuthorization,
        state: PreparedSubmissionState,
        *,
        now: datetime,
    ) -> None:
        if authorization.status is not SubmissionAuthorizationStatus.ACTIVE:
            raise SubmissionAuthorizationInvalidError(
                f"submit authorization is {authorization.status.value}, not active"
            )
        if now >= _as_utc(authorization.expires_at):
            raise SubmissionAuthorizationInvalidError("submit authorization has expired")

        result = self.readiness.evaluate(state, now=now)
        if not result.ready:
            raise SubmissionNotReadyError(result)
        if result.state_fingerprint != authorization.state_fingerprint:
            raise SubmissionAuthorizationInvalidError(
                "prepared application state changed after submit authorization"
            )
        if state.application_id != authorization.application_id:
            raise SubmissionAuthorizationInvalidError("authorization application mismatch")
        if state.job_id != authorization.job_id:
            raise SubmissionAuthorizationInvalidError("authorization job mismatch")
        if state.vendor is not authorization.vendor:
            raise SubmissionAuthorizationInvalidError("authorization ATS/vendor mismatch")
        if state.audit_run_id != authorization.audit_run_id:
            raise SubmissionAuthorizationInvalidError("authorization audit context changed")
        if state.browser_session_id != authorization.browser_session_id:
            raise SubmissionAuthorizationInvalidError("authorized browser session changed")
        if state.document_url_sha256 != authorization.document_url_sha256:
            raise SubmissionAuthorizationInvalidError("authorized document identity changed")
        if state.submit_selector != authorization.submit_selector:
            raise SubmissionAuthorizationInvalidError("authorized submit selector changed")
        if state.submit_control_sha256 != authorization.submit_control_sha256:
            raise SubmissionAuthorizationInvalidError("authorized submit control changed")
        if state.prepared_payload_sha256 != authorization.prepared_payload_sha256:
            raise SubmissionAuthorizationInvalidError("prepared application payload changed")


def _sanitize_outcome(outcome: SubmissionExecutionOutcome) -> SubmissionExecutionOutcome:
    metadata: dict[str, str | int | float | bool | None] = {}
    for key, value in outcome.receipt_metadata.items():
        if _SENSITIVE_RECEIPT_KEY.search(key):
            metadata[key] = _OMITTED
            continue
        if isinstance(value, str):
            if _URL_KEY.search(key):
                metadata[key] = sanitize_url(value) or value
            else:
                metadata[key] = sanitize_text(value) or value
        else:
            metadata[key] = value

    return outcome.model_copy(
        update={
            "receipt_metadata": metadata,
            "error_detail": (
                "submission executor reported an error"
                if outcome.error_detail
                else None
            ),
        }
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
