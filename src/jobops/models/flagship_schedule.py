from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ScheduledProfileRunStatus(StrEnum):
    SUCCEEDED = "succeeded"
    SKIPPED = "skipped"
    FAILED = "failed"


class ScheduledProfileRunResult(BaseModel):
    profile_id: str
    profile_name: str
    status: ScheduledProfileRunStatus
    run_id: str | None = None
    prepared_count: int = Field(default=0, ge=0)
    ready_count: int = Field(default=0, ge=0)
    review_required_count: int = Field(default=0, ge=0)
    error_code: str | None = None
    error: str | None = None


class ScheduledFlagshipBatchResult(BaseModel):
    started_at: datetime
    completed_at: datetime
    profiles_total: int = Field(ge=0)
    profiles_succeeded: int = Field(ge=0)
    profiles_skipped: int = Field(ge=0)
    profiles_failed: int = Field(ge=0)
    profile_results: list[ScheduledProfileRunResult] = Field(default_factory=list)
