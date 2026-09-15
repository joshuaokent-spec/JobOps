import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from jobops.browser.audit_redaction import sanitize_page_snapshot, sanitize_url
from jobops.browser.audit_store import BrowserAuditArtifactStore
from jobops.models.browser_audit import (
    BrowserAuditArtifact,
    BrowserAuditArtifactKind,
    BrowserAuditManifest,
    BrowserAuditVendor,
    BrowserInspectionCapture,
)


class BrowserAuditBundleWriter:
    """Persist one correlated, privacy-sanitized browser audit bundle."""

    def __init__(self, store: BrowserAuditArtifactStore) -> None:
        self.store = store

    def write(
        self,
        capture: BrowserInspectionCapture,
        *,
        source_url: str,
        vendor: BrowserAuditVendor = BrowserAuditVendor.GENERIC,
        semantic_payload: BaseModel | dict[str, Any] | None = None,
        ats_context_payload: BaseModel | dict[str, Any] | None = None,
        run_id: str | None = None,
        created_at: datetime | None = None,
    ) -> BrowserAuditManifest:
        audit_run_id = run_id or uuid4().hex
        timestamp = created_at or datetime.now(UTC)

        browser_snapshot = [
            sanitize_page_snapshot(document).model_dump(mode="json")
            for document in capture.documents
        ]
        semantic = self._normalize_payload(semantic_payload)
        ats_context = self._normalize_payload(ats_context_payload)

        payloads = (
            (
                BrowserAuditArtifactKind.SCREENSHOT,
                "screenshot.png",
                "image/png",
                capture.screenshot_png,
            ),
            (
                BrowserAuditArtifactKind.BROWSER_SNAPSHOT,
                "browser-snapshot.json",
                "application/json",
                self._json_bytes(browser_snapshot),
            ),
            (
                BrowserAuditArtifactKind.SEMANTIC_PLAN,
                "semantic-plan.json",
                "application/json",
                self._json_bytes(semantic),
            ),
            (
                BrowserAuditArtifactKind.ATS_CONTEXT,
                "ats-context.json",
                "application/json",
                self._json_bytes(ats_context),
            ),
        )

        artifacts: list[BrowserAuditArtifact] = []
        for kind, file_name, media_type, payload in payloads:
            relative_path = self.store.write_bytes(audit_run_id, file_name, payload)
            artifacts.append(
                BrowserAuditArtifact(
                    kind=kind,
                    relative_path=relative_path,
                    media_type=media_type,
                    byte_length=len(payload),
                    sha256=hashlib.sha256(payload).hexdigest(),
                )
            )

        manifest = BrowserAuditManifest(
            run_id=audit_run_id,
            created_at=timestamp,
            source_url=sanitize_url(source_url) or source_url,
            vendor=vendor,
            browser_engine=self._browser_engine(capture),
            redaction_applied=True,
            redacted_dom_values=capture.redacted_dom_values,
            live_writes_allowed=False,
            submission_allowed=False,
            artifacts=artifacts,
        )
        self.store.write_bytes(
            audit_run_id,
            "manifest.json",
            self._json_bytes(manifest),
        )
        return manifest

    @classmethod
    def _normalize_payload(
        cls,
        payload: BaseModel | dict[str, Any] | None,
    ) -> dict[str, Any]:
        if payload is None:
            return {}
        raw = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        return cls._sanitize_object(raw)

    @classmethod
    def _sanitize_object(cls, value: Any, key: str | None = None) -> Any:
        if isinstance(value, dict):
            return {
                str(child_key): cls._sanitize_object(child_value, str(child_key))
                for child_key, child_value in value.items()
            }
        if isinstance(value, list):
            return [cls._sanitize_object(item, key) for item in value]
        if isinstance(value, str) and cls._is_url_key(key):
            return sanitize_url(value) or value
        return value

    @staticmethod
    def _is_url_key(key: str | None) -> bool:
        if key is None:
            return False
        normalized = key.casefold().replace("-", "_")
        return normalized in {
            "url",
            "source_url",
            "document_url",
            "href",
            "action",
            "apply_url",
            "posting_url",
        } or normalized.endswith("_url")

    @staticmethod
    def _json_bytes(payload: BaseModel | dict[str, Any] | list[Any]) -> bytes:
        normalized: Any = payload
        if isinstance(payload, BaseModel):
            normalized = payload.model_dump(mode="json")
        return json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    @staticmethod
    def _browser_engine(capture: BrowserInspectionCapture):
        # The capture contract intentionally does not contain browser session secrets.
        # M3 currently captures through Chromium unless a future capture contract says otherwise.
        from jobops.models.browser import BrowserEngine

        return BrowserEngine.CHROMIUM
