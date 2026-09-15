from jobops.browser import SemanticFieldClassifier, SemanticPreparationPlanner
from jobops.browser.playwright_inspector import PlaywrightBrowserInspector
from jobops.models.form_mapping import (
    ApplicationFieldSemantic,
    SemanticPreparationOperation,
)

_FIXTURE = """
<!doctype html>
<html>
<head><title>Semantic Application</title></head>
<body>
  <form id="application" method="post" action="/apply">
    <label for="first_name">First Name</label>
    <input id="first_name" name="first_name" required>

    <label for="email">Email</label>
    <input id="email" type="email" name="email" required>

    <label for="authorization">Are you legally authorized to work in the United States?</label>
    <select id="authorization" name="authorization">
      <option value="yes">Yes</option>
      <option value="no">No</option>
    </select>

    <label for="story">Tell us about a data pipeline you improved.</label>
    <textarea id="story" name="question_1"></textarea>

    <button type="submit">Submit application</button>
  </form>
</body>
</html>
"""


def test_real_browser_snapshot_maps_into_semantic_preparation_routes() -> None:
    snapshot = PlaywrightBrowserInspector().inspect_html(
        _FIXTURE,
        base_url="https://fixture.invalid/apply",
    )
    mapping = SemanticFieldClassifier().classify_page(snapshot)
    plan = SemanticPreparationPlanner().plan(mapping)

    semantics = [item.semantic for item in mapping.mappings]
    assert semantics == [
        ApplicationFieldSemantic.FIRST_NAME,
        ApplicationFieldSemantic.EMAIL,
        ApplicationFieldSemantic.WORK_AUTHORIZATION,
        ApplicationFieldSemantic.NARRATIVE_QUESTION,
        ApplicationFieldSemantic.SUBMIT_CONTROL,
    ]

    operations = [action.operation for action in plan.actions]
    assert operations == [
        SemanticPreparationOperation.RESOLVE_FACT,
        SemanticPreparationOperation.RESOLVE_FACT,
        SemanticPreparationOperation.HUMAN_REVIEW,
        SemanticPreparationOperation.DRAFT_WITH_REVIEW,
        SemanticPreparationOperation.BLOCKED_SUBMIT,
    ]
    assert plan.submission_allowed is False
