from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from jobops.models.candidate import CandidateProfile
from jobops.models.job import JobPosting, WorkMode
from jobops.models.scoring import ScoreBreakdown


class SalaryFloorPolicy(StrEnum):
    MINIMUM_OFFERED = "minimum_offered"
    RANGE_CAN_REACH = "range_can_reach"


class UnknownCompensationPolicy(StrEnum):
    EXCLUDE = "exclude"
    ALLOW = "allow"


class SearchProfile(BaseModel):
    profile_id: str = Field(min_length=1, max_length=100)
    candidate_id: str = Field(default="local-candidate", min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=200)
    role_queries: list[str] = Field(default_factory=list)
    required_keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    allowed_work_modes: list[WorkMode] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    employment_types: list[str] = Field(default_factory=list)
    minimum_salary: int | None = Field(default=None, ge=0)
    salary_currency: str = Field(default="USD", min_length=3, max_length=3)
    salary_floor_policy: SalaryFloorPolicy = SalaryFloorPolicy.MINIMUM_OFFERED
    unknown_compensation_policy: UnknownCompensationPolicy = (
        UnknownCompensationPolicy.EXCLUDE
    )
    excluded_companies: list[str] = Field(default_factory=list)
    allowed_sources: list[str] = Field(default_factory=list)
    minimum_fit_score: float | None = Field(default=None, ge=0.0, le=100.0)
    active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator(
        "role_queries",
        "required_keywords",
        "excluded_keywords",
        "locations",
        "employment_types",
        "excluded_companies",
        "allowed_sources",
    )
    @classmethod
    def _normalize_string_lists(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            clean = " ".join(value.split()).strip()
            if not clean:
                continue
            key = clean.casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(clean)
        return result

    @field_validator("allowed_work_modes")
    @classmethod
    def _deduplicate_work_modes(cls, values: list[WorkMode]) -> list[WorkMode]:
        return list(dict.fromkeys(values))

    @field_validator("salary_currency")
    @classmethod
    def _normalize_currency(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _validate_keyword_overlap(self) -> "SearchProfile":
        required = {value.casefold() for value in self.required_keywords}
        excluded = {value.casefold() for value in self.excluded_keywords}
        overlap = required & excluded
        if overlap:
            values = ", ".join(sorted(overlap))
            raise ValueError(f"keywords cannot be both required and excluded: {values}")
        return self


class SearchProfileCreate(BaseModel):
    candidate_id: str = Field(default="local-candidate", min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=200)
    role_queries: list[str] = Field(default_factory=list)
    required_keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    allowed_work_modes: list[WorkMode] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    employment_types: list[str] = Field(default_factory=list)
    minimum_salary: int | None = Field(default=None, ge=0)
    salary_currency: str = Field(default="USD", min_length=3, max_length=3)
    salary_floor_policy: SalaryFloorPolicy = SalaryFloorPolicy.MINIMUM_OFFERED
    unknown_compensation_policy: UnknownCompensationPolicy = (
        UnknownCompensationPolicy.EXCLUDE
    )
    excluded_companies: list[str] = Field(default_factory=list)
    allowed_sources: list[str] = Field(default_factory=list)
    minimum_fit_score: float | None = Field(default=None, ge=0.0, le=100.0)


class SearchProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    role_queries: list[str] | None = None
    required_keywords: list[str] | None = None
    excluded_keywords: list[str] | None = None
    allowed_work_modes: list[WorkMode] | None = None
    locations: list[str] | None = None
    employment_types: list[str] | None = None
    minimum_salary: int | None = Field(default=None, ge=0)
    clear_minimum_salary: bool = False
    salary_currency: str | None = Field(default=None, min_length=3, max_length=3)
    salary_floor_policy: SalaryFloorPolicy | None = None
    unknown_compensation_policy: UnknownCompensationPolicy | None = None
    excluded_companies: list[str] | None = None
    allowed_sources: list[str] | None = None
    minimum_fit_score: float | None = Field(default=None, ge=0.0, le=100.0)
    clear_minimum_fit_score: bool = False
    active: bool | None = None


class SearchConstraintResult(BaseModel):
    eligible: bool
    reasons: list[str] = Field(default_factory=list)


class SearchProfilePage(BaseModel):
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    items: list[SearchProfile]


class SearchProfilePreviewRequest(BaseModel):
    candidate: CandidateProfile
    candidate_pool: int = Field(default=1000, ge=1, le=5000)
    limit: int = Field(default=25, ge=1, le=100)


class SearchProfileRankedJob(BaseModel):
    job: JobPosting
    score: ScoreBreakdown


class SearchProfileRejectedJob(BaseModel):
    job_id: str
    company: str
    title: str
    reasons: list[str]


class SearchProfilePreview(BaseModel):
    profile_id: str
    total_examined: int = Field(ge=0)
    total_eligible: int = Field(ge=0)
    total_rejected: int = Field(ge=0)
    ranked: list[SearchProfileRankedJob] = Field(default_factory=list)
    rejected_sample: list[SearchProfileRejectedJob] = Field(default_factory=list)
    rejection_summary: dict[str, int] = Field(default_factory=dict)
