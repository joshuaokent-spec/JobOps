from typing import Protocol

from jobops.models.browser import BrowserPageSnapshot, BrowserSessionConfig


class BrowserPolicyError(RuntimeError):
    """Raised when browser automation attempts an action forbidden by policy."""


class SubmissionBlockedError(BrowserPolicyError):
    """Raised when a submission action is attempted while the submit gate is closed."""


class BrowserNavigationBlockedError(BrowserPolicyError):
    """Raised when navigation targets a disallowed site or flow."""


class BrowserAdapter(Protocol):
    config: BrowserSessionConfig

    def inspect_url(self, url: str) -> BrowserPageSnapshot: ...

    def inspect_html(
        self,
        html: str,
        *,
        base_url: str = "https://fixture.invalid/",
    ) -> BrowserPageSnapshot: ...

    def submit_form(self, selector: str) -> None: ...
