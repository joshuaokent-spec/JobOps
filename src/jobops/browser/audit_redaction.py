import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from jobops.models.browser import BrowserPageSnapshot

_SAFE_ATTRIBUTION_KEYS = {
    "source",
    "gh_jid",
    "gh_src",
    "lever-source",
    "lever-source[]",
    "lever-origin",
}
_SENSITIVE_KEY = re.compile(
    r"(?:token|auth|secret|password|passwd|session|cookie|credential|api[-_]?key|"
    r"signature|sig|oauth|sso|verification|reset|code|state)",
    re.IGNORECASE,
)
_PII_KEY = re.compile(
    r"(?:email|phone|mobile|address|street|postal|zip|name|ssn|social[-_]?security|"
    r"birth|dob|gender|race|ethnic|disability|veteran|authorization|sponsor|consent)",
    re.IGNORECASE,
)
_EMAIL_VALUE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PHONE_VALUE = re.compile(r"^\+?[\d().\-\s]{7,}$")
_EMAIL_TEXT = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_PHONE_TEXT = re.compile(r"\b\+?\d[\d().\-\s]{6,}\d\b")
_SSN_TEXT = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_LABELLED_PII_TEXT = re.compile(
    r"\b(?:email|e-mail|phone|mobile|address|street address|work authorization|"
    r"sponsorship|gender|race|ethnicity|disability|veteran status|consent)\s*:\s*[^|;\n]+",
    re.IGNORECASE,
)
_REDACTED = "[REDACTED]"

SCREENSHOT_REDACTION_SCRIPT = r"""
() => {
  let redacted = 0;

  const mark = element => {
    if (!element || element.dataset.jobopsAuditRedacted === "true") return;
    element.dataset.jobopsAuditRedacted = "true";
    redacted += 1;
  };

  for (const input of document.querySelectorAll("input")) {
    const type = (input.type || "text").toLowerCase();
    if (type === "checkbox" || type === "radio") {
      if (input.checked) {
        input.checked = false;
        mark(input);
      }
      continue;
    }
    if (type === "file") continue;
    if (input.value) {
      input.value = type === "hidden" || type === "password" ? "" : "[REDACTED]";
      mark(input);
    }
  }

  for (const textarea of document.querySelectorAll("textarea")) {
    if (textarea.value) {
      textarea.value = "[REDACTED]";
      mark(textarea);
    }
  }

  for (const select of document.querySelectorAll("select")) {
    if (select.selectedIndex >= 0) {
      select.selectedIndex = -1;
      mark(select);
    }
  }

  for (const editable of document.querySelectorAll('[contenteditable="true"]')) {
    if ((editable.textContent || "").trim()) {
      editable.textContent = "[REDACTED]";
      mark(editable);
    }
  }

  const piiPatterns = [
    /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi,
    /\b\+?\d[\d().\-\s]{6,}\d\b/g,
    /\b\d{3}-\d{2}-\d{4}\b/g,
    /\b(?:email|e-mail|phone|mobile|address|street address)\s*:\s*[^\n|]+/gi,
    /\b(?:work authorization|sponsorship|gender|race|ethnicity)\s*:\s*[^\n|]+/gi,
    /\b(?:disability|veteran status|consent)\s*:\s*[^\n|]+/gi,
  ];

  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    let value = node.nodeValue || "";
    let changed = false;
    for (const pattern of piiPatterns) {
      pattern.lastIndex = 0;
      if (pattern.test(value)) {
        pattern.lastIndex = 0;
        value = value.replace(pattern, match => {
          const colon = match.indexOf(":");
          return colon >= 0 ? `${match.slice(0, colon + 1)} [REDACTED]` : "[REDACTED]";
        });
        changed = true;
      }
    }
    if (changed) {
      node.nodeValue = value;
      redacted += 1;
    }
  }

  return redacted;
}
"""


