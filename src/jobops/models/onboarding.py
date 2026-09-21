from datetime import UTC, datetime

from pydantic import BaseModel, Field, model_validator

from jobops.models.candidate import CandidateProfile
from jobops.models.discovery import DiscoveryRunRequest
from jobops.models.flagship_run import FlagshipRunRequest
from jobops.models.resume_evidence import ResumeEvidenceBase


class ResumeAsset(BaseModel):
    family_id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=200)
    file_path: str = Field(min_length=1, max_length=1000)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class FlagshipRunDefaults(BaseModel):
    discovery: DiscoveryRunRequest = Field(default_factory=DiscoveryRunRequest)
    candidate_pool: int = Field(default=1000, ge=1, le=5000)
    max_jobs: int = Field(default=25, ge=1, le=100)
    evidence_limit: int = Field(default=6, ge=1, le=20)
    resume_minimum_confidence: float = Field(default=0.35, ge=0.0, le=1.0)
    fallback_family_id: str | None = Field(default=None, min_length=1, max_length=100)

    def build_request(
        self,
        candidate: CandidateProfile,
        resume_evidence: ResumeEvidenceBase,
    ) -> FlagshipRunRequest:
        return FlagshipRunRequest(
            candidate=candidate,
            resume_evidence=resume_evidence,
            **self.model_dump(),
        )


class CandidateOnboardingPayload(BaseModel):
    candidate: CandidateProfile
    resume_evidence: ResumeEvidenceBase
    resume_assets: list[ResumeAsset] = Field(default_factory=list)
    run_defaults: FlagshipRunDefaults = Field(default_factory=FlagshipRunDefaults)

    @model_validator(mode="after")
    def _validate_ownership_and_assets(self) -> "CandidateOnboardingPayload":
        candidate_id = self.candidate.candidate_id
        if self.resume_evidence.candidate_id != candidate_id:
            raise ValueError("resume evidence does not match candidate owner")

        family_ids = {family.family_id for family in self.resume_evidence.families}
        asset_ids = [asset.family_id for asset in self.resume_assets]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("resume asset family ids must be unique")

        unknown_assets = set(asset_ids) - family_ids
        if unknown_assets:
            raise ValueError(
                f"resume assets reference unknown families: {sorted(unknown_assets)}"
            )

        fallback = self.run_defaults.fallback_family_id
        if fallback is not None and fallback not in family_ids:
            raise ValueError(f"unknown fallback resume family: {fallback}")
        return self


class CandidateOnboarding(CandidateOnboardingPayload):
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def build_run_request(self) -> FlagshipRunRequest:
        return self.run_defaults.build_request(
            self.candidate,
            self.resume_evidence,
        )

    def resume_asset(self, family_id: str) -> ResumeAsset | None:
        return next(
            (asset for asset in self.resume_assets if asset.family_id == family_id),
            None,
        )


class CandidateOnboardingStatus(BaseModel):
    candidate_id: str
    onboarded: bool = False
    ready_to_run: bool = False
    ready_for_application_execution: bool = False
    resume_family_ids: list[str] = Field(default_factory=list)
    resume_asset_family_ids: list[str] = Field(default_factory=list)
    missing_resume_asset_family_ids: list[str] = Field(default_factory=list)
    verified_evidence_count: int = Field(default=0, ge=0)
    verified_fact_count: int = Field(default=0, ge=0)
    unverified_fact_count: int = Field(default=0, ge=0)
    updated_at: datetime | None = None


def onboarding_status(
    onboarding: CandidateOnboarding | None,
    *,
    candidate_id: str,
) -> CandidateOnboardingStatus:
    if onboarding is None:
        return CandidateOnboardingStatus(candidate_id=candidate_id)

    family_ids = sorted(
        family.family_id for family in onboarding.resume_evidence.families
    )
    asset_ids = sorted(asset.family_id for asset in onboarding.resume_assets)
    missing_assets = sorted(set(family_ids) - set(asset_ids))
    verified_evidence = sum(
        item.verified for item in onboarding.resume_evidence.items
    )
    verified_facts = sum(fact.verified for fact in onboarding.candidate.facts)
    unverified_facts = len(onboarding.candidate.facts) - verified_facts
    ready_to_run = bool(family_ids and verified_evidence)
    return CandidateOnboardingStatus(
        candidate_id=onboarding.candidate.candidate_id,
        onboarded=True,
        ready_to_run=ready_to_run,
        ready_for_application_execution=ready_to_run and not missing_assets,
        resume_family_ids=family_ids,
        resume_asset_family_ids=asset_ids,
        missing_resume_asset_family_ids=missing_assets,
        verified_evidence_count=verified_evidence,
        verified_fact_count=verified_facts,
        unverified_fact_count=unverified_facts,
        updated_at=onboarding.updated_at,
    )
