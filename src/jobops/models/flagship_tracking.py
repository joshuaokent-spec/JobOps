from datetime import datetime

from pydantic import BaseModel, Field


class FlagshipTrackingSummary(BaseModel):
    profile_id: str
    latest_run_id: str
    previous_run_id: str | None = None
    has_previous_run: bool = False
    latest_completed_at: datetime
    previous_completed_at: datetime | None = None
    prepared_count: int = Field(ge=0)
    ready_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    new_job_ids: list[str] = Field(default_factory=list)
    no_longer_prepared_job_ids: list[str] = Field(default_factory=list)
    newly_ready_job_ids: list[str] = Field(default_factory=list)
    newly_review_required_job_ids: list[str] = Field(default_factory=list)
    readiness_changed_job_ids: list[str] = Field(default_factory=list)
