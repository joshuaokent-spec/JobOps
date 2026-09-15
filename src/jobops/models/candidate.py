from enum import StrEnum

from pydantic import BaseModel, Field


class FactRisk(StrEnum):
    """How consequential it is to answer a question incorrectly."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CandidateFact(BaseModel):
    key: str = Field(min_length=1)
    value: str | int | float | bool | list[str]
    evidence: list[str] = Field(default_factory=list)
    verified: bool = False
    risk: FactRisk = FactRisk.LOW


class CandidateProfile(BaseModel):
    candidate_id: str = "local-candidate"
    target_roles: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    years_experience: float = Field(default=0, ge=0)
    preferred_work_modes: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    minimum_salary: int | None = Field(default=None, ge=0)
    facts: list[CandidateFact] = Field(default_factory=list)
