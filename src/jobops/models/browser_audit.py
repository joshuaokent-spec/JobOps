from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from jobops.models.browser import BrowserEngine, BrowserPageSnapshot


class BrowserAuditVendor(StrEnum):
    GENERIC = "generic"
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    WORKDAY = "workday"


class BrowserAuditArtifactKind(StrEnum):
    SCREENSHOT = "screenshot"
    BROWSER_SNAPSHOT = "browser_snapshot"
    SEMANTIC_PLAN = "semantic_plan"
    ATS_CONTEXT = "ats_context"


class BrowserAuditArtifact(BaseModel):
    kind: BrowserAuditArtifactKind
    relative_path: str
    media_type: str
    byte_length: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class BrowserAuditManifest(BaseModel):
    schema_version: str = "1.0"
    run_id: str
    created_at: datetime
    source_url: str
    vendor: BrowserAuditVendor
    browser_engine: BrowserEngine
    redaction_applied: bool = True
    redacted_dom_values: int = Field(default=0, ge=0)
    live_writes_allowed: bool = False
    submission_allowed: bool = False
    artifacts: list[BrowserAuditArtifact] = Field(default_factory=list)


class BrowserInspectionCapture(BaseModel):
    documents: list[BrowserPageSnapshot] = Field(default_factory=list)
    screenshot_png: bytes
    redacted_dom_values: int = Field(default=0, ge=0)
