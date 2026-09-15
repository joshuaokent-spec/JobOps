from html import escape
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import BrowserContext, Frame, Page, Route, sync_playwright

from jobops.browser.audit_redaction import SCREENSHOT_REDACTION_SCRIPT
from jobops.browser.base import (
    BrowserNavigationBlockedError,
    BrowserPolicyError,
    SubmissionBlockedError,
)
from jobops.models.browser import BrowserPageSnapshot, BrowserSessionConfig
from jobops.models.browser_audit import BrowserInspectionCapture

_DISALLOWED_HOST_SUFFIXES = ("linkedin.com",)
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

_SUBMISSION_GUARD_SCRIPT = r"""
(() => {
  if (window.__jobopsSubmissionGuardInstalled) return;
  window.__jobopsSubmissionGuardInstalled = true;

  document.addEventListener("submit", event => {
    event.preventDefault();
    event.stopImmediatePropagation();
  }, true);

  HTMLFormElement.prototype.submit = function() {
    throw new Error("JOBOPS_SUBMISSION_BLOCKED");
  };
  HTMLFormElement.prototype.requestSubmit = function() {
    throw new Error("JOBOPS_SUBMISSION_BLOCKED");
  };
})();
"""

_INSPECTION_SCRIPT = r"""
() => {
  const normalize = value => {
    if (value === null || value === undefined) return null;
    const text = String(value).replace(/\s+/g, " ").trim();
    return text || null;
  };

  const cssString = value => String(value)
    .replace(/\\/g, "\\\\")
    .replace(/"/g, "\\\"");

  const selectorFor = element => {
    if (element.id) return `#${CSS.escape(element.id)}`;
    if (element.name) {
      return `${element.tagName.toLowerCase()}[name="${cssString(element.name)}"]`;
    }
    const parts = [];
    let current = element;
    while (current && current.nodeType === Node.ELEMENT_NODE && current !== document.body) {
      let part = current.tagName.toLowerCase();
      const parent = current.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter(
          sibling => sibling.tagName === current.tagName
        );
        if (siblings.length > 1) {
          part += `:nth-of-type(${siblings.indexOf(current) + 1})`;
        }
      }
      parts.unshift(part);
      current = parent;
    }
    return parts.join(" > ");
  };

  const kindFor = element => {
    const tag = element.tagName.toLowerCase();
    if (tag === "textarea") return "textarea";
    if (tag === "select") return "select";
    if (tag === "button") {
      const type = (element.getAttribute("type") || "submit").toLowerCase();
      return type === "submit" ? "submit" : "button";
    }
    if (tag !== "input") return "other";

    const type = (element.getAttribute("type") || "text").toLowerCase();
    const kinds = {
      email: "email",
      tel: "telephone",
      url: "url",
      number: "number",
      date: "date",
      checkbox: "checkbox",
      radio: "radio",
      file: "file",
      hidden: "hidden",
      submit: "submit",
      image: "submit",
      button: "button",
      reset: "button",
    };
    return kinds[type] || "text";
  };

  const forms = Array.from(document.forms).map((form, formIndex) => {
    const fields = Array.from(form.querySelectorAll("input, textarea, select, button"))
      .map((element, fieldIndex) => {
        const tag = element.tagName.toLowerCase();
        const inputType = tag === "input" || tag === "button"
          ? (element.getAttribute("type") || (tag === "button" ? "submit" : "text")).toLowerCase()
          : null;
        const kind = kindFor(element);
        const labelText = element.labels
          ? normalize(Array.from(element.labels).map(label => label.innerText).join(" "))
          : null;
        const ariaLabel = normalize(element.getAttribute("aria-label"));
        const options = tag === "select"
          ? Array.from(element.options).map(option => ({
              value: option.value,
              label: normalize(option.textContent) || option.value,
              disabled: option.disabled,
            }))
          : [];

        return {
          form_index: formIndex,
          field_index: fieldIndex,
          tag,
          kind,
          input_type: inputType,
          name: normalize(element.getAttribute("name")),
          element_id: normalize(element.id),
          label: labelText,
          accessible_name: ariaLabel || labelText || normalize(element.getAttribute("name")),
          placeholder: normalize(element.getAttribute("placeholder")),
          required: Boolean(element.required || element.getAttribute("aria-required") === "true"),
          disabled: Boolean(element.disabled),
          selector: selectorFor(element),
          options,
          is_submit_control: kind === "submit",
        };
      });

    return {
      form_index: formIndex,
      action: normalize(form.getAttribute("action")),
      method: (form.getAttribute("method") || "get").toLowerCase(),
      selector: selectorFor(form),
      fields,
    };
  });

  const headings = Array.from(document.querySelectorAll("h1, h2, h3, h4, [role='heading']"))
    .map(element => normalize(element.innerText || element.textContent))
    .filter(Boolean);

  const pageActions = Array.from(document.querySelectorAll("button, a[href], [role='button']"))
    .map(element => ({
      tag: element.tagName.toLowerCase(),
      text: normalize(element.innerText || element.textContent || element.value),
      accessible_name: normalize(element.getAttribute("aria-label")),
      href: element.tagName.toLowerCase() === "a"
        ? normalize(element.getAttribute("href"))
        : null,
      selector: selectorFor(element),
      disabled: Boolean(element.disabled || element.getAttribute("aria-disabled") === "true"),
    }));

  return {
    title: document.title,
    headings,
    page_actions: pageActions,
    forms,
  };
}
"""


