from enum import StrEnum

from pydantic import BaseModel, Field


class BrowserEngine(StrEnum):
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


class BrowserFieldKind(StrEnum):
    TEXT = "text"
    EMAIL = "email"
    TELEPHONE = "telephone"
    URL = "url"
    NUMBER = "number"
    DATE = "date"
    TEXTAREA = "textarea"
    SELECT = "select"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    FILE = "file"
    HIDDEN = "hidden"
    BUTTON = "button"
    SUBMIT = "submit"
    OTHER = "other"


class DryRunOperation(StrEnum):
    FILL = "fill"
    SELECT = "select"
    CHOOSE = "choose"
    UPLOAD = "upload"
    REVIEW = "review"
    SKIP = "skip"
    BLOCKED_SUBMIT = "blocked_submit"


class BrowserSessionConfig(BaseModel):
    engine: BrowserEngine = BrowserEngine.CHROMIUM
    headless: bool = True
    allow_submit: bool = False
    timeout_ms: int = Field(default=30_000, ge=1_000, le=120_000)
    block_service_workers: bool = True


class BrowserOption(BaseModel):
    value: str
    label: str
    disabled: bool = False


class BrowserFieldDescriptor(BaseModel):
    form_index: int = Field(ge=0)
    field_index: int = Field(ge=0)
    tag: str
    kind: BrowserFieldKind
    input_type: str | None = None
    name: str | None = None
    element_id: str | None = None
    label: str | None = None
    accessible_name: str | None = None
    placeholder: str | None = None
    required: bool = False
    disabled: bool = False
    selector: str
    options: list[BrowserOption] = Field(default_factory=list)
    is_submit_control: bool = False


class BrowserFormSnapshot(BaseModel):
    form_index: int = Field(ge=0)
    action: str | None = None
    method: str = "get"
    selector: str
    fields: list[BrowserFieldDescriptor] = Field(default_factory=list)


class BrowserPageActionDescriptor(BaseModel):
    tag: str
    text: str | None = None
    accessible_name: str | None = None
    href: str | None = None
    selector: str
    disabled: bool = False


class BrowserPageSnapshot(BaseModel):
    url: str
    title: str
    headings: list[str] = Field(default_factory=list)
    page_actions: list[BrowserPageActionDescriptor] = Field(default_factory=list)
    forms: list[BrowserFormSnapshot] = Field(default_factory=list)
    submit_controls: int = Field(default=0, ge=0)
    blocked_network_requests: int = Field(default=0, ge=0)
    dry_run: bool = True


class DryRunAction(BaseModel):
    form_index: int = Field(ge=0)
    field_index: int = Field(ge=0)
    operation: DryRunOperation
    selector: str
    label: str | None = None
    required: bool = False
    reason: str


class BrowserDryRunPlan(BaseModel):
    url: str
    actions: list[DryRunAction] = Field(default_factory=list)
    fillable_fields: int = Field(default=0, ge=0)
    submit_controls: int = Field(default=0, ge=0)
    submission_allowed: bool = False
