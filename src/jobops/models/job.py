from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class WorkMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class JobPosting(BaseModel):
    job_id: str
    company: str
    title: str
    description: str = ""
    location: str | None = None
    work_mode: WorkMode = WorkMode.UNKNOWN
    employment_type: str | None = None
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    salary_currency: str | None = None
    salary_interval: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    minimum_years_experience: float | None = Field(default=None, ge=0)
    source: str | None = None
    source_job_id: str | None = None
    source_url: str | None = None
    apply_url: str | None = None
    source_updated_at: datetime | None = None
    dedupe_key: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    active: bool = True
