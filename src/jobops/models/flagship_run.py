from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from jobops.models.candidate import CandidateProfile
from jobops.models.discovery import DiscoveryRunRequest, DiscoveryRunResult
from jobops.models.evidence_retrieval import EvidenceRetrievalResult
from jobops.models.job import JobPosting
from jobops.models.resume_evidence import ResumeEvidenceBase
from jobops.models.resume_selection import ResumeFamilySelection
from jobops.models.scoring import ScoreBreakdown


class FlagshipReadiness(StrEnum):
    READY = "ready"
    REVIEW_REQUIRED = "review_required"


class FlagshipRunRequest(BaseModel):
    candidate: CandidateProfile
    resume_evidence: ResumeEvidenceBase
    discovery: DiscoveryRunRequest = Field(default_factory=DiscoveryRunRequest)
    candidate_pool: int = Field(default=1000, ge=1, le=5000)
    max_jobs: int = Field(default=25, ge=1, le=100)
    evidence_limit: int = Field(default=6, ge=1, le=20)
    resume_minimum_confidence: float = Field(default=0.35, ge=0.0, le=1.0)
    fallback_family_id: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def _validate_candidate_ownership(self) -> "FlagshipRunRequest":
        if self.resume_evidence.candidate_id != self.candidate.candidate_id:
            raise ValueError("resume evidence does not match candidate owner")
        return self


class FlagshipPreparedJob(BaseModel):
    rank: int = Field(ge=1)
    job: JobPosting
    score: ScoreBreakdown
    resume_selection: ResumeFamilySelection
    evidence: EvidenceRetrievalResult
    readiness: FlagshipReadiness
    readiness_reasons: list[str] = Field(default_factory=list)


class FlagshipRunResult(BaseModel):
    profile_id: str
    started_at: datetime
    completed_at: datetime
    discovery: DiscoveryRunResult
    total_examined: int = Field(ge=0)
    total_hard_eligible: int = Field(ge=0)
    total_hard_rejected: int = Field(ge=0)
    total_fit_eligible: int = Field(ge=0)
    total_fit_rejected: int = Field(ge=0)
    prepared_count: int = Field(ge=0)
    ready_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    rejection_summary: dict[str, int] = Field(default_factory=dict)
    prepared_jobs: list[FlagshipPreparedJob] = Field(default_factory=list)
