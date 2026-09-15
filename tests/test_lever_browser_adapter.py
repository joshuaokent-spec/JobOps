from html import escape

import pytest

from jobops.browser import LeverBrowserAdapter, LeverDetectionError
from jobops.models.application_question import HandlingRoute, ReviewBand
from jobops.models.form_mapping import (
    ApplicationFieldSemantic,
    SemanticPreparationOperation,
)

_POSTING_ID = "5c8c534e-fa04-45a8-b1b4-99d28f34de0d"

_HOSTED_FIXTURE = f"""
<!doctype html>
<html>
<head><title>Acme — Data Engineer</title></head>
<body>
  <form id="job-search" action="/search">
    <label for="query">Search jobs</label>
    <input id="query" name="query">
    <button type="submit">Search</button>
  </form>

  <form id="application-form" method="post"
        action="https://jobs.lever.co/acme/{_POSTING_ID}/apply">
    <label for="resume">Resume/CV</label>
    <input id="resume" type="file" name="resume">

    <label for="name">Full name</label>
    <input id="name" name="name" required>

    <label for="email">Email</label>
    <input id="email" type="email" name="email" required>

    <label for="phone">Phone</label>
    <input id="phone" type="tel" name="phone">

    <label for="linkedin">LinkedIn URL</label>
    <input id="linkedin" type="url" name="urls[LinkedIn]">

    <label for="motivation">Why do you want to work here?</label>
    <textarea id="motivation" name="customQuestions[motivation]"></textarea>

    <label for="authorization">Do you have the right to work in the US?</label>
    <select id="authorization" name="customQuestions[authorization]">
      <option value="">Choose</option>
      <option value="yes">Yes</option>
      <option value="no">No</option>
    </select>

    <label for="salary">What are your salary expectations?</label>
    <input id="salary" name="customQuestions[salary]">

    <label for="gender">What gender do you identify as?</label>
    <select id="gender" name="eeo[gender]">
      <option value="">Choose</option>
      <option value="female">Female</option>
      <option value="male">Male</option>
      <option value="decline">Prefer not to answer</option>
    </select>

    <label for="retention">
      I consent to retain my data for the purpose of considering me for employment.
    </label>
    <input id="retention" type="checkbox" name="data-retention-consent">

    <button type="submit">Submit application</button>
  </form>
</body>
</html>
"""

_EMBEDDED_APPLICATION = f"""
<!doctype html>
<html>
<body>
  <form class="application-form" method="post"
        action="https://jobs.lever.co/acme/{_POSTING_ID}/apply">
    <label for="resume">Resume/CV</label>
    <input id="resume" type="file" name="resume">

    <label for="name">Full name</label>
    <input id="name" name="name">

    <label for="email">Email</label>
    <input id="email" type="email" name="email">

    <label for="why">Why are you interested in this role?</label>
    <textarea id="why" name="customQuestions[why]"></textarea>

    <button type="submit">Submit application</button>
  </form>
</body>
</html>
"""

_GENERIC_FORM = """
<!doctype html>
<html>
<body>
  <form id="application-form" method="post" action="/apply">
    <label for="name">Full name</label>
    <input id="name" name="name">
    <label for="email">Email</label>
    <input id="email" type="email" name="email">
    <label for="phone">Phone</label>
    <input id="phone" type="tel" name="phone">
    <button type="submit">Apply</button>
  </form>
</body>
</html>
"""


