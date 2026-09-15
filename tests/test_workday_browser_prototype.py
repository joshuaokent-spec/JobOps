import pytest

from jobops.browser import WorkdayBrowserPrototype, WorkdayDetectionError
from jobops.models.application_question import HandlingRoute, ReviewBand
from jobops.models.form_mapping import ApplicationFieldSemantic
from jobops.models.workday_browser import (
    WorkdayBlockedOperation,
    WorkdayStepCategory,
)

_BASE_URL = (
    "https://acme.wd5.myworkdayjobs.com/en-US/External/job/"
    "Data-Engineer_REQ-123?source=Portfolio"
)


def test_prepares_my_information_without_advancing_workday() -> None:
    html = """
    <!doctype html>
    <html>
    <head><title>Apply - Data Engineer</title></head>
    <body>
      <h1>My Information</h1>
      <form id="application-step">
        <label for="first">First Name</label>
        <input id="first" name="firstName" required>
        <label for="last">Last Name</label>
        <input id="last" name="lastName" required>
        <label for="email">Email</label>
        <input id="email" type="email" name="email" required>
        <label for="phone">Phone</label>
        <input id="phone" type="tel" name="phone">
      </form>
      <button id="save" type="button">Save for Later</button>
      <button id="next" type="button">Next</button>
    </body>
    </html>
    """

    result = WorkdayBrowserPrototype().prepare_html(html, base_url=_BASE_URL)

    assert result.detection.detected is True
    assert result.detection.tenant == "acme"
    assert result.detection.site == "External"
    assert result.detection.locale == "en-US"
    assert result.detection.requisition_id == "REQ-123"
    assert result.detection.source == "Portfolio"
    assert result.step.category is WorkdayStepCategory.CONTACT_INFORMATION
    assert result.page.headings == ["My Information"]

    operations = {action.operation for action in result.blocked_actions}
    assert WorkdayBlockedOperation.NEXT in operations
    assert WorkdayBlockedOperation.SAVE_FOR_LATER in operations
    assert result.progression_allowed is False
    assert result.live_writes_allowed is False
    assert result.submission_allowed is False


def test_application_questions_reuse_existing_red_and_yellow_policy() -> None:
    html = """
    <!doctype html>
    <html><body>
      <h2>Application Questions</h2>
      <form id="questions">
        <label for="auth">Are you legally authorized to work in the United States?</label>
        <select id="auth" name="workAuthorization">
          <option>Yes</option><option>No</option>
        </select>
        <label for="why">Why are you interested in this role?</label>
        <textarea id="why" name="whyRole"></textarea>
      </form>
      <button id="next" type="button">Next</button>
    </body></html>
    """

    result = WorkdayBrowserPrototype().prepare_html(html, base_url=_BASE_URL)

    assert result.step.category is WorkdayStepCategory.APPLICATION_QUESTIONS
    by_semantic = {item.semantic: item for item in result.semantic_mapping.mappings}
    authorization = by_semantic[ApplicationFieldSemantic.WORK_AUTHORIZATION]
    assert authorization.route is HandlingRoute.HUMAN_REVIEW
    assert authorization.review_band is ReviewBand.RED
    narrative = by_semantic[ApplicationFieldSemantic.NARRATIVE_QUESTION]
    assert narrative.route is HandlingRoute.DRAFT_WITH_REVIEW
    assert narrative.review_band is ReviewBand.YELLOW


def test_voluntary_disclosures_and_terms_remain_human_review() -> None:
    html = """
    <!doctype html>
    <html><body>
      <h2>Voluntary Disclosures</h2>
      <form id="disclosures">
        <label for="gender">Gender self-identification</label>
        <select id="gender" name="gender">
          <option>Woman</option><option>Man</option><option>Decline</option>
        </select>
        <label for="consent">I consent to the terms and conditions.</label>
        <input id="consent" type="checkbox" name="candidateConsent">
      </form>
      <button id="next" type="button">Next</button>
    </body></html>
    """

    result = WorkdayBrowserPrototype().prepare_html(html, base_url=_BASE_URL)

    assert result.step.category is WorkdayStepCategory.VOLUNTARY_DISCLOSURES
    by_semantic = {item.semantic: item for item in result.semantic_mapping.mappings}
    assert by_semantic[ApplicationFieldSemantic.DEMOGRAPHIC_SELF_ID].review_band is ReviewBand.RED
    assert by_semantic[ApplicationFieldSemantic.CONSENT_ATTESTATION].review_band is ReviewBand.RED


def test_final_review_can_be_classified_without_a_form_and_submit_stays_blocked() -> None:
    html = """
    <!doctype html>
    <html><body>
      <h1>Review Your Application</h1>
      <p>Please review your information before submitting.</p>
      <button id="submit" type="button">Submit Application</button>
    </body></html>
    """

    result = WorkdayBrowserPrototype().prepare_html(html, base_url=_BASE_URL)

    assert result.step.category is WorkdayStepCategory.FINAL_REVIEW
    assert result.semantic_mapping.mappings == []
    assert result.preparation_plan.submission_allowed is False
    assert [action.operation for action in result.blocked_actions] == [
        WorkdayBlockedOperation.SUBMIT
    ]


def test_job_detail_page_is_not_mistaken_for_application_wizard() -> None:
    html = """
    <!doctype html>
    <html><body>
      <a href="/candidate-home">Sign In</a>
      <h1>Data Engineer</h1>
      <p>Build reliable data systems.</p>
      <button id="apply" type="button">Apply</button>
    </body></html>
    """

    with pytest.raises(WorkdayDetectionError, match="could not be identified"):
        WorkdayBrowserPrototype().prepare_html(html, base_url=_BASE_URL)


def test_non_workday_form_is_rejected() -> None:
    html = """
    <!doctype html>
    <html><body>
      <h1>My Information</h1>
      <form><input name="email" type="email"></form>
      <button type="button">Next</button>
    </body></html>
    """

    with pytest.raises(WorkdayDetectionError, match="could not be identified"):
        WorkdayBrowserPrototype().prepare_html(
            html,
            base_url="https://careers.example.com/jobs/123",
        )


def test_invalid_workday_detection_threshold_is_rejected() -> None:
    with pytest.raises(ValueError, match="minimum_confidence"):
        WorkdayBrowserPrototype(minimum_confidence=1.1)
