from html import escape

import pytest

from jobops.browser import GreenhouseBrowserAdapter, GreenhouseDetectionError
from jobops.models.application_question import HandlingRoute, ReviewBand
from jobops.models.form_mapping import (
    ApplicationFieldSemantic,
    SemanticPreparationOperation,
)

_HOSTED_FIXTURE = """
<!doctype html>
<html>
<head><title>Acme — Data Engineer</title></head>
<body>
  <form id="job-search" method="get" action="/search">
    <label for="query">Search jobs</label>
    <input id="query" name="query">
    <button type="submit">Search</button>
  </form>

  <form id="application_form" method="post" action="/applications">
    <label for="first_name">First name</label>
    <input id="first_name" name="job_application[first_name]" required>

    <label for="last_name">Last name</label>
    <input id="last_name" name="job_application[last_name]" required>

    <label for="email">Email</label>
    <input id="email" type="email" name="job_application[email]" required>

    <label for="resume">Resume</label>
    <input id="resume" type="file" name="job_application[resume]">

    <label for="sponsorship">Will you now or in the future require visa sponsorship?</label>
    <select id="sponsorship" name="job_application[answers_attributes][0][text_value]">
      <option value="">Choose</option>
      <option value="yes">Yes</option>
      <option value="no">No</option>
    </select>

    <button type="submit">Submit application</button>
  </form>
</body>
</html>
"""

_EMBEDDED_APPLICATION = """
<!doctype html>
<html>
<body>
  <form id="application_form" method="post" action="/applications">
    <label for="first_name">First name</label>
    <input id="first_name" name="job_application[first_name]">

    <label for="email">Email address</label>
    <input id="email" type="email" name="job_application[email]">

    <label for="why_us">Why do you want to work here?</label>
    <textarea id="why_us" name="job_application[answers_attributes][1][text_value]"></textarea>

    <button type="submit">Apply</button>
  </form>
</body>
</html>
"""

_GENERIC_FORM = """
<!doctype html>
<html>
<body>
  <form id="application" method="post" action="/apply">
    <label>First name <input name="first_name"></label>
    <label>Last name <input name="last_name"></label>
    <label>Email <input type="email" name="email"></label>
    <button type="submit">Apply</button>
  </form>
</body>
</html>
"""


def test_prepares_greenhouse_hosted_application_and_preserves_metadata() -> None:
    result = GreenhouseBrowserAdapter().prepare_html(
        _HOSTED_FIXTURE,
        base_url="https://boards.greenhouse.io/acme/jobs/12345?gh_src=campaign123",
    )

    assert result.detection.detected is True
    assert result.detection.embedded is False
    assert result.detection.job_id == "12345"
    assert result.detection.source_token == "campaign123"
    assert result.detection.board_token == "acme"
    assert result.detection.confidence == 1.0

    assert len(result.page.forms) == 1
    assert result.page.forms[0].selector == "#application_form"
    assert result.page.submit_controls == 1

    by_semantic = {
        mapping.semantic: mapping for mapping in result.semantic_mapping.mappings
    }
    assert by_semantic[ApplicationFieldSemantic.FIRST_NAME].fact_key == "first_name"
    assert by_semantic[ApplicationFieldSemantic.RESUME].fact_key == "selected_resume"

    sponsorship = by_semantic[ApplicationFieldSemantic.SPONSORSHIP]
    assert sponsorship.route is HandlingRoute.HUMAN_REVIEW
    assert sponsorship.review_band is ReviewBand.RED
    assert sponsorship.requires_human_review is True

    assert result.preparation_plan.submission_allowed is False
    assert result.submission_allowed is False
    assert any(
        action.operation is SemanticPreparationOperation.BLOCKED_SUBMIT
        for action in result.preparation_plan.actions
    )


def test_prepares_greenhouse_application_inside_iframe() -> None:
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

    result = GreenhouseBrowserAdapter().prepare_html(
        outer,
        base_url="https://careers.example.com/jobs?gh_jid=67890&gh_src=embedded123",
    )

    assert result.detection.detected is True
    assert result.detection.embedded is True
    assert result.detection.document_index == 1
    assert result.detection.job_id == "67890"
    assert result.detection.source_token == "embedded123"
    assert result.detection.board_token is None
    assert len(result.page.forms) == 1
    assert result.page.forms[0].selector == "#application_form"

    semantics = {mapping.semantic for mapping in result.semantic_mapping.mappings}
    assert ApplicationFieldSemantic.FIRST_NAME in semantics
    assert ApplicationFieldSemantic.EMAIL in semantics
    assert ApplicationFieldSemantic.NARRATIVE_QUESTION in semantics
    assert ApplicationFieldSemantic.SUBMIT_CONTROL in semantics
    assert result.preparation_plan.submission_allowed is False


def test_greenhouse_adapter_does_not_claim_generic_application_form() -> None:
    adapter = GreenhouseBrowserAdapter()
    with pytest.raises(GreenhouseDetectionError, match="could not be identified"):
        adapter.prepare_html(
            _GENERIC_FORM,
            base_url="https://careers.example.com/jobs/123",
        )


def test_invalid_detection_threshold_is_rejected() -> None:
    with pytest.raises(ValueError, match="minimum_confidence"):
        GreenhouseBrowserAdapter(minimum_confidence=1.1)
