from enum import StrEnum

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
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    minimum_years_experience: float | None = Field(default=None, ge=0)
    source: str | None = None
    source_url: str | None = None
