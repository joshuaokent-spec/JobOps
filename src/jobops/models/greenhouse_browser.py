from pydantic import BaseModel, Field

from jobops.models.browser import BrowserPageSnapshot
from jobops.models.form_mapping import SemanticPageMapping, SemanticPreparationPlan


class GreenhouseDetection(BaseModel):
    detected: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    document_index: int = Field(ge=0)
    document_url: str
    embedded: bool = False
    job_id: str | None = None
    source_token: str | None = None
    board_token: str | None = None


class GreenhousePreparationResult(BaseModel):
    detection: GreenhouseDetection
    page: BrowserPageSnapshot
    semantic_mapping: SemanticPageMapping
    preparation_plan: SemanticPreparationPlan
    submission_allowed: bool = False
