import hashlib
import json
from collections.abc import Callable, Mapping

from playwright.sync_api import Page

from jobops.models.submission import (
    PreparedSubmissionState,
    SubmissionAttemptStatus,
    SubmissionExecutionOutcome,
    SubmitAuthorization,
)

ReceiptScalar = str | int | float | bool | None
SubmissionSuccessProbe = Callable[[Page], Mapping[str, ReceiptScalar] | None]

_CONTROL_DESCRIPTOR_SCRIPT = r"""
(element) => {
  const normalize = value => {
    if (value === null || value === undefined) return null;
    const text = String(value).replace(/\s+/g, " ").trim();
    return text || null;
  };

  const form = element.form || null;
  return {
    tag: element.tagName.toLowerCase(),
    type: normalize(element.getAttribute("type")),
    id: normalize(element.id),
    name: normalize(element.getAttribute("name")),
    aria_label: normalize(element.getAttribute("aria-label")),
    text: normalize(element.innerText || element.value || element.textContent),
    disabled: Boolean(element.disabled || element.getAttribute("aria-disabled") === "true"),
    form_action: form ? normalize(form.getAttribute("action")) : null,
    form_method: form
      ? (normalize(form.getAttribute("method")) || "get").toLowerCase()
      : null,
  };
}
"""


def document_url_sha256(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def submit_control_sha256(page: Page, selector: str) -> str:
    locator = page.locator(selector)
    if locator.count() != 1:
        raise ValueError("submit control fingerprint requires exactly one matching element")
    descriptor = locator.evaluate(_CONTROL_DESCRIPTOR_SCRIPT)
    payload = json.dumps(
        descriptor,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class PlaywrightFinalSubmitExecutor:
    """Execute only the submit control sealed into a consumed authorization."""

    def __init__(
        self,
        page: Page,
        *,
        browser_session_id: str,
        success_probe: SubmissionSuccessProbe | None = None,
        timeout_ms: int = 10_000,
    ) -> None:
        if not browser_session_id.strip():
            raise ValueError("browser_session_id cannot be blank")
        if timeout_ms < 1:
            raise ValueError("timeout_ms must be positive")
        self.page = page
        self.browser_session_id = browser_session_id.strip()
        self.success_probe = success_probe
        self.timeout_ms = timeout_ms

    def execute(
        self,
        authorization: SubmitAuthorization,
        state: PreparedSubmissionState,
    ) -> SubmissionExecutionOutcome:
        preflight = self._preflight(authorization, state)
        if preflight is not None:
            return preflight

        locator = self.page.locator(authorization.submit_selector)
        try:
            locator.click(timeout=self.timeout_ms)
        except Exception:
            return SubmissionExecutionOutcome(
                status=SubmissionAttemptStatus.INDETERMINATE,
                submit_invoked=True,
                error_code="submit_click_exception",
                error_detail=(
                    "the authorized submit click raised after execution began; "
                    "manual reconciliation is required"
                ),
            )

        if self.success_probe is None:
            return SubmissionExecutionOutcome(
                status=SubmissionAttemptStatus.INDETERMINATE,
                submit_invoked=True,
                error_code="confirmation_not_observed",
                error_detail="submit was invoked but no success probe is configured",
            )

        try:
            metadata = self.success_probe(self.page)
        except Exception:
            return SubmissionExecutionOutcome(
                status=SubmissionAttemptStatus.INDETERMINATE,
                submit_invoked=True,
                error_code="confirmation_probe_exception",
                error_detail=(
                    "submit was invoked but confirmation could not be evaluated; "
                    "manual reconciliation is required"
                ),
            )

        if metadata is None:
            return SubmissionExecutionOutcome(
                status=SubmissionAttemptStatus.INDETERMINATE,
                submit_invoked=True,
                error_code="confirmation_not_observed",
                error_detail="submit was invoked but the configured confirmation was not observed",
            )

        receipt = dict(metadata)
        receipt["document_url_sha256"] = document_url_sha256(self.page.url)
        return SubmissionExecutionOutcome(
            status=SubmissionAttemptStatus.SUCCEEDED,
            submit_invoked=True,
            receipt_metadata=receipt,
        )

    def _preflight(
        self,
        authorization: SubmitAuthorization,
        state: PreparedSubmissionState,
    ) -> SubmissionExecutionOutcome | None:
        if (
            authorization.browser_session_id != self.browser_session_id
            or state.browser_session_id != self.browser_session_id
        ):
            return self._failed("browser_session_mismatch")

        current_document_hash = document_url_sha256(self.page.url)
        if (
            current_document_hash != authorization.document_url_sha256
            or current_document_hash != state.document_url_sha256
        ):
            return self._failed("document_drift")

        locator = self.page.locator(authorization.submit_selector)
        if locator.count() != 1:
            return self._failed("submit_control_not_unique")
        if not locator.is_visible() or not locator.is_enabled():
            return self._failed("submit_control_unavailable")

        current_control_hash = submit_control_sha256(
            self.page,
            authorization.submit_selector,
        )
        if (
            current_control_hash != authorization.submit_control_sha256
            or current_control_hash != state.submit_control_sha256
        ):
            return self._failed("submit_control_drift")

        if document_url_sha256(self.page.url) != current_document_hash:
            return self._failed("document_drift")
        return None

    @staticmethod
    def _failed(error_code: str) -> SubmissionExecutionOutcome:
        return SubmissionExecutionOutcome(
            status=SubmissionAttemptStatus.FAILED,
            submit_invoked=False,
            error_code=error_code,
            error_detail="authorized final-submit preflight failed closed",
        )