LIVE_SCREENSHOT_REDACTION_APPLY_SCRIPT = r"""
() => {
  let redacted = 0;
  window.__jobopsAuditLiveTextRestores = [];
  window.__jobopsAuditLiveStyleRestores = [];

  const rememberStyle = element => {
    if (!element || element.dataset.jobopsAuditLiveMasked === "true") return;
    window.__jobopsAuditLiveStyleRestores.push({
      element,
      style: element.getAttribute("style"),
    });
    element.dataset.jobopsAuditLiveMasked = "true";
    redacted += 1;
  };

  for (const element of document.querySelectorAll(
    "input, textarea, select, [contenteditable='true']"
  )) {
    rememberStyle(element);
    const type = (element.getAttribute("type") || "").toLowerCase();
    if (type === "checkbox" || type === "radio") {
      element.style.setProperty("opacity", "0", "important");
      continue;
    }
    element.style.setProperty("color", "transparent", "important");
    element.style.setProperty("caret-color", "transparent", "important");
    element.style.setProperty("text-shadow", "none", "important");
  }

  const piiPatterns = [
    /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi,
    /\b\+?\d[\d().\-\s]{6,}\d\b/g,
    /\b\d{3}-\d{2}-\d{4}\b/g,
    /\b(?:email|e-mail|phone|mobile|address|street address)\s*:\s*[^\n|]+/gi,
    /\b(?:work authorization|sponsorship|gender|race|ethnicity)\s*:\s*[^\n|]+/gi,
    /\b(?:disability|veteran status|consent)\s*:\s*[^\n|]+/gi,
  ];

  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    let value = node.nodeValue || "";
    let changed = false;
    for (const pattern of piiPatterns) {
      pattern.lastIndex = 0;
      if (pattern.test(value)) {
        pattern.lastIndex = 0;
        value = value.replace(pattern, match => {
          const colon = match.indexOf(":");
          return colon >= 0 ? match.slice(0, colon + 1) + " [REDACTED]" : "[REDACTED]";
        });
        changed = true;
      }
    }
    if (changed) {
      window.__jobopsAuditLiveTextRestores.push({node, value: node.nodeValue});
      node.nodeValue = value;
      redacted += 1;
    }
  }

  return redacted;
}
"""

LIVE_SCREENSHOT_REDACTION_RESTORE_SCRIPT = r"""
() => {
  for (const item of (window.__jobopsAuditLiveTextRestores || [])) {
    if (item.node) item.node.nodeValue = item.value;
  }
  for (const item of (window.__jobopsAuditLiveStyleRestores || [])) {
    if (!item.element) continue;
    if (item.style === null) {
      item.element.removeAttribute("style");
    } else {
      item.element.setAttribute("style", item.style);
    }
    delete item.element.dataset.jobopsAuditLiveMasked;
  }
  window.__jobopsAuditLiveTextRestores = [];
  window.__jobopsAuditLiveStyleRestores = [];
  return true;
}
"""


def sanitize_url(url: str | None) -> str | None:
    if not url:
        return url
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))

    safe_query: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if _should_redact_query_value(key, value):
            safe_query.append((key, _REDACTED))
        else:
            safe_query.append((key, value))
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(safe_query, doseq=True),
            "",
        )
    )


def sanitize_text(value: str | None) -> str | None:
    if value is None:
        return None
    sanitized = _LABELLED_PII_TEXT.sub(_redact_labelled_value, value)
    sanitized = _EMAIL_TEXT.sub(_REDACTED, sanitized)
    sanitized = _PHONE_TEXT.sub(_REDACTED, sanitized)
    sanitized = _SSN_TEXT.sub(_REDACTED, sanitized)
    return sanitized


def sanitize_page_snapshot(page: BrowserPageSnapshot) -> BrowserPageSnapshot:
    forms = []
    for form in page.forms:
        fields = []
        for field in form.fields:
            options = [
                option.model_copy(
                    update={
                        "value": sanitize_text(option.value) or option.value,
                        "label": sanitize_text(option.label) or option.label,
                    }
                )
                for option in field.options
            ]
            fields.append(
                field.model_copy(
                    update={
                        "label": sanitize_text(field.label),
                        "accessible_name": sanitize_text(field.accessible_name),
                        "placeholder": sanitize_text(field.placeholder),
                        "options": options,
                    }
                )
            )
        forms.append(
            form.model_copy(
                update={
                    "action": sanitize_url(form.action),
                    "fields": fields,
                }
            )
        )

    actions = [
        action.model_copy(
            update={
                "text": sanitize_text(action.text),
                "accessible_name": sanitize_text(action.accessible_name),
                "href": sanitize_url(action.href),
            }
        )
        for action in page.page_actions
    ]
    return page.model_copy(
        update={
            "url": sanitize_url(page.url) or page.url,
            "title": sanitize_text(page.title) or page.title,
            "headings": [sanitize_text(heading) or heading for heading in page.headings],
            "forms": forms,
            "page_actions": actions,
        }
    )


def _redact_labelled_value(match: re.Match[str]) -> str:
    text = match.group(0)
    colon = text.find(":")
    if colon < 0:
        return _REDACTED
    return f"{text[: colon + 1]} {_REDACTED}"


def _should_redact_query_value(key: str, value: str) -> bool:
    if _SENSITIVE_KEY.search(key) or _PII_KEY.search(key):
        return True
    if _EMAIL_VALUE.fullmatch(value.strip()) or _PHONE_VALUE.fullmatch(value.strip()):
        return True
    return key.casefold() not in _SAFE_ATTRIBUTION_KEYS and _looks_secret_like(value)


def _looks_secret_like(value: str) -> bool:
    normalized = value.strip()
    if len(normalized) < 24:
        return False
    if re.fullmatch(r"[A-Za-z0-9_\-.~+/=]+", normalized) is None:
        return False
    has_alpha = any(char.isalpha() for char in normalized)
    has_digit = any(char.isdigit() for char in normalized)
    return has_alpha and has_digit