class PlaywrightBrowserInspector:
    """Inspect application UI in an isolated, submission-disabled browser context."""

    def __init__(self, config: BrowserSessionConfig | None = None) -> None:
        self.config = config or BrowserSessionConfig()

    def inspect_url(self, url: str) -> BrowserPageSnapshot:
        return self.inspect_url_documents(url)[0]

    def inspect_url_documents(self, url: str) -> list[BrowserPageSnapshot]:
        """Inspect the top document plus meaningful child-frame application UI."""
        self._assert_allowed_url(url)
        blocked = {"count": 0}
        navigation = {"complete": False}

        with sync_playwright() as playwright:
            browser_type = getattr(playwright, self.config.engine.value)
            browser = browser_type.launch(headless=self.config.headless)
            try:
                context = self._new_context(browser)
                self._install_network_guard(context, blocked, navigation)
                context.add_init_script(_SUBMISSION_GUARD_SCRIPT)
                page = context.new_page()
                page.set_default_timeout(self.config.timeout_ms)
                page.goto(url, wait_until="domcontentloaded", timeout=self.config.timeout_ms)
                navigation["complete"] = True
                return self._snapshots(page, blocked_requests=blocked["count"])
            finally:
                browser.close()

    def capture_url(self, url: str) -> BrowserInspectionCapture:
        """Capture structural state plus a privacy-redacted screenshot without writing."""
        self._assert_allowed_url(url)
        blocked = {"count": 0}
        navigation = {"complete": False}

        with sync_playwright() as playwright:
            browser_type = getattr(playwright, self.config.engine.value)
            browser = browser_type.launch(headless=self.config.headless)
            try:
                context = self._new_context(browser)
                self._install_network_guard(context, blocked, navigation)
                context.add_init_script(_SUBMISSION_GUARD_SCRIPT)
                page = context.new_page()
                page.set_default_timeout(self.config.timeout_ms)
                page.goto(url, wait_until="domcontentloaded", timeout=self.config.timeout_ms)
                navigation["complete"] = True
                return self._capture(page, blocked_requests=blocked["count"])
            finally:
                browser.close()

    def inspect_html(
        self,
        html: str,
        *,
        base_url: str = "https://fixture.invalid/",
    ) -> BrowserPageSnapshot:
        return self.inspect_html_documents(html, base_url=base_url)[0]

    def inspect_html_documents(
        self,
        html: str,
        *,
        base_url: str = "https://fixture.invalid/",
    ) -> list[BrowserPageSnapshot]:
        """Inspect controlled HTML and meaningful child-frame application UI."""
        self._assert_allowed_url(base_url)
        blocked = {"count": 0}
        navigation = {"complete": True}

        with sync_playwright() as playwright:
            browser_type = getattr(playwright, self.config.engine.value)
            browser = browser_type.launch(headless=self.config.headless)
            try:
                context = self._new_context(browser)
                self._install_network_guard(context, blocked, navigation)
                context.add_init_script(_SUBMISSION_GUARD_SCRIPT)
                page = context.new_page()
                page.set_default_timeout(self.config.timeout_ms)
                guarded_html = (
                    f'<base href="{escape(base_url, quote=True)}">'
                    f"<script>{_SUBMISSION_GUARD_SCRIPT}</script>{html}"
                )
                page.set_content(guarded_html, wait_until="domcontentloaded")
                page.wait_for_timeout(25)
                return self._snapshots(
                    page,
                    blocked_requests=blocked["count"],
                    root_url_override=base_url,
                )
            finally:
                browser.close()

    def capture_html(
        self,
        html: str,
        *,
        base_url: str = "https://fixture.invalid/",
    ) -> BrowserInspectionCapture:
        """Capture controlled HTML with the same guards used by normal inspection."""
        self._assert_allowed_url(base_url)
        blocked = {"count": 0}
        navigation = {"complete": True}

        with sync_playwright() as playwright:
            browser_type = getattr(playwright, self.config.engine.value)
            browser = browser_type.launch(headless=self.config.headless)
            try:
                context = self._new_context(browser)
                self._install_network_guard(context, blocked, navigation)
                context.add_init_script(_SUBMISSION_GUARD_SCRIPT)
                page = context.new_page()
                page.set_default_timeout(self.config.timeout_ms)
                guarded_html = (
                    f'<base href="{escape(base_url, quote=True)}">'
                    f"<script>{_SUBMISSION_GUARD_SCRIPT}</script>{html}"
                )
                page.set_content(guarded_html, wait_until="domcontentloaded")
                page.wait_for_timeout(25)
                return self._capture(
                    page,
                    blocked_requests=blocked["count"],
                    root_url_override=base_url,
                )
            finally:
                browser.close()

    def submit_form(self, selector: str) -> None:
        if not self.config.allow_submit:
            raise SubmissionBlockedError(
                f"submission is disabled for M3.1 dry-run sessions: {selector}"
            )
        raise BrowserPolicyError("form submission execution is not implemented in M3.1")

    def _new_context(self, browser: Any) -> BrowserContext:
        service_workers = "block" if self.config.block_service_workers else "allow"
        return browser.new_context(service_workers=service_workers)

    def _install_network_guard(
        self,
        context: BrowserContext,
        blocked: dict[str, int],
        navigation: dict[str, bool],
    ) -> None:
        if self.config.allow_submit:
            return

        def handler(route: Route) -> None:
            request = route.request
            should_block = request.method.upper() in _MUTATING_METHODS
            if (
                navigation["complete"]
                and request.is_navigation_request()
                and request.resource_type == "document"
            ):
                should_block = True

            if should_block:
                blocked["count"] += 1
                route.abort("blockedbyclient")
            else:
                route.continue_()

        context.route("**/*", handler)

    @classmethod
    def _capture(
        cls,
        page: Page,
        *,
        blocked_requests: int,
        root_url_override: str | None = None,
    ) -> BrowserInspectionCapture:
        documents = cls._snapshots(
            page,
            blocked_requests=blocked_requests,
            root_url_override=root_url_override,
        )
        redacted_dom_values = sum(
            int(frame.evaluate(SCREENSHOT_REDACTION_SCRIPT) or 0)
            for frame in page.frames
        )
        screenshot = page.screenshot(full_page=True, type="png")
        return BrowserInspectionCapture(
            documents=documents,
            screenshot_png=screenshot,
            redacted_dom_values=redacted_dom_values,
        )

    @classmethod
    def _snapshots(
        cls,
        page: Page,
        *,
        blocked_requests: int,
        root_url_override: str | None = None,
    ) -> list[BrowserPageSnapshot]:
        ordered_frames = [
            page.main_frame,
            *(frame for frame in page.frames if frame != page.main_frame),
        ]
        snapshots: list[BrowserPageSnapshot] = []
        for index, frame in enumerate(ordered_frames):
            snapshot = cls._snapshot(
                frame,
                blocked_requests=blocked_requests,
                url_override=root_url_override if index == 0 else None,
            )
            meaningful_child_ui = bool(
                snapshot.forms or snapshot.page_actions or snapshot.headings
            )
            if index == 0 or meaningful_child_ui:
                snapshots.append(snapshot)
        return snapshots

    @staticmethod
    def _snapshot(
        document: Page | Frame,
        *,
        blocked_requests: int,
        url_override: str | None = None,
    ) -> BrowserPageSnapshot:
        payload = document.evaluate(_INSPECTION_SCRIPT)
        forms = payload.get("forms", [])
        submit_controls = sum(
            1
            for form in forms
            for field in form.get("fields", [])
            if field.get("is_submit_control")
        )
        return BrowserPageSnapshot.model_validate(
            {
                "url": url_override or document.url,
                "title": payload.get("title", ""),
                "headings": payload.get("headings", []),
                "page_actions": payload.get("page_actions", []),
                "forms": forms,
                "submit_controls": submit_controls,
                "blocked_network_requests": blocked_requests,
                "dry_run": True,
            }
        )

    @staticmethod
    def _assert_allowed_url(url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise BrowserNavigationBlockedError("browser navigation requires an HTTP(S) URL")
        hostname = parsed.hostname.casefold().rstrip(".")
        if any(
            hostname == suffix or hostname.endswith(f".{suffix}")
            for suffix in _DISALLOWED_HOST_SUFFIXES
        ):
            raise BrowserNavigationBlockedError(
                "LinkedIn browser automation is outside the JobOps ATS automation scope"
            )
