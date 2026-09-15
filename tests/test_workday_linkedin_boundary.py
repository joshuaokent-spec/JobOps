from jobops.browser import WorkdayBrowserPrototype
from jobops.models.workday_browser import WorkdayBlockedOperation, WorkdayStepCategory

_BASE_URL = (
    "https://acme.wd5.myworkdayjobs.com/en-US/External/job/"
    "Data-Engineer_REQ-123?source=Portfolio"
)


def test_apply_with_linkedin_is_visible_but_never_executed() -> None:
    html = """
    <!doctype html>
    <html><body>
      <h1>Candidate Home - Sign In</h1>
      <button id="linkedin" type="button">Apply with LinkedIn</button>
      <button id="create" type="button">Create Account</button>
    </body></html>
    """

    result = WorkdayBrowserPrototype().prepare_html(html, base_url=_BASE_URL)

    assert result.step.category is WorkdayStepCategory.ACCOUNT_ACCESS
    operations = {action.operation for action in result.blocked_actions}
    assert WorkdayBlockedOperation.APPLY_WITH_LINKEDIN in operations
    assert WorkdayBlockedOperation.CREATE_ACCOUNT in operations
    assert result.progression_allowed is False
    assert result.live_writes_allowed is False
    assert result.submission_allowed is False
