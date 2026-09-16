import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from jobops.browser.audit import BrowserAuditBundleWriter
from jobops.browser.audit_redaction import sanitize_text, sanitize_url
from jobops.browser.audit_store import LocalBrowserAuditArtifactStore
from jobops.browser.playwright_inspector import PlaywrightBrowserInspector
from jobops.models.browser import (
    BrowserEngine,
    BrowserPageActionDescriptor,
    BrowserPageSnapshot,
)
from jobops.models.browser_audit import BrowserAuditVendor, BrowserInspectionCapture


def test_sanitize_url_preserves_safe_attribution_and_redacts_sensitive_values() -> None:
    sanitized = sanitize_url(
        "https://boards.example.com/jobs/123?"
        "gh_jid=123&source=Portfolio&email=josh@example.com&token=abc123#private"
    )

    assert sanitized is not None
    parsed = urlsplit(sanitized)
    query = parse_qs(parsed.query)
    assert query["gh_jid"] == ["123"]
    assert query["source"] == ["Portfolio"]
    assert query["email"] == ["[REDACTED]"]
    assert query["token"] == ["[REDACTED]"]
    assert parsed.fragment == ""


def test_sanitize_text_masks_structural_pii() -> None:
    assert sanitize_text("candidate@example.com") == "[REDACTED]"
    assert sanitize_text("Call 517-555-0123") == "Call [REDACTED]"
    assert sanitize_text("Address: 123 Main Street") == "Address: [REDACTED]"
    assert sanitize_text("General application guidance") == "General application guidance"


def test_capture_html_redacts_dom_before_screenshot_and_blocks_mutating_requests() -> None:
    html = """
    <!doctype html>
    <html>
    <body>
      <h1>Application</h1>
      <form>
        <label for="email">Email</label>
        <input id="email" name="email" value="candidate@example.com">
        <label for="phone">Phone</label>
        <input id="phone" name="phone" value="517-555-0123">
        <label for="why">Why this role?</label>
        <textarea id="why">Private candidate answer</textarea>
        <label for="auth">Work authorization</label>
        <select id="auth"><option selected>Yes</option><option>No</option></select>
      </form>
      <p>Email: candidate@example.com</p>
      <script>
        fetch('/should-be-blocked', {method: 'POST', body: 'private'}).catch(() => {});
      </script>
    </body>
    </html>
    """

    capture = PlaywrightBrowserInspector().capture_html(
        html,
        base_url="https://careers.example.com/jobs/123?source=fixture",
    )

    assert capture.screenshot_png.startswith(b"\x89PNG\r\n\x1a\n")
    assert capture.redacted_dom_values >= 5
    assert capture.browser_engine is BrowserEngine.CHROMIUM
    assert capture.documents
    assert capture.documents[0].blocked_network_requests >= 1
    serialized_snapshot = json.dumps(
        [document.model_dump(mode="json") for document in capture.documents]
    )
    assert "candidate@example.com" not in serialized_snapshot
    assert "517-555-0123" not in serialized_snapshot
    assert "Private candidate answer" not in serialized_snapshot


def test_bundle_writer_persists_correlated_hashed_sanitized_artifacts(tmp_path: Path) -> None:
    page = BrowserPageSnapshot(
        url=(
            "https://jobs.example.com/apply?source=Portfolio&"
            "email=candidate@example.com&token=topsecret123"
        ),
        title="Application for candidate@example.com",
        headings=["Phone: 517-555-0123"],
        page_actions=[
            BrowserPageActionDescriptor(
                tag="a",
                text="Email candidate@example.com",
                accessible_name="Call 517-555-0123",
                href="https://jobs.example.com/next?session=secret-session",
                selector="#continue",
                disabled=False,
            )
        ],
        forms=[],
        submit_controls=0,
        blocked_network_requests=2,
        dry_run=True,
    )
    capture = BrowserInspectionCapture(
        documents=[page],
        screenshot_png=b"\x89PNG\r\n\x1a\nsynthetic",
        browser_engine=BrowserEngine.WEBKIT,
        redacted_dom_values=4,
    )
    root = tmp_path / "audit"
    writer = BrowserAuditBundleWriter(LocalBrowserAuditArtifactStore(root))

    manifest = writer.write(
        capture,
        source_url=(
            "https://jobs.example.com/apply?source=Portfolio&"
            "email=candidate@example.com&token=topsecret123#fragment"
        ),
        vendor=BrowserAuditVendor.GENERIC,
        semantic_payload={
            "question": "Why this role?",
            "answer": "This is a private candidate answer.",
            "nested": {"review_band": "red", "current_value": "Yes"},
            "apply_url": "https://jobs.example.com/apply?source=Portfolio&token=secret",
        },
        ats_context_payload={
            "posting_id": "job-123",
            "posting_url": (
                "https://jobs.example.com/job/123?lever-source=Portfolio&"
                "email=candidate@example.com"
            ),
            "api_key": "never-persist-this",
        },
        run_id="run-123",
        created_at=datetime(2026, 9, 16, 12, 0, tzinfo=UTC),
    )

    assert manifest.run_id == "run-123"
    assert manifest.vendor is BrowserAuditVendor.GENERIC
    assert manifest.browser_engine is BrowserEngine.WEBKIT
    assert manifest.redacted_dom_values == 4
    assert manifest.live_writes_allowed is False
    assert manifest.submission_allowed is False

    source_query = parse_qs(urlsplit(manifest.source_url).query)
    assert source_query["source"] == ["Portfolio"]
    assert source_query["email"] == ["[REDACTED]"]
    assert source_query["token"] == ["[REDACTED]"]
    assert urlsplit(manifest.source_url).fragment == ""

    assert len(manifest.artifacts) == 4
    for artifact in manifest.artifacts:
        artifact_path = root / artifact.relative_path
        payload = artifact_path.read_bytes()
        assert len(payload) == artifact.byte_length
        assert hashlib.sha256(payload).hexdigest() == artifact.sha256

    semantic = json.loads((root / "run-123/semantic-plan.json").read_text())
    assert semantic["answer"] == "[OMITTED]"
    assert semantic["nested"]["current_value"] == "[OMITTED]"
    apply_query = parse_qs(urlsplit(semantic["apply_url"]).query)
    assert apply_query["source"] == ["Portfolio"]
    assert apply_query["token"] == ["[REDACTED]"]

    ats_context = json.loads((root / "run-123/ats-context.json").read_text())
    assert ats_context["api_key"] == "[OMITTED]"
    posting_query = parse_qs(urlsplit(ats_context["posting_url"]).query)
    assert posting_query["lever-source"] == ["Portfolio"]
    assert posting_query["email"] == ["[REDACTED]"]

    manifest_text = (root / "run-123/manifest.json").read_text()
    browser_snapshot_text = (root / "run-123/browser-snapshot.json").read_text()
    bundle_text = "\n".join(
        path.read_text(errors="ignore")
        for path in (root / "run-123").glob("*.json")
    )
    assert "candidate@example.com" not in bundle_text
    assert "517-555-0123" not in browser_snapshot_text
    assert "private candidate answer" not in bundle_text.casefold()
    assert "never-persist-this" not in bundle_text
    assert "topsecret123" not in manifest_text


def test_local_audit_store_rejects_path_traversal(tmp_path: Path) -> None:
    store = LocalBrowserAuditArtifactStore(tmp_path)

    with pytest.raises(ValueError, match="run_id"):
        store.write_bytes("../escape", "artifact.json", b"{}")
    with pytest.raises(ValueError, match="file_name"):
        store.write_bytes("run-1", "../artifact.json", b"{}")
