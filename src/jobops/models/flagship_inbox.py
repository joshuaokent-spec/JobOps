from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from jobops.models.approval import ApprovalItem
from jobops.models.flagship_run import FlagshipReadiness


class FlagshipExceptionKind(StrEnum):
    READINESS = "readiness"
    APPROVAL = "approval"


class FlagshipRunJobSnapshot(BaseModel):
    run_id: str
    job_id: str
    rank: int = Field(ge=1)
    company: str
    title: str
    score: float = Field(ge=0, le=100)
    family_id: str
    family_score: float = Field(ge=0, le=100)
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
    jobs: list[FlagshipRunJobSnapshot] = Field(default_factory=list)


class FlagshipExceptionItem(BaseModel):
    kind: FlagshipExceptionKind
    job_id: str
    company: str
    title: str
    rank: int = Field(ge=1)
    reasons: list[str] = Field(default_factory=list)
    approval: ApprovalItem | None = None


class FlagshipExceptionInbox(BaseModel):
    profile_id: str
    run_id: str
    run_completed_at: datetime
    ready_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    pending_approval_count: int = Field(ge=0)
    total_exceptions: int = Field(ge=0)
    items: list[FlagshipExceptionItem] = Field(default_factory=list)
