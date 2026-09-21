from datetime import datetime

from pydantic import BaseModel, Field

from jobops.models.approval import ApprovalItem
from jobops.models.flagship_run import FlagshipReadiness


class FlagshipPreparedSnapshot(BaseModel):
    run_id: str
    job_id: str
    rank: int = Field(ge=1)
    score: float = Field(ge=0, le=100)
    resume_family_id: str
    resume_selection_score: float = Field(ge=0, le=100)
    resume_low_confidence: bool = False
    readiness: FlagshipReadiness
    readiness_reasons: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class FlagshipReadinessSummary(BaseModel):
    run_id: str
    profile_id: str
    candidate_id: str
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
    prepared_jobs: list[FlagshipPreparedSnapshot] = Field(default_factory=list)


class FlagshipExceptionInbox(BaseModel):
    run_id: str
    profile_id: str
    candidate_id: str
    completed_at: datetime
    review_required_jobs: list[FlagshipPreparedSnapshot] = Field(default_factory=list)
    pending_approvals: list[ApprovalItem] = Field(default_factory=list)
    total_exceptions: int = Field(ge=0)
