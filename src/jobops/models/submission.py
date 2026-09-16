from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from jobops.models.browser_audit import BrowserAuditVendor

_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class SubmissionReadinessBlocker(StrEnum):
    MISSING_AUDIT_CONTEXT = "missing_audit_context"
    UNRESOLVED_REQUIRED_FIELDS = "unresolved_required_fields"
    AMBIGUOUS_MAPPINGS = "ambiguous_mappings"
    BLOCKED_VERIFICATION = "blocked_verification"
    PENDING_REVIEW = "pending_review"
    UNANSWERED_RED_FIELDS = "unanswered_red_fields"
    UNCONFIRMED_CONSENT = "unconfirmed_consent"
    SUBMIT_CONTROL_NOT_UNIQUE = "submit_control_not_unique"
    SUBMIT_CONTROL_DISABLED = "submit_control_disabled"
    ATS_CONTEXT_MISMATCH = "ats_context_mismatch"
    BROWSER_STATE_MISMATCH = "browser_state_mismatch"
    AUDIT_TOO_OLD = "audit_too_old"


class SubmissionAuthorizationStatus(StrEnum):
    ACTIVE = "active"
    CONSUMED = "consumed"
    REVOKED = "revoked"
    EXPIRED = "expired"


class SubmissionAttemptStatus(StrEnum):
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INDETERMINATE = "indeterminate"


class PreparedSubmissionState(BaseModel):
    application_id: str = Field(min_length=1, max_length=255)
    job_id: str = Field(min_length=1, max_length=255)
    vendor: BrowserAuditVendor
    prepared_payload_sha256: str = Field(pattern=_SHA256_PATTERN)
    audit_run_id: str | None = Field(default=None, max_length=255)
    audit_created_at: datetime | None = None
    browser_session_id: str | None = Field(default=None, min_length=1, max_length=255)
    document_url_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    submit_selector: str = Field(min_length=1, max_length=2000)
    submit_control_sha256: str = Field(pattern=_SHA256_PATTERN)
    required_unresolved: int = Field(default=0, ge=0)
    ambiguous_mappings: int = Field(default=0, ge=0)
    blocked_verification: int = Field(default=0, ge=0)
    pending_review: int = Field(default=0, ge=0)
    unanswered_red: int = Field(default=0, ge=0)
    unconfirmed_consent: int = Field(default=0, ge=0)
    submit_control_count: int = Field(default=1, ge=0)
    submit_control_enabled: bool = True
    ats_context_matches: bool = True
    browser_state_matches: bool = True


class SubmissionReadinessResult(BaseModel):
    application_id: str
    job_id: str
    state_fingerprint: str = Field(pattern=_SHA256_PATTERN)
    ready: bool
    blockers: list[SubmissionReadinessBlocker] = Field(default_factory=list)
    evaluated_at: datetime


class SubmitAuthorizationCreate(BaseModel):
    state: PreparedSubmissionState
    authorized_by: str = Field(min_length=1, max_length=200)
    note: str = Field(min_length=1, max_length=2000)
    ttl_seconds: int = Field(default=300, ge=30, le=900)


class SubmitAuthorizationRevoke(BaseModel):
    revoked_by: str = Field(min_length=1, max_length=200)
    note: str = Field(min_length=1, max_length=2000)


class SubmitAuthorization(BaseModel):
    authorization_id: str = Field(default_factory=lambda: str(uuid4()))
    application_id: str
    job_id: str
    vendor: BrowserAuditVendor
    state_fingerprint: str = Field(pattern=_SHA256_PATTERN)
    prepared_payload_sha256: str = Field(pattern=_SHA256_PATTERN)
    audit_run_id: str
    browser_session_id: str
    document_url_sha256: str = Field(pattern=_SHA256_PATTERN)
    submit_selector: str
    submit_control_sha256: str = Field(pattern=_SHA256_PATTERN)
    authorized_by: str
    note: str
    status: SubmissionAuthorizationStatus = SubmissionAuthorizationStatus.ACTIVE
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None
    revoked_at: datetime | None = None
    revoked_by: str | None = None
    revoke_note: str | None = None
    attempt_id: str | None = None


class SubmissionExecutionRequest(BaseModel):
    authorization_id: str = Field(min_length=1)
    state: PreparedSubmissionState


class SubmissionExecutionOutcome(BaseModel):
    status: SubmissionAttemptStatus
    submit_invoked: bool
    receipt_metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    error_code: str | None = Field(default=None, max_length=100)
    error_detail: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _validate_outcome(self) -> "SubmissionExecutionOutcome":
        if self.status is SubmissionAttemptStatus.SUCCEEDED and not self.submit_invoked:
            raise ValueError("successful submission outcome must have invoked submit")
        if self.status is SubmissionAttemptStatus.EXECUTING:
            raise ValueError("executor outcome cannot remain executing")
        return self


class SubmissionAttempt(BaseModel):
    attempt_id: str = Field(default_factory=lambda: str(uuid4()))
    authorization_id: str
    application_id: str
    job_id: str
    vendor: BrowserAuditVendor
    state_fingerprint: str = Field(pattern=_SHA256_PATTERN)
    browser_session_id: str
    document_url_sha256: str = Field(pattern=_SHA256_PATTERN)
    submit_selector: str
    submit_control_sha256: str = Field(pattern=_SHA256_PATTERN)
    audit_run_id: str
    status: SubmissionAttemptStatus
    submit_invoked: bool = False
    receipt_metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    error_code: str | None = None
    error_detail: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
