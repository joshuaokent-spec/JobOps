import re
from collections.abc import Iterable
from urllib.parse import parse_qs, urlsplit

from jobops.browser.base import BrowserPolicyError
from jobops.browser.field_classifier import SemanticFieldClassifier
from jobops.browser.playwright_inspector import PlaywrightBrowserInspector
from jobops.browser.semantic_planner import SemanticPreparationPlanner
from jobops.models.browser import BrowserPageActionDescriptor, BrowserPageSnapshot
from jobops.models.form_mapping import ApplicationFieldSemantic
from jobops.models.workday_browser import (
    WorkdayBlockedAction,
    WorkdayBlockedOperation,
    WorkdayDetection,
    WorkdayPreparationResult,
    WorkdayStepCategory,
    WorkdayWizardStep,
)

_WORKDAY_HOST_SUFFIXES = ("myworkdayjobs.com", "myworkdaysite.com")
_LOCALE = re.compile(r"^[a-z]{2}(?:-[A-Z]{2})?$", re.IGNORECASE)
_REQUISITION_SUFFIX = re.compile(r"_([A-Za-z]{1,10}-?\d[\w-]*)$")


class WorkdayDetectionError(BrowserPolicyError):
    """Raised when a page cannot be identified as a Workday application safely."""


class WorkdayBrowserPrototype:
    """Inspect one visible Workday wizard state without advancing or writing it."""

    def __init__(
        self,
        inspector: PlaywrightBrowserInspector | None = None,
        classifier: SemanticFieldClassifier | None = None,
        planner: SemanticPreparationPlanner | None = None,
        *,
        minimum_confidence: float = 0.75,
    ) -> None:
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be between 0 and 1")
        self.inspector = inspector or PlaywrightBrowserInspector()
        self.classifier = classifier or SemanticFieldClassifier()
        self.planner = planner or SemanticPreparationPlanner()
        self.minimum_confidence = minimum_confidence

    def prepare_url(self, url: str) -> WorkdayPreparationResult:
        return self.prepare_documents(self.inspector.inspect_url_documents(url))

    def prepare_html(
        self,
        html: str,
        *,
        base_url: str = "https://fixture.invalid/",
    ) -> WorkdayPreparationResult:
        return self.prepare_documents(
            self.inspector.inspect_html_documents(html, base_url=base_url)
        )

    def prepare_documents(
        self,
        documents: Iterable[BrowserPageSnapshot],
    ) -> WorkdayPreparationResult:
        pages = list(documents)
        if not pages:
            raise WorkdayDetectionError("no browser documents were available for detection")

        detections = [
            self._detect_document(page, index=index) for index, page in enumerate(pages)
        ]
        detection = max(detections, key=lambda item: item.confidence)
        if not detection.detected:
            raise WorkdayDetectionError(
                "Workday application context could not be identified with enough confidence"
            )

        page = pages[detection.document_index]
        mapping = self.classifier.classify_page(page)
        plan = self.planner.plan(mapping)
        step = self._classify_step(page, mapping_semantics={
            item.semantic for item in mapping.mappings
        })
        blocked_actions = self._blocked_actions(page.page_actions)
        return WorkdayPreparationResult(
            detection=detection,
            step=step,
            page=page,
            semantic_mapping=mapping,
            preparation_plan=plan,
            blocked_actions=blocked_actions,
            progression_allowed=False,
            live_writes_allowed=False,
            submission_allowed=False,
        )

    def _detect_document(
        self,
        page: BrowserPageSnapshot,
        *,
        index: int,
    ) -> WorkdayDetection:
        parsed = urlsplit(page.url)
        hostname = (parsed.hostname or "").casefold().rstrip(".")
        reasons: list[str] = []
        score = 0.0

        workday_host = self._is_workday_host(hostname)
        if workday_host:
            score += 0.65
            reasons.append("Workday external-career host")
        if "/job/" in parsed.path.casefold():
            score += 0.15
            reasons.append("Workday-style job path")
        if self._has_wizard_heading(page):
            score += 0.20
            reasons.append("Workday application-wizard heading")
        if self._has_progression_action(page):
            score += 0.15
            reasons.append("application-wizard progression control")
        if page.forms:
            score += 0.10
            reasons.append("application controls present")

        metadata = self._metadata(parsed, hostname)
        if metadata["source"]:
            score += 0.03
            reasons.append("source attribution metadata")

        confidence = min(score, 1.0)
        detected = (
            workday_host
            and confidence >= self.minimum_confidence
            and self._has_application_context(page)
        )
        return WorkdayDetection(
            detected=detected,
            confidence=confidence,
            reasons=reasons,
            document_index=index,
            document_url=page.url,
            embedded=index > 0,
            tenant=metadata["tenant"],
            site=metadata["site"],
            locale=metadata["locale"],
            requisition_id=metadata["requisition_id"],
            source=metadata["source"],
        )

    @classmethod
    def _classify_step(
        cls,
        page: BrowserPageSnapshot,
        *,
        mapping_semantics: set[ApplicationFieldSemantic],
    ) -> WorkdayWizardStep:
        headings = " | ".join(page.headings).casefold()
        action_text = " | ".join(cls._action_label(action) for action in page.page_actions)
        scores: dict[WorkdayStepCategory, tuple[float, list[str]]] = {}

        def add(category: WorkdayStepCategory, score: float, reason: str) -> None:
            current_score, current_reasons = scores.get(category, (0.0, []))
            scores[category] = (current_score + score, [*current_reasons, reason])

        if re.search(r"\b(?:sign in|create account|candidate home|log in)\b", headings):
            add(WorkdayStepCategory.ACCOUNT_ACCESS, 1.0, "account-access heading")

        if re.search(r"\b(?:final review|review your application|review application)\b", headings):
            add(WorkdayStepCategory.FINAL_REVIEW, 1.0, "final-review heading")
        if "submit" in action_text and not cls._editable_semantics(mapping_semantics):
            add(WorkdayStepCategory.FINAL_REVIEW, 0.85, "submit control with no editable semantics")

        if re.search(r"\b(?:terms|conditions|agreement|consent|privacy)\b", headings):
            add(WorkdayStepCategory.TERMS_CONSENT, 0.95, "terms/consent heading")
        if ApplicationFieldSemantic.CONSENT_ATTESTATION in mapping_semantics:
            add(WorkdayStepCategory.TERMS_CONSENT, 0.75, "consent semantic present")

        if re.search(
            r"\b(?:voluntary|self[- ]identif|disclosure|disability|veteran|eeo)\b",
            headings,
        ):
            add(
                WorkdayStepCategory.VOLUNTARY_DISCLOSURES,
                0.95,
                "voluntary-disclosure heading",
            )
        if ApplicationFieldSemantic.DEMOGRAPHIC_SELF_ID in mapping_semantics:
            add(
                WorkdayStepCategory.VOLUNTARY_DISCLOSURES,
                0.80,
                "demographic self-identification semantic present",
            )

        if re.search(r"\b(?:application questions?|questionnaire)\b", headings):
            add(
                WorkdayStepCategory.APPLICATION_QUESTIONS,
                0.95,
                "application-question heading",
            )
        question_semantics = {
            ApplicationFieldSemantic.NARRATIVE_QUESTION,
            ApplicationFieldSemantic.WORK_AUTHORIZATION,
            ApplicationFieldSemantic.SPONSORSHIP,
            ApplicationFieldSemantic.PRIOR_EMPLOYMENT,
            ApplicationFieldSemantic.SECURITY_CLEARANCE,
            ApplicationFieldSemantic.SALARY_EXPECTATION,
            ApplicationFieldSemantic.RELOCATION,
            ApplicationFieldSemantic.TRAVEL,
            ApplicationFieldSemantic.START_DATE,
        }
        if mapping_semantics & question_semantics:
            add(
                WorkdayStepCategory.APPLICATION_QUESTIONS,
                0.65,
                "application-question semantics present",
            )

        if re.search(r"\b(?:my experience|experience|education|work history)\b", headings):
            add(WorkdayStepCategory.EXPERIENCE, 0.95, "experience heading")
        if mapping_semantics & {
            ApplicationFieldSemantic.RESUME,
            ApplicationFieldSemantic.EDUCATION,
            ApplicationFieldSemantic.CERTIFICATIONS,
        }:
            add(WorkdayStepCategory.EXPERIENCE, 0.55, "experience/document semantics present")

        if re.search(
            r"\b(?:my information|contact information|personal information)\b",
            headings,
        ):
            add(
                WorkdayStepCategory.CONTACT_INFORMATION,
                0.95,
                "contact-information heading",
            )
        contact_semantics = {
            ApplicationFieldSemantic.FIRST_NAME,
            ApplicationFieldSemantic.LAST_NAME,
            ApplicationFieldSemantic.FULL_NAME,
            ApplicationFieldSemantic.EMAIL,
            ApplicationFieldSemantic.PHONE,
            ApplicationFieldSemantic.STREET_ADDRESS,
            ApplicationFieldSemantic.CITY,
            ApplicationFieldSemantic.REGION,
            ApplicationFieldSemantic.POSTAL_CODE,
            ApplicationFieldSemantic.COUNTRY,
        }
        if len(mapping_semantics & contact_semantics) >= 2:
            add(
                WorkdayStepCategory.CONTACT_INFORMATION,
                0.70,
                "multiple contact-information semantics present",
            )

        if (
            ApplicationFieldSemantic.RESUME in mapping_semantics
            and re.search(r"\b(?:apply|resume|résumé|cv)\b", headings)
        ):
            add(WorkdayStepCategory.RESUME, 0.85, "resume/application heading and upload")

        if not scores:
            return WorkdayWizardStep(
                category=WorkdayStepCategory.UNKNOWN,
                confidence=0.0,
                reasons=["no deterministic wizard-step signal matched"],
            )

        category, (raw_score, reasons) = max(
            scores.items(), key=lambda item: item[1][0]
        )
        return WorkdayWizardStep(
            category=category,
            confidence=min(raw_score, 1.0),
            reasons=reasons,
        )

    @classmethod
    def _blocked_actions(
        cls,
        actions: list[BrowserPageActionDescriptor],
    ) -> list[WorkdayBlockedAction]:
        blocked: list[WorkdayBlockedAction] = []
        seen: set[tuple[str, str]] = set()
        for action in actions:
            operation = cls._blocked_operation(action)
            if operation is None:
                continue
            key = (operation.value, action.selector)
            if key in seen:
                continue
            seen.add(key)
            blocked.append(
                WorkdayBlockedAction(
                    operation=operation,
                    control=action,
                    reason=cls._blocked_reason(operation),
                )
            )
        return blocked

    @classmethod
    def _blocked_operation(
        cls,
        action: BrowserPageActionDescriptor,
    ) -> WorkdayBlockedOperation | None:
        label = cls._action_label(action)
        if "linkedin" in label and ("apply" in label or "sign in" in label):
            return WorkdayBlockedOperation.APPLY_WITH_LINKEDIN
        if "save for later" in label or label == "save":
            return WorkdayBlockedOperation.SAVE_FOR_LATER
        if "create account" in label or "register" in label:
            return WorkdayBlockedOperation.CREATE_ACCOUNT
        if re.search(r"\b(?:sign in|log in)\b", label):
            return WorkdayBlockedOperation.SIGN_IN
        if "submit" in label:
            return WorkdayBlockedOperation.SUBMIT
        if re.search(r"\b(?:next|continue)\b", label):
            return WorkdayBlockedOperation.NEXT
        if re.search(r"\b(?:review|apply)\b", label):
            return WorkdayBlockedOperation.OTHER_PROGRESSION
        return None

    @staticmethod
    def _blocked_reason(operation: WorkdayBlockedOperation) -> str:
        reasons = {
            WorkdayBlockedOperation.NEXT: (
                "Workday may persist or update a candidate draft when the wizard advances"
            ),
            WorkdayBlockedOperation.SAVE_FOR_LATER: (
                "saving a draft is an employer-side write and is disabled in the prototype"
            ),
            WorkdayBlockedOperation.SIGN_IN: (
                "Candidate Home authentication is outside the prototype boundary"
            ),
            WorkdayBlockedOperation.CREATE_ACCOUNT: (
                "Candidate Home account creation is outside the prototype boundary"
            ),
            WorkdayBlockedOperation.APPLY_WITH_LINKEDIN: (
                "LinkedIn account automation is outside the JobOps ATS automation scope"
            ),
            WorkdayBlockedOperation.SUBMIT: (
                "final application submission remains behind a separate explicit gate"
            ),
            WorkdayBlockedOperation.OTHER_PROGRESSION: (
                "stateful Workday progression is disabled until write behavior is modeled"
            ),
        }
        return reasons[operation]

    @classmethod
    def _has_application_context(cls, page: BrowserPageSnapshot) -> bool:
        return bool(
            page.forms
            or cls._has_wizard_heading(page)
            or cls._has_progression_action(page)
        )

    @staticmethod
    def _has_wizard_heading(page: BrowserPageSnapshot) -> bool:
        text = " | ".join(page.headings).casefold()
        return bool(
            re.search(
                r"\b(?:my information|my experience|application questions?|questionnaire|"
                r"voluntary|self[- ]identif|terms|agreement|final review|review your application|"
                r"resume|résumé|candidate home|create account)\b",
                text,
            )
        )

    @classmethod
    def _has_progression_action(cls, page: BrowserPageSnapshot) -> bool:
        return any(cls._blocked_operation(action) is not None for action in page.page_actions)

    @staticmethod
    def _editable_semantics(
        semantics: set[ApplicationFieldSemantic],
    ) -> set[ApplicationFieldSemantic]:
        return semantics - {
            ApplicationFieldSemantic.SUBMIT_CONTROL,
            ApplicationFieldSemantic.UNKNOWN,
        }

    @staticmethod
    def _action_label(action: BrowserPageActionDescriptor) -> str:
        return (action.accessible_name or action.text or "").strip().casefold()

    @classmethod
    def _is_workday_host(cls, hostname: str) -> bool:
        return any(
            hostname == suffix or hostname.endswith(f".{suffix}")
            for suffix in _WORKDAY_HOST_SUFFIXES
        )

    @classmethod
    def _metadata(cls, parsed: object, hostname: str) -> dict[str, str | None]:
        path = parsed.path
        segments = [segment for segment in path.split("/") if segment]
        locale: str | None = None
        site: str | None = None
        if segments and _LOCALE.match(segments[0]):
            locale = segments[0]
            segments = segments[1:]
        if segments:
            site = segments[0]

        requisition_id: str | None = None
        if segments:
            match = _REQUISITION_SUFFIX.search(segments[-1])
            if match:
                requisition_id = match.group(1)

        query = parse_qs(parsed.query)
        source = query.get("source", [None])[0]
        tenant = hostname.split(".", 1)[0] if cls._is_workday_host(hostname) else None
        return {
            "tenant": tenant,
            "site": site,
            "locale": locale,
            "requisition_id": requisition_id,
            "source": source,
        }
