import hashlib
import json
from collections.abc import Mapping

from playwright.sync_api import Page

from jobops.browser.live_preparer import LiveApplicationPreparer
from jobops.db.approval_repository import ApprovalRepository
from jobops.db.flagship_repository import FlagshipReadinessRepository
from jobops.models.application_execution import (
    ApplicationPreparationBlock,
    ApplicationPreparationBlocker,
    ApplicationPreparationResult,
    ApplicationPreparationStatus,
    FlagshipApplicationExecutionResult,
)
from jobops.models.approval import ApprovalStatus
from jobops.models.browser_audit import BrowserAuditManifest, BrowserAuditVendor
from jobops.models.candidate import CandidateProfile
from jobops.models.flagship_run import FlagshipReadiness
from jobops.models.submission import PreparedSubmissionState
from jobops.submissions.service import SubmissionReadinessEvaluator


class FlagshipApplicationExecutionService:
    """Bind a latest-run Flagship job to one controlled live ATS preparation state."""

    def __init__(
        self,
        readiness_repository: FlagshipReadinessRepository,
        approval_repository: ApprovalRepository,
        *,
        readiness_evaluator: SubmissionReadinessEvaluator | None = None,
    ) -> None:
        self.readiness_repository = readiness_repository
        self.approval_repository = approval_repository
        self.readiness_evaluator = readiness_evaluator or SubmissionReadinessEvaluator()

    def prepare_live(
        self,
        *,
        profile_id: str,
        application_id: str,
        job_id: str,
        vendor: BrowserAuditVendor,
        candidate: CandidateProfile,
        page: Page,
        browser_session_id: str | None = None,
        audit_manifest: BrowserAuditManifest | None = None,
        file_paths: Mapping[str, str] | None = None,
    ) -> FlagshipApplicationExecutionResult:
        summary = self.readiness_repository.latest(profile_id)
        if summary is None:
            return self._blocked(
                application_id=application_id,
                job_id=job_id,
                vendor=vendor,
                code=ApplicationPreparationBlocker.JOB_NOT_IN_LATEST_RUN,
                reason="No durable Flagship run exists for this search profile.",
            )

        if summary.candidate_id != candidate.candidate_id:
            return self._blocked(
                application_id=application_id,
                job_id=job_id,
                vendor=vendor,
                run_id=summary.run_id,
                code=ApplicationPreparationBlocker.CANDIDATE_MISMATCH,
                reason="Candidate does not match the owner of the latest Flagship run.",
            )

        prepared_snapshot = next(
            (item for item in summary.prepared_jobs if item.job_id == job_id),
            None,
        )
        if prepared_snapshot is None:
            return self._blocked(
                application_id=application_id,
                job_id=job_id,
                vendor=vendor,
                run_id=summary.run_id,
                code=ApplicationPreparationBlocker.JOB_NOT_IN_LATEST_RUN,
                reason="Job is not present in the latest Flagship run.",
            )

        if prepared_snapshot.readiness is not FlagshipReadiness.READY:
            return self._blocked(
                application_id=application_id,
                job_id=job_id,
                vendor=vendor,
                run_id=summary.run_id,
                code=ApplicationPreparationBlocker.FLAGSHIP_REVIEW_REQUIRED,
                reason="Latest Flagship snapshot still requires human review for this job.",
            )

        pending_approvals = self.approval_repository.count(
            status=ApprovalStatus.PENDING,
            job_id=job_id,
        )
        if pending_approvals:
            return self._blocked(
                application_id=application_id,
                job_id=job_id,
                vendor=vendor,
                run_id=summary.run_id,
                code=ApplicationPreparationBlocker.PENDING_APPROVALS,
                reason=(
                    f"{pending_approvals} approval item(s) remain pending for this job."
                ),
            )

        approved = self.approval_repository.list(
            status=ApprovalStatus.APPROVED,
            job_id=job_id,
            limit=100,
            offset=0,
        )
        preparation = LiveApplicationPreparer(page).prepare(
            application_id=application_id,
            job_id=job_id,
            vendor=vendor,
            candidate=candidate,
            approvals=approved,
            file_paths=file_paths,
        )
        if preparation.status is not ApplicationPreparationStatus.PREPARED:
            return FlagshipApplicationExecutionResult(
                run_id=summary.run_id,
                preparation=preparation,
            )

        if (
            audit_manifest is not None
            and audit_manifest.vendor is not vendor
        ):
            preparation = preparation.model_copy(
                update={
                    "status": ApplicationPreparationStatus.BLOCKED,
                    "blockers": [
                        *preparation.blockers,
                        ApplicationPreparationBlock(
                            code=ApplicationPreparationBlocker.AUDIT_CONTEXT_MISMATCH,
                            reason=(
                                "Post-preparation audit vendor does not match "
                                "the prepared ATS vendor."
                            ),
                        ),
                    ],
                    "prepared_payload_sha256": None,
                }
            )
            return FlagshipApplicationExecutionResult(
                run_id=summary.run_id,
                preparation=preparation,
            )

        assert preparation.submit_selector is not None
        assert preparation.prepared_payload_sha256 is not None

        submit_locator = page.locator(preparation.submit_selector)
        submit_count = submit_locator.count()
        submit_enabled = submit_count == 1 and submit_locator.is_enabled()
        submit_control_sha256 = self._submit_control_sha256(
            page,
            preparation.submit_selector,
        )
        document_url_sha256 = hashlib.sha256(page.url.encode("utf-8")).hexdigest()

        state = PreparedSubmissionState(
            application_id=application_id,
            job_id=job_id,
            vendor=vendor,
            prepared_payload_sha256=preparation.prepared_payload_sha256,
            audit_run_id=audit_manifest.run_id if audit_manifest is not None else None,
            audit_created_at=(
                audit_manifest.created_at if audit_manifest is not None else None
            ),
            browser_session_id=browser_session_id,
            document_url_sha256=document_url_sha256,
            submit_selector=preparation.submit_selector,
            submit_control_sha256=submit_control_sha256,
            pending_review=0,
            submit_control_count=submit_count,
            submit_control_enabled=submit_enabled,
            ats_context_matches=(
                audit_manifest is None or audit_manifest.vendor is vendor
            ),
            browser_state_matches=True,
        )
        readiness = self.readiness_evaluator.evaluate(state)
        return FlagshipApplicationExecutionResult(
            run_id=summary.run_id,
            preparation=preparation,
            prepared_state=state,
            readiness=readiness,
        )

    @staticmethod
    def _submit_control_sha256(page: Page, selector: str) -> str:
        locator = page.locator(selector)
        if locator.count() != 1:
            payload = {"selector": selector, "count": locator.count()}
        else:
            payload = locator.evaluate(
                """el => ({
                    selector: null,
                    tag: el.tagName.toLowerCase(),
                    id: el.id || null,
                    name: el.getAttribute("name"),
                    type: el.getAttribute("type"),
                    disabled: Boolean(el.disabled || el.getAttribute("aria-disabled") === "true"),
                    text: (\n                        el.innerText || el.textContent || el.value || ""\n                    ).replace(/\s+/g, " ").trim()
                })"""
            )
            payload["selector"] = selector
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _blocked(
        *,
        application_id: str,
        job_id: str,
        vendor: BrowserAuditVendor,
        code: ApplicationPreparationBlocker,
        reason: str,
        run_id: str | None = None,
    ) -> FlagshipApplicationExecutionResult:
        return FlagshipApplicationExecutionResult(
            run_id=run_id,
            preparation=ApplicationPreparationResult(
                application_id=application_id,
                job_id=job_id,
                vendor=vendor,
                status=ApplicationPreparationStatus.BLOCKED,
                blockers=[
                    ApplicationPreparationBlock(
                        code=code,
                        reason=reason,
                    )
                ],
            ),
        )
