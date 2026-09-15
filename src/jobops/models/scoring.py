from pydantic import BaseModel, Field

from jobops.models.candidate import CandidateProfile
from jobops.models.job import JobPosting


class ScoreRequest(BaseModel):
    candidate: CandidateProfile
    job: JobPosting


class ScoreBreakdown(BaseModel):
    overall: float = Field(ge=0, le=100)
    title_fit: float = Field(ge=0, le=1)
    required_skill_fit: float = Field(ge=0, le=1)
    preferred_skill_fit: float = Field(ge=0, le=1)
    experience_fit: float = Field(ge=0, le=1)
    compensation_fit: float = Field(ge=0, le=1)
    work_mode_fit: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)
