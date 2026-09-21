from datetime import datetime

from pydantic import BaseModel, Field

from jobops.models.application_question import ReviewBand
from jobops.models.flagship_run import FlagshipReadiness
from jobops.models.job import WorkMode
from jobops.models.search_profile import SearchProfile


class CommandCenterJob(BaseModel):
    run_id: str
    job_id: str
    rank: int = Field(ge=1)
    score: float = Field(ge=0, le=100)
    readiness: FlagshipReadiness
    readiness_reasons: list[str] = Field(default_factory=list)
    resume_family_id: str
    resume_selection_score: float = Field(ge=0, le=100)
    title: str
    company: str
    location: str | None = None
    work_mode: WorkMode
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    source: str | None = None
    source_url: str | None = None
    apply_url: str | None = None
    active: bool = True


class CommandCenterApproval(BaseModel):
    approval_id: str
    job_id: str
    question: str
    review_band: ReviewBand
    reason: str
    created_at: datetime


class CommandCenterRunMetrics(BaseModel):
    run_id: str
    started_at: datetime
    completed_at: datetime
    total_examined: int = Field(ge=0)
    total_hard_eligible: int = Field(ge=0)
    total_hard_rejected: int = Field(ge=0)
    total_fit_eligible: int = Field(ge=0)
    total_fit_rejected: int = Field(ge=0)
    prepared_count: int = Field(ge=0)
    ready_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    rejection_summary: dict[str, int] = Field(default_factory=dict)


class CommandCenterActions(BaseModel):
    profile: str
    run: str
    readiness: str
    exceptions: str
    approvals: str
    api_docs: str = "/docs"


class CommandCenterView(BaseModel):
    profile: SearchProfile
    has_run: bool
    metrics: CommandCenterRunMetrics | None = None
    ready_jobs: list[CommandCenterJob] = Field(default_factory=list)
    review_required_jobs: list[CommandCenterJob] = Field(default_factory=list)
    pending_approval_count: int = Field(default=0, ge=0)
    pending_approvals: list[CommandCenterApproval] = Field(default_factory=list)
    missing_job_ids: list[str] = Field(default_factory=list)
    actions: CommandCenterActions
