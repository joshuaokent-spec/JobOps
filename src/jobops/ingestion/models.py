from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SourceJobPosting(BaseModel):
    """Source-agnostic contract emitted by ATS adapters before normalization."""

    source: str = Field(min_length=1)
    source_job_id: str = Field(min_length=1)
    company: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""
    location: str | None = None
    workplace_type: str | None = None
    employment_type: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_interval: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    source_url: str | None = None
    apply_url: str | None = None
    source_updated_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
