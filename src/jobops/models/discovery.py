from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class DiscoveryProviderName(StrEnum):
    JOBICY = "jobicy"
    ADZUNA = "adzuna"


class DiscoveryProviderStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class DiscoveryRunRequest(BaseModel):
    providers: list[DiscoveryProviderName] = Field(
        default_factory=lambda: [
            DiscoveryProviderName.JOBICY,
            DiscoveryProviderName.ADZUNA,
        ]
    )
    limit_per_provider: int = Field(default=200, ge=1, le=500)


class DiscoveryProviderDiagnostic(BaseModel):
    provider: DiscoveryProviderName
    status: DiscoveryProviderStatus
    queries: int = Field(default=0, ge=0)
    fetched: int = Field(default=0, ge=0)
    normalized: int = Field(default=0, ge=0)
    persisted: int = Field(default=0, ge=0)
    duplicates: int = Field(default=0, ge=0)
    error: str | None = None


class DiscoveryRunResult(BaseModel):
    profile_id: str
    started_at: datetime
    completed_at: datetime
    providers_requested: int = Field(ge=0)
    providers_succeeded: int = Field(ge=0)
    providers_failed: int = Field(ge=0)
    providers_skipped: int = Field(ge=0)
    fetched: int = Field(ge=0)
    normalized: int = Field(ge=0)
    persisted: int = Field(ge=0)
    duplicates: int = Field(ge=0)
    persisted_job_ids: list[str] = Field(default_factory=list)
    provider_results: list[DiscoveryProviderDiagnostic] = Field(default_factory=list)
