from datetime import UTC, datetime

from playwright.sync_api import sync_playwright

from jobops.browser import LiveApplicationPreparer
from jobops.browser.playwright_inspector import PlaywrightBrowserInspector
from jobops.models.application_execution import (
    ApplicationPreparationBlocker,
    ApplicationPreparationStatus,
)
from jobops.models.application_question import HandlingRoute, QuestionCategory, ReviewBand
from jobops.models.approval import (
    ApprovalItem,
    ApprovalReason,
    ApprovalStatus,
)
from jobops.models.browser_audit import BrowserAuditVendor
from jobops.models.candidate import CandidateFact, CandidateProfile


_GREENHOUSE = """
<!doctype html>
<html>
<body>
<form id="application_form" method="post" action="/applications"
      onsubmit="window.__submitted = (window.__submitted || 0) + 1; return false;">
  <input type="hidden" name="csrf" value="server-token">

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

  <button type="button" id="help">Help</button>
  <button type="submit" id="submit-app">Submit application</button>
</form>
</body>
</html>
"""


_LEVER = """
<!doctype html>
<html>
<body>
<form id="application-form" method="post"
      action="https://jobs.lever.co/acme/5c8c534e-fa04-45a8-b1b4-99d28f34de0d/apply"
      onsubmit="window.__submitted = (window.__submitted || 0) + 1; return false;">
  <label for="resume">Resume/CV</label>
  <input id="resume" type="file" name="resume" required>

  <label for="name">Full name</label>
  <input id="name" name="name" required>

  <label for="email">Email</label>
  <input id="email" type="email" name="email" required>

  <label for="why">Why are you interested in this role?</label>
  <textarea id="why" name="customQuestions[why]" required></textarea>

  <button type="submit" id="submit-app">Submit application</button>
</form>
</body>
</html>
"""


def _fact(key: str, value: object) -> CandidateFact:
    return CandidateFact(
        key=key,
        value=value,
        evidence=[f"source:{key}"],
        verified=True,
    )


def _candidate(*facts: CandidateFact) -> CandidateProfile:
    return CandidateProfile(candidate_id="me", facts=list(facts))


def _approved(job_id: str, question: str, answer: str) -> ApprovalItem:
    now = datetime.now(UTC)
    return ApprovalItem(
        approval_id=f"approval-{abs(hash((job_id, question))) % 100000}",
        job_id=job_id,
        family_id="data-engineer",
        question=question,
        category=QuestionCategory.LEGAL_SENSITIVE,
        route=HandlingRoute.HUMAN_REVIEW,
        review_band=ReviewBand.RED,
        reason=ApprovalReason.LEGAL_SENSITIVE,
        status=ApprovalStatus.APPROVED,
        proposed_answer=answer,
        edited_answer=None,
        final_answer=answer,
        evidence_ids=[],
        reviewer="candidate",
        decision_note="Explicitly reviewed for fixture.",
        created_at=now,
        updated_at=now,
        reviewed_at=now,
        approved_for_preparation=True,
        submitted=False,
    )


def test_greenhouse_live_preparation_fills_verified_and_approved_values_without_submit(
    tmp_path,
) -> None:
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF fixture")

    candidate = _candidate(
        _fact("first_name", "Casey"),
        _fact("last_name", "Candidate"),
        _fact("email", "casey@example.com"),
    )
    approvals = [
        _approved(
            "job-1",
            "Will you now or in the future require visa sponsorship?",
            "No",
        )
    ]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(_GREENHOUSE)
            result = LiveApplicationPreparer(page).prepare(
                application_id="application-1",
                job_id="job-1",
                vendor=BrowserAuditVendor.GREENHOUSE,
                candidate=candidate,
                approvals=approvals,
                file_paths={"selected_resume": str(resume)},
            )

            assert result.status is ApplicationPreparationStatus.PREPARED
            assert result.filled_fields == 5
            assert result.blockers == []
            assert result.submit_selector == "#submit-app"
            assert result.submit_control_count == 1
            assert result.prepared_payload_sha256 is not None
            assert result.submission_allowed is False

            assert page.locator("#first").input_value() == "Casey"
            assert page.locator("#last").input_value() == "Candidate"
            assert page.locator("#email").input_value() == "casey@example.com"
            assert page.locator("#sponsor").input_value() == "no"
            assert page.locator("#resume").evaluate("el => el.files[0].name") == "resume.pdf"

            capture = PlaywrightBrowserInspector().capture_live_page(page)
            assert capture.screenshot_png.startswith(b"\\x89PNG")
            assert capture.redacted_dom_values > 0
            assert page.locator("#first").input_value() == "Casey"
            assert page.locator("#last").input_value() == "Candidate"
            assert page.locator("#email").input_value() == "casey@example.com"
            assert page.locator("#sponsor").input_value() == "no"
            assert page.locator("#resume").evaluate("el => el.files[0].name") == "resume.pdf"
            assert page.evaluate("window.__submitted || 0") == 0
        finally:
            browser.close()


