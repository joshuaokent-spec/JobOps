import pytest

from jobops.browser import BrowserDryRunPlanner, BrowserNavigationBlockedError, BrowserPolicyError
from jobops.browser.base import SubmissionBlockedError
from jobops.browser.playwright_inspector import PlaywrightBrowserInspector
from jobops.models.browser import BrowserFieldKind, BrowserSessionConfig, DryRunOperation

_FIXTURE = """
<!doctype html>
<html>
<head><title>Example Application</title></head>
<body>
  <form id="application" method="post" action="/apply">
    <label for="full_name">Full name</label>
    <input id="full_name" name="full_name" required>

    <label>Email address <input type="email" name="email" aria-required="true"></label>

    <label for="work_mode">Preferred work mode</label>
    <select id="work_mode" name="work_mode">
      <option value="remote">Remote</option>
      <option value="hybrid">Hybrid</option>
    </select>

    <label><input type="checkbox" name="sponsorship"> I require sponsorship</label>

    <label for="resume">Resume</label>
    <input id="resume" type="file" name="resume">

    <textarea name="why_us" aria-label="Why do you want to work here?"></textarea>

    <button type="submit">Submit application</button>
  </form>
  <script>
    fetch('/blocked-write', {method: 'POST', body: 'dry-run-probe'}).catch(() => {});
  </script>
</body>
</html>
"""


def test_inspects_real_form_and_blocks_mutating_fixture_request() -> None:
    inspector = PlaywrightBrowserInspector()
    snapshot = inspector.inspect_html(
        _FIXTURE,
        base_url="https://fixture.invalid/application",
    )

    assert snapshot.url == "https://fixture.invalid/application"
    assert snapshot.title == "Example Application"
    assert snapshot.dry_run is True
    assert snapshot.submit_controls == 1
    assert snapshot.blocked_network_requests >= 1
    assert len(snapshot.forms) == 1

    form = snapshot.forms[0]
    assert form.selector == "#application"
    assert form.method == "post"
    assert form.action == "/apply"

    by_name = {field.name: field for field in form.fields if field.name}
    assert by_name["full_name"].kind is BrowserFieldKind.TEXT
    assert by_name["full_name"].label == "Full name"
    assert by_name["full_name"].required is True
    assert by_name["email"].kind is BrowserFieldKind.EMAIL
    assert by_name["email"].required is True
    assert by_name["work_mode"].kind is BrowserFieldKind.SELECT
    assert [option.value for option in by_name["work_mode"].options] == ["remote", "hybrid"]
    assert by_name["sponsorship"].kind is BrowserFieldKind.CHECKBOX
    assert by_name["resume"].kind is BrowserFieldKind.FILE
    assert by_name["why_us"].kind is BrowserFieldKind.TEXTAREA


def test_planner_inventory_never_turns_submit_control_into_action() -> None:
    snapshot = PlaywrightBrowserInspector().inspect_html(_FIXTURE)
    plan = BrowserDryRunPlanner().plan(snapshot)

    assert plan.submission_allowed is False
    assert plan.submit_controls == 1
    assert plan.fillable_fields == 6
    assert any(action.operation is DryRunOperation.UPLOAD for action in plan.actions)
    submit_actions = [
        action for action in plan.actions if action.operation is DryRunOperation.BLOCKED_SUBMIT
    ]
    assert len(submit_actions) == 1
    assert "unavailable" in submit_actions[0].reason


def test_explicit_submit_attempt_is_blocked_by_default() -> None:
    inspector = PlaywrightBrowserInspector()
    with pytest.raises(SubmissionBlockedError, match="submission is disabled"):
        inspector.submit_form("#application")


def test_m3_1_still_does_not_submit_when_config_gate_is_manually_opened() -> None:
    inspector = PlaywrightBrowserInspector(BrowserSessionConfig(allow_submit=True))
    with pytest.raises(BrowserPolicyError, match="not implemented in M3.1"):
        inspector.submit_form("#application")


def test_linkedin_navigation_is_out_of_scope() -> None:
    inspector = PlaywrightBrowserInspector()
    with pytest.raises(BrowserNavigationBlockedError, match="LinkedIn"):
        inspector.inspect_url("https://www.linkedin.com/jobs/view/123")


def test_non_http_navigation_is_rejected_before_browser_launch() -> None:
    inspector = PlaywrightBrowserInspector()
    with pytest.raises(BrowserNavigationBlockedError, match="HTTP"):
        inspector.inspect_url("data:text/html,unsafe")
