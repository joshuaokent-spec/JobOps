import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path

from playwright.sync_api import Page

from jobops.browser.base import BrowserPolicyError
from jobops.browser.greenhouse import GreenhouseBrowserAdapter
from jobops.browser.lever import LeverBrowserAdapter
from jobops.browser.playwright_inspector import PlaywrightBrowserInspector
from jobops.models.application_execution import (
    ApplicationFieldValueSource,
    ApplicationFieldWrite,
    ApplicationPreparationBlock,
    ApplicationPreparationBlocker,
    ApplicationPreparationResult,
    ApplicationPreparationStatus,
)
from jobops.models.application_question import HandlingRoute
from jobops.models.approval import ApprovalItem, ApprovalStatus
from jobops.models.browser import BrowserFieldDescriptor, BrowserFieldKind
from jobops.models.browser_audit import BrowserAuditVendor
from jobops.models.candidate import CandidateFact, CandidateProfile
from jobops.models.form_mapping import (
    ApplicationFieldSemantic,
    SemanticFieldMapping,
    SemanticPageMapping,
)


class LiveApplicationPreparer:
    """Write only resolved, reviewed values into an already-owned live ATS page."""

    def __init__(
        self,
        page: Page,
        *,
        inspector: PlaywrightBrowserInspector | None = None,
    ) -> None:
        self.page = page
        self.inspector = inspector or PlaywrightBrowserInspector()

    def prepare(
        self,
        *,
        application_id: str,
        job_id: str,
        vendor: BrowserAuditVendor,
        candidate: CandidateProfile,
        approvals: Iterable[ApprovalItem] = (),
        file_paths: Mapping[str, str] | None = None,
    ) -> ApplicationPreparationResult:
        if vendor is BrowserAuditVendor.WORKDAY:
            return self._unsupported_workday(application_id, job_id)
        if vendor not in {BrowserAuditVendor.GREENHOUSE, BrowserAuditVendor.LEVER}:
            return self._unsupported_vendor(application_id, job_id, vendor)

        try:
            mapping = self._mapping_for_vendor(vendor)
        except BrowserPolicyError as exc:
            return ApplicationPreparationResult(
                application_id=application_id,
                job_id=job_id,
                vendor=vendor,
                status=ApplicationPreparationStatus.BLOCKED,
                blockers=[
                    ApplicationPreparationBlock(
                        code=ApplicationPreparationBlocker.ATS_DETECTION_FAILED,
                        reason=str(exc),
                    )
                ],
            )

        verified_facts = {
            fact.key.strip().casefold(): fact
            for fact in candidate.facts
            if fact.verified and fact.key.strip()
        }
        approved_answers = self._approved_answers(job_id, approvals)
        files = {
            key.strip().casefold(): value
            for key, value in (file_paths or {}).items()
            if key.strip() and value.strip()
        }

        writes: list[ApplicationFieldWrite] = []
        blockers: list[ApplicationPreparationBlock] = []
        payload_entries: list[dict[str, str]] = []
        submit_selectors: list[str] = []

        for item in mapping.mappings:
            if item.semantic is ApplicationFieldSemantic.SUBMIT_CONTROL:
                submit_selectors.append(item.field.selector)
                continue

            resolution = self._resolve(
                item,
                verified_facts=verified_facts,
                approved_answers=approved_answers,
                file_paths=files,
            )
            if resolution is None:
                blocker = self._missing_resolution_blocker(item)
                if blocker is not None:
                    blockers.append(blocker)
                continue

            value, source = resolution
            try:
                self._write(item.field, value)
            except (ValueError, OSError, RuntimeError) as exc:
                blockers.append(
                    ApplicationPreparationBlock(
                        code=ApplicationPreparationBlocker.FIELD_WRITE_FAILED,
                        selector=item.field.selector,
                        semantic=item.semantic,
                        reason=f"Field could not be prepared safely: {exc}",
                    )
                )
                continue

            writes.append(
                ApplicationFieldWrite(
                    selector=item.field.selector,
                    semantic=item.semantic,
                    source=source,
                    required=item.field.required,
                )
            )
            payload_entries.append(
                {
                    "selector": item.field.selector,
                    "semantic": item.semantic.value,
                    "source": source.value,
                    "value_sha256": self._value_sha256(value),
                }
            )

        unique_submit_selectors = list(dict.fromkeys(submit_selectors))
        if len(unique_submit_selectors) != 1:
            blockers.append(
                ApplicationPreparationBlock(
                    code=ApplicationPreparationBlocker.SUBMIT_CONTROL_NOT_UNIQUE,
                    reason=(
                        "Prepared ATS document must expose exactly one final submit control; "
                        f"found {len(unique_submit_selectors)}."
                    ),
                )
            )

        status = (
            ApplicationPreparationStatus.PREPARED
            if not blockers
            else ApplicationPreparationStatus.BLOCKED
        )
        payload_sha256 = (
            self._payload_sha256(payload_entries)
            if status is ApplicationPreparationStatus.PREPARED
            else None
        )
        return ApplicationPreparationResult(
            application_id=application_id,
            job_id=job_id,
            vendor=vendor,
            status=status,
            filled_fields=len(writes),
            writes=writes,
            blockers=blockers,
            submit_selector=(
                unique_submit_selectors[0]
                if len(unique_submit_selectors) == 1
                else None
            ),
            submit_control_count=len(unique_submit_selectors),
            prepared_payload_sha256=payload_sha256,
            submission_allowed=False,
        )

    def _mapping_for_vendor(
        self,
        vendor: BrowserAuditVendor,
    ) -> SemanticPageMapping:
        documents = self.inspector.snapshot_live_page_documents(self.page)
        if vendor is BrowserAuditVendor.GREENHOUSE:
            return GreenhouseBrowserAdapter(
                inspector=self.inspector
            ).prepare_documents(documents).semantic_mapping
        if vendor is BrowserAuditVendor.LEVER:
            return LeverBrowserAdapter(
                inspector=self.inspector
            ).prepare_documents(documents).semantic_mapping
        raise ValueError(f"unsupported ATS vendor: {vendor.value}")

    @staticmethod
    def _approved_answers(
        job_id: str,
        approvals: Iterable[ApprovalItem],
    ) -> dict[str, str]:
        answers: dict[str, str] = {}
        conflicts: set[str] = set()
        for item in approvals:
            if item.job_id != job_id or item.status is not ApprovalStatus.APPROVED:
                continue
            if not item.final_answer or not item.final_answer.strip():
                continue
            key = LiveApplicationPreparer._normalize_question(item.question)
            answer = item.final_answer.strip()
            existing = answers.get(key)
            if existing is not None and existing != answer:
                conflicts.add(key)
                continue
            answers[key] = answer
        for key in conflicts:
            answers.pop(key, None)
        return answers

    @staticmethod
    def _resolve(
        mapping: SemanticFieldMapping,
        *,
        verified_facts: Mapping[str, CandidateFact],
        approved_answers: Mapping[str, str],
        file_paths: Mapping[str, str],
    ) -> tuple[object, ApplicationFieldValueSource] | None:
        if mapping.field.kind in {BrowserFieldKind.HIDDEN, BrowserFieldKind.BUTTON}:
            return None
        if mapping.ambiguous or mapping.semantic is ApplicationFieldSemantic.UNKNOWN:
            return None

        if mapping.route is HandlingRoute.AUTO_FILL:
            fact_key = (mapping.fact_key or "").strip().casefold()
            if mapping.semantic is ApplicationFieldSemantic.RESUME:
                path = file_paths.get("selected_resume") or file_paths.get("resume")
                if path:
                    return path, ApplicationFieldValueSource.APPROVED_FILE
                return None
            fact = verified_facts.get(fact_key)
            if fact is None:
                return None
            return fact.value, ApplicationFieldValueSource.VERIFIED_FACT

        if mapping.route in {
            HandlingRoute.DRAFT_WITH_REVIEW,
            HandlingRoute.HUMAN_REVIEW,
        }:
            question = LiveApplicationPreparer._normalize_question(
                mapping.question_text
                or mapping.field.label
                or mapping.field.accessible_name
                or mapping.field.name
                or ""
            )
            answer = approved_answers.get(question)
            if answer is not None:
                return answer, ApplicationFieldValueSource.APPROVED_REVIEW

            if mapping.semantic is ApplicationFieldSemantic.COVER_LETTER:
                path = file_paths.get("cover_letter")
                if path and mapping.field.kind is BrowserFieldKind.FILE:
                    return path, ApplicationFieldValueSource.APPROVED_FILE
            return None

        return None

    @staticmethod
    def _missing_resolution_blocker(
        mapping: SemanticFieldMapping,
    ) -> ApplicationPreparationBlock | None:
        if mapping.field.kind in {BrowserFieldKind.HIDDEN, BrowserFieldKind.BUTTON}:
            return None
        if mapping.ambiguous:
            return ApplicationPreparationBlock(
                code=ApplicationPreparationBlocker.AMBIGUOUS_FIELD,
                selector=mapping.field.selector,
                semantic=mapping.semantic,
                reason="Ambiguous semantic mapping must be reviewed before browser preparation.",
            )
        if mapping.semantic is ApplicationFieldSemantic.UNKNOWN:
            return ApplicationPreparationBlock(
                code=ApplicationPreparationBlocker.UNKNOWN_FIELD,
                selector=mapping.field.selector,
                semantic=mapping.semantic,
                reason="Unknown application field must be resolved before final readiness.",
            )
        if mapping.route in {
            HandlingRoute.DRAFT_WITH_REVIEW,
            HandlingRoute.HUMAN_REVIEW,
        }:
            return ApplicationPreparationBlock(
                code=ApplicationPreparationBlocker.MISSING_APPROVED_REVIEW,
                selector=mapping.field.selector,
                semantic=mapping.semantic,
                reason="Review-required field has no approved final answer.",
            )
        if mapping.semantic is ApplicationFieldSemantic.RESUME:
            return ApplicationPreparationBlock(
                code=ApplicationPreparationBlocker.FILE_NOT_AVAILABLE,
                selector=mapping.field.selector,
                semantic=mapping.semantic,
                reason="Selected resume file is not available to the live browser runtime.",
            )
        if mapping.field.required:
            return ApplicationPreparationBlock(
                code=ApplicationPreparationBlocker.MISSING_VERIFIED_FACT,
                selector=mapping.field.selector,
                semantic=mapping.semantic,
                reason="Required Green-band field has no verified candidate fact.",
            )
        return None

    def _write(self, field: BrowserFieldDescriptor, value: object) -> None:
        locator = self.page.locator(field.selector)
        if locator.count() != 1:
            raise ValueError("field selector no longer resolves to exactly one element")
        if field.disabled or not locator.is_enabled():
            raise ValueError("field is disabled")

        if field.kind in {
            BrowserFieldKind.TEXT,
            BrowserFieldKind.EMAIL,
            BrowserFieldKind.TELEPHONE,
            BrowserFieldKind.URL,
            BrowserFieldKind.NUMBER,
            BrowserFieldKind.DATE,
            BrowserFieldKind.TEXTAREA,
        }:
            locator.fill(self._text_value(value))
            return

        if field.kind is BrowserFieldKind.SELECT:
            option_value = self._select_option(field, value)
            locator.select_option(value=option_value)
            return

        if field.kind is BrowserFieldKind.CHECKBOX:
            checked = self._boolean_value(value)
            if checked:
                locator.check()
            else:
                locator.uncheck()
            return

        if field.kind is BrowserFieldKind.FILE:
            path = Path(self._text_value(value))
            if not path.is_file():
                raise ValueError("approved file path does not exist")
            locator.set_input_files(str(path))
            return

        if field.kind is BrowserFieldKind.RADIO:
            raise ValueError("radio-group execution is not supported until option identity is sealed")

        raise ValueError(f"unsupported browser field kind: {field.kind.value}")

    @staticmethod
    def _select_option(field: BrowserFieldDescriptor, value: object) -> str:
        wanted = LiveApplicationPreparer._text_value(value).strip().casefold()
        for option in field.options:
            if option.disabled:
                continue
            if option.value.strip().casefold() == wanted:
                return option.value
        for option in field.options:
            if option.disabled:
                continue
            if option.label.strip().casefold() == wanted:
                return option.value
        raise ValueError("approved value does not match an enabled select option")

    @staticmethod
    def _boolean_value(value: object) -> bool:
        if isinstance(value, bool):
            return value
        normalized = LiveApplicationPreparer._text_value(value).strip().casefold()
        if normalized in {"yes", "true", "1", "checked", "agree", "agreed"}:
            return True
        if normalized in {"no", "false", "0", "unchecked", "decline", "declined"}:
            return False
        raise ValueError("approved checkbox value is not an explicit boolean choice")

    @staticmethod
    def _text_value(value: object) -> str:
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)
        return str(value)

    @staticmethod
    def _normalize_question(value: str) -> str:
        return " ".join(value.split()).casefold()

    @staticmethod
    def _value_sha256(value: object) -> str:
        encoded = LiveApplicationPreparer._text_value(value).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _payload_sha256(entries: list[dict[str, str]]) -> str:
        payload = json.dumps(
            entries,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _unsupported_workday(
        application_id: str,
        job_id: str,
    ) -> ApplicationPreparationResult:
        return ApplicationPreparationResult(
            application_id=application_id,
            job_id=job_id,
            vendor=BrowserAuditVendor.WORKDAY,
            status=ApplicationPreparationStatus.UNSUPPORTED,
            blockers=[
                ApplicationPreparationBlock(
                    code=ApplicationPreparationBlocker.WORKDAY_STATEFUL_PROGRESSION,
                    reason=(
                        "Workday execution remains review-only because wizard progression "
                        "can persist employer-side draft state."
                    ),
                )
            ],
        )

    @staticmethod
    def _unsupported_vendor(
        application_id: str,
        job_id: str,
        vendor: BrowserAuditVendor,
    ) -> ApplicationPreparationResult:
        return ApplicationPreparationResult(
            application_id=application_id,
            job_id=job_id,
            vendor=vendor,
            status=ApplicationPreparationStatus.UNSUPPORTED,
            blockers=[
                ApplicationPreparationBlock(
                    code=ApplicationPreparationBlocker.UNSUPPORTED_VENDOR,
                    reason=f"Live application preparation is not supported for {vendor.value}.",
                )
            ],
        )
