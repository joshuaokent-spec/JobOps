from enum import StrEnum

from pydantic import BaseModel, Field

from jobops.models.evidence_retrieval import EvidenceRetrievalResult
from jobops.models.narrative_draft import NarrativeDraftResult


class VerificationStatus(StrEnum):
    PASS = "pass"
    REVIEW = "review"
    BLOCK = "block"


class VerificationSeverity(StrEnum):
    REVIEW = "review"
    BLOCK = "block"


class VerificationFinding(BaseModel):
    code: str = Field(min_length=1)
    severity: VerificationSeverity
    message: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)


class DraftVerificationRequest(BaseModel):
    draft: NarrativeDraftResult
    evidence: EvidenceRetrievalResult


class DraftVerificationResult(BaseModel):
    status: VerificationStatus
    findings: list[VerificationFinding] = Field(default_factory=list)
    checked_evidence_ids: list[str] = Field(default_factory=list)
    semantic_checked: bool = False
    requires_human_review: bool = True
