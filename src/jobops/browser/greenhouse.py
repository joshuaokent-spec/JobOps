import re
from collections.abc import Iterable
from urllib.parse import parse_qs, urlsplit

from jobops.browser.base import BrowserPolicyError
from jobops.browser.field_classifier import SemanticFieldClassifier
from jobops.browser.playwright_inspector import PlaywrightBrowserInspector
from jobops.browser.semantic_planner import SemanticPreparationPlanner
from jobops.models.browser import BrowserFormSnapshot, BrowserPageSnapshot
from jobops.models.greenhouse_browser import (
    GreenhouseDetection,
    GreenhousePreparationResult,
)

_GREENHOUSE_HOST_SUFFIX = "greenhouse.io"
_GREENHOUSE_FIELD_PREFIX = "job_application["
_GREENHOUSE_JOB_PATH = re.compile(r"/(?:jobs?|job)/(?P<job_id>\d+)(?:/|$)")


class GreenhouseDetectionError(BrowserPolicyError):
    """Raised when a page cannot be identified as a Greenhouse application safely."""


class GreenhouseBrowserAdapter:
    """Prepare Greenhouse application forms without filling or submitting them."""

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

    def prepare_url(self, url: str) -> GreenhousePreparationResult:
        documents = self.inspector.inspect_url_documents(url)
        return self.prepare_documents(documents)

    def prepare_html(
        self,
        html: str,
        *,
        base_url: str = "https://fixture.invalid/",
    ) -> GreenhousePreparationResult:
        documents = self.inspector.inspect_html_documents(html, base_url=base_url)
        return self.prepare_documents(documents)

    def prepare_documents(
        self,
        documents: Iterable[BrowserPageSnapshot],
    ) -> GreenhousePreparationResult:
        pages = list(documents)
        if not pages:
            raise GreenhouseDetectionError("no browser documents were available for detection")

        metadata = self._shared_metadata(pages)
        detections = [
            self._detect_document(page, index=index, metadata=metadata)
            for index, page in enumerate(pages)
        ]
        detection = max(detections, key=lambda item: item.confidence)
        if not detection.detected:
            raise GreenhouseDetectionError(
                "Greenhouse application context could not be identified with enough confidence"
            )

        selected_page = self._application_snapshot(pages[detection.document_index])
        mapping = self.classifier.classify_page(selected_page)
        plan = self.planner.plan(mapping)
        return GreenhousePreparationResult(
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
        metadata: dict[str, str | None],
    ) -> GreenhouseDetection:
        parsed = urlsplit(page.url)
        hostname = (parsed.hostname or "").casefold().rstrip(".")
        reasons: list[str] = []
        score = 0.0

        if hostname == _GREENHOUSE_HOST_SUFFIX or hostname.endswith(
            f".{_GREENHOUSE_HOST_SUFFIX}"
        ):
            score += 0.65
            reasons.append(f"Greenhouse host: {hostname}")

        query = parse_qs(parsed.query)
        if query.get("gh_jid"):
            score += 0.20
            reasons.append("Greenhouse gh_jid query parameter")
        if query.get("gh_src"):
            score += 0.05
            reasons.append("Greenhouse gh_src query parameter")

        application_forms = [form for form in page.forms if self._is_application_form(form)]
        if any(form.selector == "#application_form" for form in application_forms):
            score += 0.30
            reasons.append("Greenhouse application_form selector")
        if any(self._has_greenhouse_field_names(form) for form in application_forms):
            score += 0.45
            reasons.append("Greenhouse job_application field naming")
        if any(self._greenhouse_action(form.action) for form in application_forms):
            score += 0.35
            reasons.append("Greenhouse-like application form action")

        confidence = min(score, 1.0)
        detected = confidence >= self.minimum_confidence and bool(application_forms)
        return GreenhouseDetection(
            detected=detected,
            confidence=confidence,
            reasons=reasons,
            document_index=index,
            document_url=page.url,
            embedded=index > 0,
            job_id=metadata["job_id"],
            source_token=metadata["source_token"],
            board_token=metadata["board_token"],
        )

    @classmethod
    def _application_snapshot(cls, page: BrowserPageSnapshot) -> BrowserPageSnapshot:
        forms = [form for form in page.forms if cls._is_application_form(form)]
        if not forms:
            raise GreenhouseDetectionError(
                "Greenhouse was detected but no application form could be isolated safely"
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
        selector = form.selector.casefold()
        if selector == "#application_form":
            return True
        if cls._greenhouse_action(form.action):
            return True
        if cls._has_greenhouse_field_names(form):
            return True

        names = {field.name.casefold() for field in form.fields if field.name}
        common_identity = {"first_name", "last_name", "email", "resume"}
        return len(names & common_identity) >= 2

    @staticmethod
    def _has_greenhouse_field_names(form: BrowserFormSnapshot) -> bool:
        return any(
            field.name and _GREENHOUSE_FIELD_PREFIX in field.name.casefold()
            for field in form.fields
        )

    @staticmethod
    def _greenhouse_action(action: str | None) -> bool:
        if not action:
            return False
        normalized = action.casefold()
        return "greenhouse" in normalized or "/applications" in normalized

    @classmethod
    def _shared_metadata(cls, pages: list[BrowserPageSnapshot]) -> dict[str, str | None]:
        job_id: str | None = None
        source_token: str | None = None
        board_token: str | None = None

        for page in pages:
            parsed = urlsplit(page.url)
            query = parse_qs(parsed.query)
            if job_id is None:
                values = query.get("gh_jid") or query.get("job_id")
                if values:
                    job_id = values[0]
                else:
                    match = _GREENHOUSE_JOB_PATH.search(parsed.path)
                    if match:
                        job_id = match.group("job_id")
            if source_token is None and query.get("gh_src"):
                source_token = query["gh_src"][0]
            if board_token is None:
                board_token = cls._board_token(parsed.hostname, parsed.path)

        return {
            "job_id": job_id,
            "source_token": source_token,
            "board_token": board_token,
        }

    @staticmethod
    def _board_token(hostname: str | None, path: str) -> str | None:
        if not hostname:
            return None
        normalized_host = hostname.casefold().rstrip(".")
        if not (
            normalized_host == _GREENHOUSE_HOST_SUFFIX
            or normalized_host.endswith(f".{_GREENHOUSE_HOST_SUFFIX}")
        ):
            return None
        segments = [segment for segment in path.split("/") if segment]
        if not segments or segments[0].casefold() in {"job", "jobs"}:
            return None
        return segments[0]
