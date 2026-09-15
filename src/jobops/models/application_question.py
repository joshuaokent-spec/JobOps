from enum import StrEnum

from pydantic import BaseModel, Field

from jobops.models.candidate import FactRisk


class QuestionCategory(StrEnum):
    FACTUAL = "factual"
    NUMERICAL = "numerical"
    PREFERENCE = "preference"
    NARRATIVE = "narrative"
    LEGAL_SENSITIVE = "legal_sensitive"
    UNKNOWN = "unknown"


class HandlingRoute(StrEnum):
    AUTO_FILL = "auto_fill"
    CALCULATE = "calculate"
    DRAFT_WITH_REVIEW = "draft_with_review"
    HUMAN_REVIEW = "human_review"
    ESCALATE = "escalate"


class ReviewBand(StrEnum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class ReviewPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class QuestionClassification(BaseModel):
    question: str = Field(min_length=1)
    category: QuestionCategory
    route: HandlingRoute
    review_band: ReviewBand
    risk: FactRisk
    confidence: float = Field(ge=0, le=1)
    priority: ReviewPriority
    requires_human_review: bool
    matched_fact_key: str | None = None
    fact_found: bool = False
    fact_verified: bool = False
    reasons: list[str] = Field(default_factory=list)
