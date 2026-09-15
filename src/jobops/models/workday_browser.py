from enum import StrEnum

from pydantic import BaseModel, Field

from jobops.models.browser import BrowserPageActionDescriptor, BrowserPageSnapshot
from jobops.models.form_mapping import SemanticPageMapping, SemanticPreparationPlan


class WorkdayStepCategory(StrEnum):
    ACCOUNT_ACCESS = "account_access"
    RESUME = "resume"
    CONTACT_INFORMATION = "contact_information"
    EXPERIENCE = "experience"
    APPLICATION_QUESTIONS = "application_questions"
    VOLUNTARY_DISCLOSURES = "voluntary_disclosures"
    TERMS_CONSENT = "terms_consent"
    FINAL_REVIEW = "final_review"
    UNKNOWN = "unknown"


class WorkdayBlockedOperation(StrEnum):
    NEXT = "next"
    SAVE_FOR_LATER = "save_for_later"
    SIGN_IN = "sign_in"
    CREATE_ACCOUNT = "create_account"
    APPLY_WITH_LINKEDIN = "apply_with_linkedin"
    SUBMIT = "submit"
    OTHER_PROGRESSION = "other_progression"


class WorkdayDetection(BaseModel):
    detected: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    document_index: int = Field(ge=0)
    document_url: str
    embedded: bool = False
    tenant: str | None = None
    site: str | None = None
    locale: str | None = None
    requisition_id: str | None = None
    source: str | None = None


class WorkdayBlockedAction(BaseModel):
    operation: WorkdayBlockedOperation
    control: BrowserPageActionDescriptor
    reason: str


class WorkdayWizardStep(BaseModel):
    category: WorkdayStepCategory
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class WorkdayPreparationResult(BaseModel):
    detection: WorkdayDetection
    step: WorkdayWizardStep
    page: BrowserPageSnapshot
    semantic_mapping: SemanticPageMapping
    preparation_plan: SemanticPreparationPlan
    blocked_actions: list[WorkdayBlockedAction] = Field(default_factory=list)
    progression_allowed: bool = False
    live_writes_allowed: bool = False
    submission_allowed: bool = False
