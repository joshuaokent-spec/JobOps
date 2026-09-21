from datetime import UTC, datetime

from playwright.sync_api import sync_playwright

from jobops.browser.audit import BrowserAuditBundleWriter
from jobops.browser.audit_store import LocalBrowserAuditArtifactStore
from jobops.flagship import FlagshipApplicationExecutionService
from jobops.models.application_execution import (
    ApplicationPreparationBlocker,
    ApplicationPreparationStatus,
)
from jobops.models.application_question import HandlingRoute, QuestionCategory, ReviewBand
from jobops.models.approval import ApprovalItem, ApprovalReason, ApprovalStatus
from jobops.models.browser_audit import BrowserAuditVendor
from jobops.models.candidate import CandidateFact, CandidateProfile
from jobops.models.flagship_readiness import (
    FlagshipPreparedSnapshot,
    FlagshipReadinessSummary,
)
from jobops.models.flagship_run import FlagshipReadiness
from jobops.models.submission import (
    SubmissionAuthorizationStatus,
    SubmitAuthorizationCreate,
)
from jobops.submissions import SubmissionGate


_GREENHOUSE = """
<!doctype html>
<html>
<body>
<form id="application_form" method="post" action="/applications"
      onsubmit="window.__submitted = (window.__submitted || 0) + 1; return false;">
  <label for="first">First name</label>
  <input id="first" name="job_application[first_name]" required>
  <label for="last">Last name</label>
  <input id="last" name="job_application[last_name]" required>
  <label for="email">Email</label>
  <input id="email" type="email" name="job_application[email]" required>
  <label for="resume">Resume</label>
  <input id="resume" type="file" name="job_application[resume]" required>
  <label for="sponsor">Will you now or in the future require visa sponsorship?</label>
  <select id="sponsor" name="job_application[answers_attributes][0][text_value]" required>
    <option value="">Choose</option>
    <option value="yes">Yes</option>
    <option value="no">No</option>
  </select>
  <button type="submit" id="submit-app">Submit application</button>
</form>
</body>
</html>
"""


class _ReadinessRepository:
    def __init__(self, summary: FlagshipReadinessSummary | None):
        self.summary = summary

    def latest(self, profile_id: str) -> FlagshipReadinessSummary | None:
        if self.summary is None or self.summary.profile_id != profile_id:
            return None
        return self.summary


class _AuthorizationRepository:
    def __init__(self) -> None:
        self.authorizations = {}

    def create_authorization(self, item):
        self.authorizations[item.authorization_id] = item
        return item

    def get_blocking_attempt(self, application_id: str):
        return None


class _ApprovalRepository:
    def __init__(self, approvals: list[ApprovalItem] | None = None, pending: int = 0):
        self.approvals = approvals or []
        self.pending = pending

    def count(self, *, status=None, job_id=None) -> int:
        if status is ApprovalStatus.PENDING:
            return self.pending
        return len(
            [
                item
                for item in self.approvals
                if (status is None or item.status is status)
                and (job_id is None or item.job_id == job_id)
            ]
        )

    def list(self, *, status=None, job_id=None, limit=50, offset=0):
        items = [
            item
            for item in self.approvals
            if (status is None or item.status is status)
            and (job_id is None or item.job_id == job_id)
        ]
        return items[offset : offset + limit]


def _summary(
    *,
    job_id: str = "job-1",
    readiness: FlagshipReadiness = FlagshipReadiness.READY,
) -> FlagshipReadinessSummary:
    now = datetime.now(UTC)
    snapshot = FlagshipPreparedSnapshot(
        run_id="run-1",
        job_id=job_id,
        rank=1,
        score=88.0,
        resume_family_id="data",
        resume_selection_score=90.0,
        readiness=readiness,
        evidence_ids=["project-1"],
    )
    return FlagshipReadinessSummary(
        run_id="run-1",
        profile_id="profile-1",
        candidate_id="me",
        started_at=now,
        completed_at=now,
        total_examined=1,
        total_hard_eligible=1,
        total_hard_rejected=0,
        total_fit_eligible=1,
        total_fit_rejected=0,
        prepared_count=1,
        ready_count=1 if readiness is FlagshipReadiness.READY else 0,
        review_required_count=(
            1 if readiness is FlagshipReadiness.REVIEW_REQUIRED else 0
        ),
        prepared_jobs=[snapshot],
    )


