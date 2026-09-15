from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from jobops.models.application_question import HandlingRoute, QuestionCategory, ReviewBand
from jobops.models.draft_verification import VerificationFinding, VerificationStatus


class ApprovalReason(StrEnum):
    NARRATIVE_DRAFT = "narrative_draft"
    FACTUAL_REVIEW = "factual_review"
    PREFERENCE = "preference"
    LEGAL_SENSITIVE = "legal_sensitive"
    VERIFIER_REVIEW = "verifier_review"
    ESCALATED = "escalated"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUIRED = "revision_required"


class ApprovalCreate(BaseModel):
    approval_id: str = Field(default_factory=lambda: str(uuid4()))
    job_id: str = Field(min_length=1)
    family_id: str | None = None
    question: str = Field(min_length=1)
    category: QuestionCategory
    route: HandlingRoute
    review_band: ReviewBand
    reason: ApprovalReason
    proposed_answer: str | None = None
    verification_status: VerificationStatus | None = None
    verification_findings: list[VerificationFinding] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_verification_state(self) -> "ApprovalCreate":
        if self.verification_status is VerificationStatus.BLOCK:
            raise ValueError("blocked verification results cannot enter the approval queue")
        return self


class ApprovalDecision(BaseModel):
    status: ApprovalStatus
    reviewer: str = Field(min_length=1, max_length=200)
    note: str = Field(min_length=1, max_length=2000)
    edited_answer: str | None = None

    @model_validator(mode="after")
    def _validate_decision(self) -> "ApprovalDecision":
        if self.status is ApprovalStatus.PENDING:
            raise ValueError("pending is not a review decision")
        if self.edited_answer is not None and not self.edited_answer.strip():
            raise ValueError("edited_answer cannot be blank")
        return self


class ApprovalItem(BaseModel):
    approval_id: str
    job_id: str
    family_id: str | None = None
    question: str
    category: QuestionCategory
    route: HandlingRoute
    review_band: ReviewBand
    reason: ApprovalReason
    status: ApprovalStatus
    proposed_answer: str | None = None
    edited_answer: str | None = None
    final_answer: str | None = None
    verification_status: VerificationStatus | None = None
    verification_findings: list[VerificationFinding] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    reviewer: str | None = None
    decision_note: str | None = None
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None = None
    approved_for_preparation: bool = False
    submitted: bool = False


class ApprovalPage(BaseModel):
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    items: list[ApprovalItem] = Field(default_factory=list)
