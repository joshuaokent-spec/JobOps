from pydantic import BaseModel, Field

from jobops.models.candidate import CandidateProfile
from jobops.models.job import JobPosting, WorkMode
from jobops.models.scoring import ScoreBreakdown


class JobSearchFilters(BaseModel):
    title: str | None = None
    company: str | None = None
    location: str | None = None
    work_mode: WorkMode | None = None
    min_salary: int | None = Field(default=None, ge=0)
    source: str | None = None
    active: bool | None = True


class JobPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[JobPosting]


class RankJobsRequest(BaseModel):
    candidate: CandidateProfile
    filters: JobSearchFilters = Field(default_factory=JobSearchFilters)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    candidate_pool: int = Field(default=500, ge=1, le=2000)


class RankedJob(BaseModel):
    job: JobPosting
    score: ScoreBreakdown


class RankedJobPage(BaseModel):
    total_available: int
    total_considered: int
    limit: int
    offset: int
    items: list[RankedJob]
