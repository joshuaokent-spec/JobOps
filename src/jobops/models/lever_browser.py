from pydantic import BaseModel, Field

from jobops.models.browser import BrowserPageSnapshot
from jobops.models.form_mapping import SemanticPageMapping, SemanticPreparationPlan


class LeverDetection(BaseModel):
    detected: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    document_index: int = Field(ge=0)
    document_url: str
    embedded: bool = False
    site: str | None = None
    posting_id: str | None = None
    source_tokens: list[str] = Field(default_factory=list)
    origin: str | None = None
    apply_page: bool = False


class LeverPreparationResult(BaseModel):
    detection: LeverDetection
    page: BrowserPageSnapshot
    semantic_mapping: SemanticPageMapping
    preparation_plan: SemanticPreparationPlan
    submission_allowed: bool = False
