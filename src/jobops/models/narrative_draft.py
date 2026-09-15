from pydantic import BaseModel, Field, field_validator

from jobops.models.application_question import (
    HandlingRoute,
    QuestionClassification,
    ReviewBand,
)
from jobops.models.evidence_retrieval import EvidenceRetrievalResult
from jobops.models.job import JobPosting


class NarrativeDraftRequest(BaseModel):
    classification: QuestionClassification
    job: JobPosting
    family_id: str = Field(min_length=1)
    evidence: EvidenceRetrievalResult
    word_limit: int = Field(default=180, ge=10, le=500)
    tone: str = Field(default="professional, concise, specific", min_length=1, max_length=200)


class NarrativeDraftResult(BaseModel):
    question: str
    job_id: str
    family_id: str
    draft: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    provider: str
    model: str
    word_count: int = Field(ge=1)
    review_band: ReviewBand
    route: HandlingRoute
    requires_human_review: bool = True

    @field_validator("evidence_ids")
    @classmethod
    def _deduplicate_evidence_ids(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))