def test_lever_live_preparation_uses_approved_narrative_and_never_submits(
    tmp_path,
) -> None:
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF fixture")

    candidate = _candidate(
        _fact("full_name", "Casey Candidate"),
        _fact("email", "casey@example.com"),
    )
    now = datetime.now(UTC)
    narrative = ApprovalItem(
        approval_id="approval-narrative",
        job_id="job-2",
        family_id="data-engineer",
        question="Why are you interested in this role?",
        category=QuestionCategory.NARRATIVE,
        route=HandlingRoute.DRAFT_WITH_REVIEW,
        review_band=ReviewBand.YELLOW,
        reason=ApprovalReason.NARRATIVE_DRAFT,
        status=ApprovalStatus.APPROVED,
        proposed_answer="I build reliable data systems.",
        final_answer="I build reliable data systems.",
        evidence_ids=["project-1"],
        reviewer="candidate",
        decision_note="Reviewed.",
        created_at=now,
        updated_at=now,
        reviewed_at=now,
        approved_for_preparation=True,
        submitted=False,
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(_LEVER)
            result = LiveApplicationPreparer(page).prepare(
                application_id="application-2",
                job_id="job-2",
                vendor=BrowserAuditVendor.LEVER,
                candidate=candidate,
                approvals=[narrative],
                file_paths={"selected_resume": str(resume)},
            )

            assert result.status is ApplicationPreparationStatus.PREPARED
            assert result.filled_fields == 4
            assert page.locator("#name").input_value() == "Casey Candidate"
            assert page.locator("#email").input_value() == "casey@example.com"
            assert page.locator("#why").input_value() == "I build reliable data systems."
            assert page.evaluate("window.__submitted || 0") == 0
        finally:
            browser.close()


def test_missing_required_verified_fact_blocks_final_preparation_but_does_not_submit(
    tmp_path,
) -> None:
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF fixture")

    candidate = _candidate(
        _fact("first_name", "Casey"),
        _fact("last_name", "Candidate"),
    )
    approvals = [
        _approved(
            "job-1",
            "Will you now or in the future require visa sponsorship?",
            "No",
        )
    ]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(_GREENHOUSE)
            result = LiveApplicationPreparer(page).prepare(
                application_id="application-3",
                job_id="job-1",
                vendor=BrowserAuditVendor.GREENHOUSE,
                candidate=candidate,
                approvals=approvals,
                file_paths={"selected_resume": str(resume)},
            )

            assert result.status is ApplicationPreparationStatus.BLOCKED
            assert result.prepared_payload_sha256 is None
            assert any(
                blocker.code is ApplicationPreparationBlocker.MISSING_VERIFIED_FACT
                and blocker.selector == "#email"
                for blocker in result.blockers
            )
            assert page.locator("#email").input_value() == ""
            assert page.evaluate("window.__submitted || 0") == 0
        finally:
            browser.close()


def test_workday_live_execution_is_explicitly_unsupported() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            result = LiveApplicationPreparer(page).prepare(
                application_id="application-4",
                job_id="job-4",
                vendor=BrowserAuditVendor.WORKDAY,
                candidate=_candidate(),
            )
            assert result.status is ApplicationPreparationStatus.UNSUPPORTED
            assert result.blockers[0].code is (
                ApplicationPreparationBlocker.WORKDAY_STATEFUL_PROGRESSION
            )
            assert result.filled_fields == 0
        finally:
            browser.close()
