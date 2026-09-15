from enum import StrEnum

from pydantic import BaseModel, Field

from jobops.models.application_question import HandlingRoute, QuestionCategory, ReviewBand
from jobops.models.browser import BrowserFieldDescriptor, BrowserPageSnapshot


class ApplicationFieldSemantic(StrEnum):
    FIRST_NAME = "first_name"
    LAST_NAME = "last_name"
    FULL_NAME = "full_name"
    EMAIL = "email"
    PHONE = "phone"
    STREET_ADDRESS = "street_address"
    CITY = "city"
    REGION = "region"
    POSTAL_CODE = "postal_code"
    COUNTRY = "country"
    LINKEDIN_URL = "linkedin_url"
    GITHUB_URL = "github_url"
    PORTFOLIO_URL = "portfolio_url"
    PERSONAL_WEBSITE = "personal_website"
    RESUME = "resume"
    COVER_LETTER = "cover_letter"
    SALARY_EXPECTATION = "salary_expectation"
    RELOCATION = "relocation"
    WORK_MODE = "work_mode"
    TRAVEL = "travel"
    START_DATE = "start_date"
    WORK_AUTHORIZATION = "work_authorization"
    SPONSORSHIP = "sponsorship"
    PRIOR_EMPLOYMENT = "prior_employment"
    CERTIFICATIONS = "certifications"
    EDUCATION = "education"
    SECURITY_CLEARANCE = "security_clearance"
    NARRATIVE_QUESTION = "narrative_question"
    DEMOGRAPHIC_SELF_ID = "demographic_self_identification"
    SUBMIT_CONTROL = "submit_control"
    UNKNOWN = "unknown"


class MappingSource(StrEnum):
    DETERMINISTIC = "deterministic"
    MODEL_ASSISTED = "model_assisted"
    UNRESOLVED = "unresolved"


class SemanticPreparationOperation(StrEnum):
    RESOLVE_FACT = "resolve_fact"
    DRAFT_WITH_REVIEW = "draft_with_review"
    HUMAN_REVIEW = "human_review"
    ESCALATE = "escalate"
    BLOCKED_SUBMIT = "blocked_submit"


class SemanticFieldMapping(BaseModel):
    field: BrowserFieldDescriptor
    semantic: ApplicationFieldSemantic
    confidence: float = Field(ge=0.0, le=1.0)
    source: MappingSource
    matched_signals: list[str] = Field(default_factory=list)
    fact_key: str | None = None
    question_text: str | None = None
    question_category: QuestionCategory
    route: HandlingRoute
    review_band: ReviewBand
    requires_human_review: bool
    ambiguous: bool = False


class SemanticPageMapping(BaseModel):
    page: BrowserPageSnapshot
    mappings: list[SemanticFieldMapping] = Field(default_factory=list)
    mapped_fields: int = Field(ge=0)
    unresolved_fields: int = Field(ge=0)
    sensitive_fields: int = Field(ge=0)
    submission_allowed: bool = False


class SemanticPreparationAction(BaseModel):
    mapping: SemanticFieldMapping
    operation: SemanticPreparationOperation
    reason: str


class SemanticPreparationPlan(BaseModel):
    url: str
    actions: list[SemanticPreparationAction] = Field(default_factory=list)
    fact_resolution_fields: int = Field(ge=0)
    review_fields: int = Field(ge=0)
    unresolved_fields: int = Field(ge=0)
    submit_controls: int = Field(ge=0)
    submission_allowed: bool = False
