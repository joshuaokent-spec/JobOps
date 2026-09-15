from jobops.browser import SemanticFieldClassifier
from jobops.browser.semantic_planner import SemanticPreparationPlanner
from jobops.models.browser import (
    BrowserFieldDescriptor,
    BrowserFieldKind,
    BrowserFormSnapshot,
    BrowserPageSnapshot,
)
from jobops.models.form_mapping import SemanticPreparationOperation


def _field(
    index: int,
    label: str,
    *,
    kind: BrowserFieldKind = BrowserFieldKind.TEXT,
    submit: bool = False,
) -> BrowserFieldDescriptor:
    return BrowserFieldDescriptor(
        form_index=0,
        field_index=index,
        tag="input",
        kind=kind,
        input_type="submit" if submit else "text",
        label=label,
        selector=f"#field-{index}",
        is_submit_control=submit,
    )


def test_semantic_plan_routes_each_field_back_into_existing_m2_policy_paths() -> None:
    fields = [
        _field(0, "Email address", kind=BrowserFieldKind.EMAIL),
        _field(1, "Desired salary"),
        _field(2, "Are you legally authorized to work in the United States?"),
        _field(3, "Special response"),
        _field(4, "Submit application", kind=BrowserFieldKind.SUBMIT, submit=True),
    ]
    page = BrowserPageSnapshot(
        url="https://boards.example.test/apply",
        title="Apply",
        forms=[
            BrowserFormSnapshot(
                form_index=0,
                selector="#application",
                fields=fields,
            )
        ],
        submit_controls=1,
    )

    semantic_mapping = SemanticFieldClassifier().classify_page(page)
    plan = SemanticPreparationPlanner().plan(semantic_mapping)
    operations = [action.operation for action in plan.actions]

    assert operations == [
        SemanticPreparationOperation.RESOLVE_FACT,
        SemanticPreparationOperation.DRAFT_WITH_REVIEW,
        SemanticPreparationOperation.HUMAN_REVIEW,
        SemanticPreparationOperation.ESCALATE,
        SemanticPreparationOperation.BLOCKED_SUBMIT,
    ]
    assert plan.fact_resolution_fields == 1
    assert plan.review_fields == 2
    assert plan.unresolved_fields == 1
    assert plan.submit_controls == 1
    assert plan.submission_allowed is False