def test_prepares_lever_hosted_application_and_preserves_metadata() -> None:
    result = LeverBrowserAdapter().prepare_html(
        _HOSTED_FIXTURE,
        base_url=(
            f"https://jobs.lever.co/acme/{_POSTING_ID}/apply"
            "?lever-origin=applied&lever-source%5B%5D=Portfolio"
        ),
    )

    assert result.detection.detected is True
    assert result.detection.embedded is False
    assert result.detection.site == "acme"
    assert result.detection.posting_id == _POSTING_ID
    assert result.detection.source_tokens == ["Portfolio"]
    assert result.detection.origin == "applied"
    assert result.detection.apply_page is True
    assert result.detection.confidence == 1.0

    assert len(result.page.forms) == 1
    assert result.page.forms[0].selector == "#application-form"
    assert result.page.submit_controls == 1

    by_semantic = {
        mapping.semantic: mapping for mapping in result.semantic_mapping.mappings
    }
    assert by_semantic[ApplicationFieldSemantic.RESUME].fact_key == "selected_resume"
    assert by_semantic[ApplicationFieldSemantic.FULL_NAME].fact_key == "full_name"
    assert by_semantic[ApplicationFieldSemantic.LINKEDIN_URL].fact_key == "linkedin_url"

    authorization = by_semantic[ApplicationFieldSemantic.WORK_AUTHORIZATION]
    assert authorization.route is HandlingRoute.HUMAN_REVIEW
    assert authorization.review_band is ReviewBand.RED

    salary = by_semantic[ApplicationFieldSemantic.SALARY_EXPECTATION]
    assert salary.route is HandlingRoute.DRAFT_WITH_REVIEW
    assert salary.review_band is ReviewBand.YELLOW

    consent = by_semantic[ApplicationFieldSemantic.CONSENT_ATTESTATION]
    assert consent.route is HandlingRoute.HUMAN_REVIEW
    assert consent.review_band is ReviewBand.RED

    demographic = by_semantic[ApplicationFieldSemantic.DEMOGRAPHIC_SELF_ID]
    assert demographic.route is HandlingRoute.HUMAN_REVIEW
    assert demographic.review_band is ReviewBand.RED

    assert result.preparation_plan.submission_allowed is False
    assert result.submission_allowed is False
    assert any(
        action.operation is SemanticPreparationOperation.BLOCKED_SUBMIT
        for action in result.preparation_plan.actions
    )


def test_prepares_lever_application_inside_iframe() -> None:
    iframe = escape(_EMBEDDED_APPLICATION, quote=True)
    outer = f"""
    <!doctype html>
    <html>
    <head><title>Acme Careers</title></head>
    <body>
      <form id="job-search" action="/jobs">
        <input name="query" aria-label="Search jobs">
      </form>
      <iframe title="Application" srcdoc="{iframe}"></iframe>
    </body>
    </html>
    """

    result = LeverBrowserAdapter().prepare_html(
        outer,
        base_url=(
            "https://careers.example.com/jobs"
            "?lever-source=Referral&lever-origin=applied"
        ),
    )

    assert result.detection.detected is True
    assert result.detection.embedded is True
    assert result.detection.document_index == 1
    assert result.detection.site == "acme"
    assert result.detection.posting_id == _POSTING_ID
    assert result.detection.source_tokens == ["Referral"]
    assert result.detection.origin == "applied"
    assert result.detection.apply_page is True

    semantics = {mapping.semantic for mapping in result.semantic_mapping.mappings}
    assert ApplicationFieldSemantic.RESUME in semantics
    assert ApplicationFieldSemantic.FULL_NAME in semantics
    assert ApplicationFieldSemantic.EMAIL in semantics
    assert ApplicationFieldSemantic.NARRATIVE_QUESTION in semantics
    assert ApplicationFieldSemantic.SUBMIT_CONTROL in semantics
    assert result.preparation_plan.submission_allowed is False


def test_lever_adapter_does_not_claim_generic_application_form() -> None:
    with pytest.raises(LeverDetectionError, match="could not be identified"):
        LeverBrowserAdapter().prepare_html(
            _GENERIC_FORM,
            base_url="https://careers.example.com/jobs/123",
        )


def test_lever_posting_page_without_application_form_is_rejected() -> None:
    posting_only = """
    <!doctype html>
    <html><body><main><h1>Data Engineer</h1><p>Job description</p></main></body></html>
    """
    with pytest.raises(LeverDetectionError, match="could not be identified"):
        LeverBrowserAdapter().prepare_html(
            posting_only,
            base_url=f"https://jobs.lever.co/acme/{_POSTING_ID}",
        )


def test_invalid_detection_threshold_is_rejected() -> None:
    with pytest.raises(ValueError, match="minimum_confidence"):
        LeverBrowserAdapter(minimum_confidence=-0.1)
