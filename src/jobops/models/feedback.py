from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class FeedbackEventType(StrEnum):
    JOB_VIEWED = "job_viewed"
    JOB_SAVED = "job_saved"
    JOB_SKIPPED = "job_skipped"
    INTEREST_MARKED = "interest_marked"
    STRONG_INTEREST_MARKED = "strong_interest_marked"
    APPLICATION_STARTED = "application_started"
    APPLICATION_ABANDONED = "application_abandoned"
    APPLICATION_PREPARED = "application_prepared"
    APPLICATION_SUBMITTED = "application_submitted"
    APPLICATION_WITHDRAWN = "application_withdrawn"
    RECRUITER_RESPONSE = "recruiter_response"
    RECRUITER_SCREEN = "recruiter_screen"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    INTERVIEW_COMPLETED = "interview_completed"
    REJECTED = "rejected"
    OFFER_RECEIVED = "offer_received"
    OFFER_ACCEPTED = "offer_accepted"
    OFFER_DECLINED = "offer_declined"
    RANKING_FEEDBACK_POSITIVE = "ranking_feedback_positive"
    RANKING_FEEDBACK_NEGATIVE = "ranking_feedback_negative"
    RESUME_CHOICE_ACCEPTED = "resume_choice_accepted"
    RESUME_CHOICE_OVERRIDDEN = "resume_choice_overridden"


class FeedbackEventSource(StrEnum):
    USER = "user"
    SYSTEM = "system"
    BROWSER = "browser"
    ATS = "ats"
    IMPORT = "import"


FeedbackMetadataValue = str | int | float | bool | None

_BLOCKED_METADATA_FRAGMENTS = (
    "answer",
    "response_body",
    "message",
    "email",
    "phone",
    "address",
    "password",
    "token",
    "cookie",
    "session",
    "secret",
    "api_key",
    "ssn",
    "social_security",
    "demographic",
    "eeo",
    "disability",
    "work_authorization",
    "sponsorship_answer",
    "legal_identification",
)


class FeedbackEventCreate(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: FeedbackEventType
    job_id: str = Field(min_length=1, max_length=255)
    application_id: str | None = Field(default=None, max_length=255)
    candidate_id: str | None = Field(default=None, max_length=255)
    resume_family_id: str | None = Field(default=None, max_length=100)
    occurred_at: datetime
    source: FeedbackEventSource
    actor: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=255)
    schema_version: int = Field(default=1, ge=1, le=100)
    metadata: dict[str, FeedbackMetadataValue] = Field(default_factory=dict)
    model_name: str | None = Field(default=None, max_length=200)
    model_version: str | None = Field(default=None, max_length=200)
    experiment_id: str | None = Field(default=None, max_length=200)

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(
        cls,
        value: dict[str, FeedbackMetadataValue],
    ) -> dict[str, FeedbackMetadataValue]:
        if len(value) > 32:
            raise ValueError("feedback metadata may contain at most 32 keys")
        sanitized: dict[str, FeedbackMetadataValue] = {}
        for raw_key, item in value.items():
            key = raw_key.strip()
            if not key:
                raise ValueError("feedback metadata keys cannot be blank")
            normalized = key.casefold().replace("-", "_").replace(" ", "_")
            if any(fragment in normalized for fragment in _BLOCKED_METADATA_FRAGMENTS):
                raise ValueError(f"feedback metadata key is not allowed: {raw_key}")
            if isinstance(item, str) and len(item) > 500:
                raise ValueError(f"feedback metadata string is too long: {raw_key}")
            sanitized[key] = item
        return sanitized

    @model_validator(mode="after")
    def _validate_model_context(self) -> "FeedbackEventCreate":
        if self.model_version and not self.model_name:
            raise ValueError("model_version requires model_name")
        return self


class FeedbackEvent(BaseModel):
    event_id: str
    event_type: FeedbackEventType
    job_id: str
    application_id: str | None = None
    candidate_id: str | None = None
    resume_family_id: str | None = None
    occurred_at: datetime
    observed_at: datetime
    source: FeedbackEventSource
    actor: str
    idempotency_key: str
    schema_version: int
    metadata: dict[str, FeedbackMetadataValue] = Field(default_factory=dict)
    model_name: str | None = None
    model_version: str | None = None
    experiment_id: str | None = None

    @model_validator(mode="after")
    def _validate_temporal_order(self) -> "FeedbackEvent":
        occurred = _as_utc(self.occurred_at)
        observed = _as_utc(self.observed_at)
        if occurred > observed:
            raise ValueError("occurred_at cannot be later than observed_at")
        return self


class FeedbackEventPage(BaseModel):
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    items: list[FeedbackEvent] = Field(default_factory=list)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
