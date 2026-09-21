from enum import StrEnum

from pydantic import BaseModel, Field

from jobops.models.browser_audit import BrowserAuditVendor
from jobops.models.form_mapping import ApplicationFieldSemantic


class ApplicationPreparationStatus(StrEnum):
    PREPARED = "prepared"
    BLOCKED = "blocked"
    UNSUPPORTED = "unsupported"


class ApplicationPreparationBlocker(StrEnum):
    JOB_NOT_IN_LATEST_RUN = "job_not_in_latest_run"
    FLAGSHIP_REVIEW_REQUIRED = "flagship_review_required"
    MISSING_VERIFIED_FACT = "missing_verified_fact"
    MISSING_APPROVED_REVIEW = "missing_approved_review"
    AMBIGUOUS_FIELD = "ambiguous_field"
    UNKNOWN_FIELD = "unknown_field"
    UNSUPPORTED_CONTROL = "unsupported_control"
    REQUIRED_FIELD_UNRESOLVED = "required_field_unresolved"
    FILE_NOT_AVAILABLE = "file_not_available"
    FIELD_WRITE_FAILED = "field_write_failed"
    ATS_DETECTION_FAILED = "ats_detection_failed"
    SUBMIT_CONTROL_NOT_UNIQUE = "submit_control_not_unique"
    WORKDAY_STATEFUL_PROGRESSION = "workday_stateful_progression"
    UNSUPPORTED_VENDOR = "unsupported_vendor"


class ApplicationFieldValueSource(StrEnum):
    VERIFIED_FACT = "verified_fact"
    APPROVED_REVIEW = "approved_review"
    APPROVED_FILE = "approved_file"


class ApplicationFieldWrite(BaseModel):
    selector: str
    semantic: ApplicationFieldSemantic
    source: ApplicationFieldValueSource
    required: bool = False


class ApplicationPreparationBlock(BaseModel):
    code: ApplicationPreparationBlocker
    selector: str | None = None
    semantic: ApplicationFieldSemantic | None = None
    reason: str


class ApplicationPreparationResult(BaseModel):
    application_id: str
    job_id: str
    vendor: BrowserAuditVendor
    status: ApplicationPreparationStatus
    filled_fields: int = Field(default=0, ge=0)
    writes: list[ApplicationFieldWrite] = Field(default_factory=list)
    blockers: list[ApplicationPreparationBlock] = Field(default_factory=list)
    submit_selector: str | None = None
    submit_control_count: int = Field(default=0, ge=0)
    prepared_payload_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    submission_allowed: bool = False
