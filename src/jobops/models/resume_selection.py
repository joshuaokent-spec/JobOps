from pydantic import BaseModel, Field


class ResumeFamilyFeatures(BaseModel):
    title_role_fit: float = Field(ge=0, le=1)
    priority_skill_fit: float = Field(ge=0, le=1)
    evidence_depth: float = Field(ge=0, le=1)
    evidence_skill_coverage: float = Field(ge=0, le=1)


class ResumeFamilyScore(BaseModel):
    family_id: str
    family_name: str
    score: float = Field(ge=0, le=100)
    features: ResumeFamilyFeatures
    evidence_ids: list[str]
    reasons: list[str]


class ResumeFamilySelection(BaseModel):
    chosen_family_id: str
    chosen_score: float = Field(ge=0, le=100)
    minimum_confidence: float = Field(ge=0, le=1)
    low_confidence: bool
    used_fallback: bool = False
    candidates: list[ResumeFamilyScore]