def _candidate() -> CandidateProfile:
    return CandidateProfile(
        candidate_id="me",
        facts=[
            CandidateFact(
                key="first_name",
                value="Casey",
                evidence=["profile:first-name"],
                verified=True,
            ),
            CandidateFact(
                key="last_name",
                value="Candidate",
                evidence=["profile:last-name"],
                verified=True,
            ),
            CandidateFact(
                key="email",
                value="casey@example.com",
                evidence=["profile:email"],
                verified=True,
            ),
        ],
    )


def _approved_sponsorship() -> ApprovalItem:
    now = datetime.now(UTC)
    return ApprovalItem(
        approval_id="approval-1",
        job_id="job-1",
        family_id="data",
        question="Will you now or in the future require visa sponsorship?",
        category=QuestionCategory.LEGAL_SENSITIVE,
        route=HandlingRoute.HUMAN_REVIEW,
        review_band=ReviewBand.RED,
        reason=ApprovalReason.LEGAL_SENSITIVE,
        status=ApprovalStatus.APPROVED,
        proposed_answer="No",
        final_answer="No",
        reviewer="candidate",
        decision_note="Reviewed.",
        created_at=now,
        updated_at=now,
        reviewed_at=now,
        approved_for_preparation=True,
        submitted=False,
    )


def test_flagship_execution_rejects_job_outside_latest_run() -> None:
    service = FlagshipApplicationExecutionService(
        _ReadinessRepository(_summary(job_id="different-job")),
        _ApprovalRepository(),
    )
    result = service.prepare_live(
        profile_id="profile-1",
        application_id="application-1",
        job_id="job-1",
        vendor=BrowserAuditVendor.GREENHOUSE,
        candidate=_candidate(),
        page=None,  # type: ignore[arg-type]
    )

    assert result.preparation.status is ApplicationPreparationStatus.BLOCKED
    assert result.preparation.blockers[0].code is (
        ApplicationPreparationBlocker.JOB_NOT_IN_LATEST_RUN
    )
    assert result.prepared_state is None


def test_flagship_execution_blocks_pending_approvals_before_browser_writes() -> None:
    service = FlagshipApplicationExecutionService(
        _ReadinessRepository(_summary()),
        _ApprovalRepository(pending=2),
    )
    result = service.prepare_live(
        profile_id="profile-1",
        application_id="application-1",
        job_id="job-1",
        vendor=BrowserAuditVendor.GREENHOUSE,
        candidate=_candidate(),
        page=None,  # type: ignore[arg-type]
    )

    assert result.preparation.status is ApplicationPreparationStatus.BLOCKED
    assert result.preparation.blockers[0].code is (
        ApplicationPreparationBlocker.PENDING_APPROVALS
    )


def test_flagship_execution_seals_ready_greenhouse_state_without_submitting(
    tmp_path,
) -> None:
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF fixture")

    audit_root = tmp_path / "audit"
    service = FlagshipApplicationExecutionService(
        _ReadinessRepository(_summary()),
        _ApprovalRepository([_approved_sponsorship()]),
        audit_writer=BrowserAuditBundleWriter(
            LocalBrowserAuditArtifactStore(audit_root)
        ),
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(_GREENHOUSE)
            result = service.prepare_live(
                profile_id="profile-1",
                application_id="application-1",
                job_id="job-1",
                vendor=BrowserAuditVendor.GREENHOUSE,
                candidate=_candidate(),
                page=page,
                browser_session_id="session-1",
                file_paths={"selected_resume": str(resume)},
            )

            assert result.preparation.status is ApplicationPreparationStatus.PREPARED
            assert result.prepared_state is not None
            assert result.prepared_state.audit_run_id is not None
            assert result.prepared_state.browser_session_id == "session-1"
            assert result.prepared_state.submit_selector == "#submit-app"
            assert result.readiness is not None
            assert result.readiness.ready is True
            assert result.readiness.blockers == []
            assert (audit_root / result.prepared_state.audit_run_id / "manifest.json").is_file()

            gate = SubmissionGate(_AuthorizationRepository())
            authorization = gate.authorize(
                SubmitAuthorizationCreate(
                    state=result.prepared_state,
                    authorized_by="candidate",
                    note="Fresh explicit authorization for controlled fixture.",
                ),
                now=datetime.now(UTC),
            )
            assert authorization.status is SubmissionAuthorizationStatus.ACTIVE
            assert authorization.state_fingerprint == result.readiness.state_fingerprint
            assert page.evaluate("window.__submitted || 0") == 0
        finally:
            browser.close()
