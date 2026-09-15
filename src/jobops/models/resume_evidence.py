from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class EvidenceKind(StrEnum):
    EXPERIENCE = "experience"
    PROJECT = "project"
    EDUCATION = "education"
    CERTIFICATION = "certification"
    SKILL = "skill"
    ACHIEVEMENT = "achievement"


class RoleFamily(StrEnum):
    DATA_ENGINEERING = "data_engineering"
    DATA_SCIENCE = "data_science"
    AI_ML = "ai_ml"
    ANALYTICS = "analytics"
    SOFTWARE = "software"
    GENERAL = "general"


class EvidenceSourceKind(StrEnum):
    DOCUMENT = "document"
    PROJECT_ARTIFACT = "project_artifact"
    EMPLOYMENT_RECORD = "employment_record"
    EDUCATION_RECORD = "education_record"
    CERTIFICATION_RECORD = "certification_record"
    SELF_ATTESTED = "self_attested"
    OTHER = "other"


class EvidenceSource(BaseModel):
    source_id: str = Field(min_length=1)
    kind: EvidenceSourceKind
    label: str = Field(min_length=1)
    locator: str | None = None
    notes: str | None = None


class EvidenceMetric(BaseModel):
    name: str = Field(min_length=1)
    value: str | int | float
    unit: str | None = None
    context: str | None = None


class ResumeEvidenceItem(BaseModel):
    evidence_id: str = Field(min_length=1)
    kind: EvidenceKind
    claim: str = Field(min_length=1)
    organization: str | None = None
    title: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    skills: list[str] = Field(default_factory=list)
    role_families: list[RoleFamily] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metrics: list[EvidenceMetric] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    verified: bool = False
    last_verified_at: datetime | None = None

    @field_validator("skills", "tags", "source_refs")
    @classmethod
    def _deduplicate_strings(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = value.strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key not in seen:
                seen.add(key)
                result.append(cleaned)
        return result

    @field_validator("role_families")
    @classmethod
    def _deduplicate_role_families(cls, values: list[RoleFamily]) -> list[RoleFamily]:
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def _validate_dates_and_verification(self) -> "ResumeEvidenceItem":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be earlier than start_date")
        if self.verified and not self.source_refs:
            raise ValueError("verified evidence requires at least one source reference")
        return self

    def retrieval_text(self) -> str:
        lines = [f"kind: {self.kind.value}", f"claim: {self.claim}"]
        if self.organization:
            lines.append(f"organization: {self.organization}")
        if self.title:
            lines.append(f"title: {self.title}")
        if self.skills:
            lines.append(f"skills: {', '.join(sorted(self.skills, key=str.casefold))}")
        if self.role_families:
            roles = ", ".join(sorted(role.value for role in self.role_families))
            lines.append(f"role_families: {roles}")
        if self.tags:
            lines.append(f"tags: {', '.join(sorted(self.tags, key=str.casefold))}")
        if self.metrics:
            metrics = "; ".join(
                f"{metric.name}={metric.value}{metric.unit or ''}" for metric in self.metrics
            )
            lines.append(f"metrics: {metrics}")
        return "\n".join(lines)


class ResumeFamilyDefinition(BaseModel):
    family_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    role_families: list[RoleFamily] = Field(default_factory=list)
    priority_skills: list[str] = Field(default_factory=list)
    pinned_evidence_ids: list[str] = Field(default_factory=list)
    excluded_evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("priority_skills", "pinned_evidence_ids", "excluded_evidence_ids")
    @classmethod
    def _deduplicate_strings(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @model_validator(mode="after")
    def _validate_pin_exclusion_overlap(self) -> "ResumeFamilyDefinition":
        overlap = set(self.pinned_evidence_ids) & set(self.excluded_evidence_ids)
        if overlap:
            raise ValueError("evidence cannot be both pinned and excluded")
        return self


class ResumeEvidenceBase(BaseModel):
    candidate_id: str = Field(min_length=1)
    sources: list[EvidenceSource] = Field(default_factory=list)
    items: list[ResumeEvidenceItem] = Field(default_factory=list)
    families: list[ResumeFamilyDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_references(self) -> "ResumeEvidenceBase":
        source_ids = [source.source_id for source in self.sources]
        evidence_ids = [item.evidence_id for item in self.items]
        family_ids = [family.family_id for family in self.families]

        for label, values in (
            ("source_id", source_ids),
            ("evidence_id", evidence_ids),
            ("family_id", family_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {label} values are not allowed")

        known_sources = set(source_ids)
        known_evidence = set(evidence_ids)
        for item in self.items:
            unknown = set(item.source_refs) - known_sources
            if unknown:
                raise ValueError(
                    f"evidence {item.evidence_id} references unknown sources: {sorted(unknown)}"
                )

        for family in self.families:
            referenced = set(family.pinned_evidence_ids) | set(family.excluded_evidence_ids)
            unknown = referenced - known_evidence
            if unknown:
                raise ValueError(
                    f"family {family.family_id} references unknown evidence: {sorted(unknown)}"
                )
        return self


class EvidenceQuery(BaseModel):
    kinds: list[EvidenceKind] = Field(default_factory=list)
    role_families: list[RoleFamily] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    verified_only: bool = True


class VerifiedResumePayload(BaseModel):
    candidate_id: str
    family_id: str | None = None
    evidence_ids: list[str]
