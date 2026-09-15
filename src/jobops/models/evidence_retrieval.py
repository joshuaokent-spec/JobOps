from pydantic import BaseModel, Field

from jobops.models.resume_evidence import ResumeEvidenceItem


class EvidenceRetrievalFeatures(BaseModel):
    lexical_fit: float = Field(ge=0, le=1)
    skill_fit: float = Field(ge=0, le=1)
    family_fit: float = Field(ge=0, le=1)
    specificity: float = Field(ge=0, le=1)
    semantic_similarity: float | None = Field(default=None, ge=-1, le=1)


class EvidenceRetrievalHit(BaseModel):
    evidence: ResumeEvidenceItem
    score: float = Field(ge=0, le=100)
    features: EvidenceRetrievalFeatures
    reasons: list[str] = Field(default_factory=list)


class EvidenceRetrievalResult(BaseModel):
    job_id: str
    family_id: str
    limit: int = Field(ge=1)
    candidates_considered: int = Field(ge=0)
    semantic_model: str | None = None
    hits: list[EvidenceRetrievalHit] = Field(default_factory=list)
