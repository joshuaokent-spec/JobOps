import re
from collections.abc import Iterable
from urllib.parse import parse_qs, urlsplit

from jobops.browser.base import BrowserPolicyError
from jobops.browser.field_classifier import SemanticFieldClassifier
from jobops.browser.playwright_inspector import PlaywrightBrowserInspector
from jobops.browser.semantic_planner import SemanticPreparationPlanner
from jobops.models.browser import BrowserFormSnapshot, BrowserPageSnapshot
from jobops.models.lever_browser import LeverDetection, LeverPreparationResult

_LEVER_HOST = "jobs.lever.co"
_LEVER_API_HOST = "api.lever.co"
_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_LEVER_POSTING_PATH = re.compile(
    rf"^/(?P<site>[^/]+)/(?P<posting_id>{_UUID})(?:/(?P<apply>apply))?/?$"
)
_LEVER_API_APPLY_PATH = re.compile(rf"/postings/(?P<posting_id>{_UUID})/apply/?$")


class LeverDetectionError(BrowserPolicyError):
    """Raised when a page cannot be identified as a Lever application safely."""


class LeverBrowserAdapter:
    """Prepare Lever application forms without filling or submitting them."""

    def __init__(
        self,
        inspector: PlaywrightBrowserInspector | None = None,
        classifier: SemanticFieldClassifier | None = None,
        planner: SemanticPreparationPlanner | None = None,
        *,
        minimum_confidence: float = 0.65,
    ) -> None:
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be between 0 and 1")
        self.inspector = inspector or PlaywrightBrowserInspector()
        self.classifier = classifier or SemanticFieldClassifier()
        self.planner = planner or SemanticPreparationPlanner()
        self.minimum_confidence = minimum_confidence

    def prepare_url(self, url: str) -> LeverPreparationResult:
        return self.prepare_documents(self.inspector.inspect_url_documents(url))

    def prepare_html(
        self,
        html: str,
        *,
        base_url: str = "https://fixture.invalid/",
    ) -> LeverPreparationResult:
        return self.prepare_documents(
            self.inspector.inspect_html_documents(html, base_url=base_url)
        )

    def prepare_documents(
        self,
        documents: Iterable[BrowserPageSnapshot],
    ) -> LeverPreparationResult:
        pages = list(documents)
        if not pages:
            raise LeverDetectionError("no browser documents were available for detection")

        metadata = self._shared_metadata(pages)
        detections = [
            self._detect_document(page, index=index, metadata=metadata)
            for index, page in enumerate(pages)
        ]
        detection = max(detections, key=lambda item: item.confidence)
        if not detection.detected:
            raise LeverDetectionError(
                "Lever application context could not be identified with enough confidence"
            )

        selected_page = self._application_snapshot(pages[detection.document_index])
        mapping = self.classifier.classify_page(selected_page)
        plan = self.planner.plan(mapping)
        return LeverPreparationResult(
            detection=detection,
            page=selected_page,
            semantic_mapping=mapping,
            preparation_plan=plan,
            submission_allowed=False,
        )

    def _detect_document(
        self,
        page: BrowserPageSnapshot,
        *,
        index: int,
        metadata: dict[str, object],
    ) -> LeverDetection:
        parsed = urlsplit(page.url)
        hostname = (parsed.hostname or "").casefold().rstrip(".")
        reasons: list[str] = []
        score = 0.0

        path_match = _LEVER_POSTING_PATH.match(parsed.path)
        apply_page = bool(path_match and path_match.group("apply"))

        if hostname == _LEVER_HOST:
            score += 0.60
            reasons.append("Lever jobs host")
        if path_match:
            score += 0.15
            reasons.append("Lever posting UUID path")
        if apply_page:
            score += 0.20
            reasons.append("Lever /apply path")

        query = parse_qs(parsed.query)
        if self._source_values(query):
            score += 0.05
            reasons.append("Lever source query metadata")
        if query.get("lever-origin"):
            score += 0.03
            reasons.append("Lever origin query metadata")

        application_forms = [form for form in page.forms if self._is_application_form(form)]
        if any(self._lever_action(form.action) for form in application_forms):
            score += 0.35
            reasons.append("Lever application form action")
        if any(self._application_selector(form.selector) for form in application_forms):
            score += 0.15
            reasons.append("application-form selector signal")
        if any(self._has_common_lever_fields(form) for form in application_forms):
            score += 0.20
            reasons.append("Lever-like identity/resume field set")

        confidence = min(score, 1.0)
        detected = confidence >= self.minimum_confidence and bool(application_forms)
        return LeverDetection(
            detected=detected,
            confidence=confidence,
            reasons=reasons,
            document_index=index,
            document_url=page.url,
            embedded=index > 0,
            site=self._string_metadata(metadata, "site"),
            posting_id=self._string_metadata(metadata, "posting_id"),
            source_tokens=list(metadata.get("source_tokens", [])),
            origin=self._string_metadata(metadata, "origin"),
            apply_page=bool(metadata.get("apply_page")) or apply_page,
        )

    @classmethod
    def _application_snapshot(cls, page: BrowserPageSnapshot) -> BrowserPageSnapshot:
        forms = [form for form in page.forms if cls._is_application_form(form)]
        if not forms:
            raise LeverDetectionError(
                "Lever was detected but no application form could be isolated safely"
            )
        submit_controls = sum(
            1
            for form in forms
            for field in form.fields
            if field.is_submit_control
        )
        return page.model_copy(
            update={
                "forms": forms,
                "submit_controls": submit_controls,
                "dry_run": True,
            }
        )

    @classmethod
    def _is_application_form(cls, form: BrowserFormSnapshot) -> bool:
        if cls._lever_action(form.action):
            return True
        if cls._application_selector(form.selector) and cls._has_common_lever_fields(form):
            return True
        return cls._has_common_lever_fields(form) and any(
            field.is_submit_control for field in form.fields
        )

    @staticmethod
    def _application_selector(selector: str) -> bool:
        normalized = selector.casefold()
        return "application" in normalized or "apply" in normalized

    @staticmethod
    def _has_common_lever_fields(form: BrowserFormSnapshot) -> bool:
        signals = " ".join(
            value.casefold()
            for field in form.fields
            for value in (
                field.name,
                field.element_id,
                field.label,
                field.accessible_name,
            )
            if value
        )
        identity_hits = sum(
            token in signals
            for token in ("full name", "email", "phone", "resume", "resume/cv")
        )
        return identity_hits >= 2

    @staticmethod
    def _lever_action(action: str | None) -> bool:
        if not action:
            return False
        parsed = urlsplit(action)
        hostname = (parsed.hostname or "").casefold().rstrip(".")
        if hostname in {_LEVER_HOST, _LEVER_API_HOST}:
            return "/apply" in parsed.path
        normalized = action.casefold()
        return normalized.endswith("/apply") or "/apply?" in normalized

    @classmethod
    def _shared_metadata(cls, pages: list[BrowserPageSnapshot]) -> dict[str, object]:
        site: str | None = None
        posting_id: str | None = None
        source_tokens: list[str] = []
        origin: str | None = None
        apply_page = False

        for page in pages:
            parsed = urlsplit(page.url)
            query = parse_qs(parsed.query)
            source_tokens.extend(cls._source_values(query))
            if origin is None and query.get("lever-origin"):
                origin = query["lever-origin"][0]

            match = _LEVER_POSTING_PATH.match(parsed.path)
            if match:
                site = site or match.group("site")
                posting_id = posting_id or match.group("posting_id")
                apply_page = apply_page or bool(match.group("apply"))

            for form in page.forms:
                if not form.action:
                    continue
                action = urlsplit(form.action)
                action_match = _LEVER_POSTING_PATH.match(action.path)
                api_match = _LEVER_API_APPLY_PATH.search(action.path)
                if action_match:
                    site = site or action_match.group("site")
                    posting_id = posting_id or action_match.group("posting_id")
                    apply_page = apply_page or bool(action_match.group("apply"))
                elif api_match:
                    posting_id = posting_id or api_match.group("posting_id")
                    apply_page = True
                action_query = parse_qs(action.query)
                source_tokens.extend(cls._source_values(action_query))
                if origin is None and action_query.get("lever-origin"):
                    origin = action_query["lever-origin"][0]

        return {
            "site": site,
            "posting_id": posting_id,
            "source_tokens": list(dict.fromkeys(source_tokens)),
            "origin": origin,
            "apply_page": apply_page,
        }

    @staticmethod
    def _source_values(query: dict[str, list[str]]) -> list[str]:
        return [
            *query.get("lever-source", []),
            *query.get("lever-source[]", []),
        ]

    @staticmethod
    def _string_metadata(metadata: dict[str, object], key: str) -> str | None:
        value = metadata.get(key)
        return value if isinstance(value, str) else None
