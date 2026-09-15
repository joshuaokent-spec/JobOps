from jobops.browser.field_classifier import SemanticFieldClassifier
from jobops.models.application_question import HandlingRoute, QuestionCategory, ReviewBand
from jobops.models.browser import (
    BrowserFieldDescriptor,
    BrowserFieldKind,
    BrowserFormSnapshot,
    BrowserPageSnapshot,
)
from jobops.models.form_mapping import ApplicationFieldSemantic, MappingSource


def _field(
    index: int,
    *,
    name: str | None = None,
    label: str | None = None,
    accessible_name: str | None = None,
    placeholder: str | None = None,
    kind: BrowserFieldKind = BrowserFieldKind.TEXT,
    input_type: str | None = "text",
    submit: bool = False,
) -> BrowserFieldDescriptor:
    return BrowserFieldDescriptor(
        form_index=0,
        field_index=index,
        tag="input" if kind is not BrowserFieldKind.TEXTAREA else "textarea",
        kind=kind,
        input_type=input_type,
        name=name,
        label=label,
        accessible_name=accessible_name,
        placeholder=placeholder,
        selector=f"#field-{index}",
        is_submit_control=submit,
    )


def _page(fields: list[BrowserFieldDescriptor]) -> BrowserPageSnapshot:
    return BrowserPageSnapshot(
        url="https://boards.example.test/apply",
        title="Apply",
        forms=[
            BrowserFormSnapshot(
                form_index=0,
                selector="#application",
                method="post",
                fields=fields,
            )
        ],
        submit_controls=sum(field.is_submit_control for field in fields),
    )


def test_greenhouse_style_contact_and_resume_fields_map_to_factual_semantics() -> None:
    page = _page(
        [
            _field(0, name="first_name", label="First Name"),
            _field(1, name="last_name", label="Last Name"),
            _field(
                2,
                name="email",
                label="Email",
                kind=BrowserFieldKind.EMAIL,
                input_type="email",
            ),
            _field(
                3,
                name="resume",
                label="Resume/CV",
                kind=BrowserFieldKind.FILE,
                input_type="file",
            ),
        ]
    )

    result = SemanticFieldClassifier().classify_page(page)
    by_name = {mapping.field.name: mapping for mapping in result.mappings}

    assert by_name["first_name"].semantic is ApplicationFieldSemantic.FIRST_NAME
    assert by_name["first_name"].fact_key == "first_name"
    assert by_name["last_name"].semantic is ApplicationFieldSemantic.LAST_NAME
    assert by_name["email"].semantic is ApplicationFieldSemantic.EMAIL
    assert by_name["resume"].semantic is ApplicationFieldSemantic.RESUME
    assert all(mapping.review_band is ReviewBand.GREEN for mapping in result.mappings)
    assert all(mapping.route is HandlingRoute.AUTO_FILL for mapping in result.mappings)
    assert result.mapped_fields == 4
    assert result.unresolved_fields == 0


def test_lever_style_links_and_portfolio_are_recognized_without_browser_navigation() -> None:
    page = _page(
        [
            _field(0, name="urls[LinkedIn]", label="LinkedIn Profile", kind=BrowserFieldKind.URL),
            _field(1, name="urls[GitHub]", label="GitHub", kind=BrowserFieldKind.URL),
            _field(2, name="urls[Portfolio]", label="Portfolio URL", kind=BrowserFieldKind.URL),
        ]
    )

    mappings = SemanticFieldClassifier().classify_page(page).mappings
    assert [mapping.semantic for mapping in mappings] == [
        ApplicationFieldSemantic.LINKEDIN_URL,
        ApplicationFieldSemantic.GITHUB_URL,
        ApplicationFieldSemantic.PORTFOLIO_URL,
    ]
    assert mappings[0].fact_key == "linkedin_url"
    assert mappings[0].route is HandlingRoute.AUTO_FILL


def test_work_authorization_sponsorship_and_clearance_are_always_red() -> None:
    page = _page(
        [
            _field(0, label="Are you legally authorized to work in the United States?"),
            _field(1, label="Will you now or in the future require visa sponsorship?"),
            _field(2, label="What is your active security clearance level?"),
        ]
    )

    mappings = SemanticFieldClassifier().classify_page(page).mappings
    assert [mapping.semantic for mapping in mappings] == [
        ApplicationFieldSemantic.WORK_AUTHORIZATION,
        ApplicationFieldSemantic.SPONSORSHIP,
        ApplicationFieldSemantic.SECURITY_CLEARANCE,
    ]
    for mapping in mappings:
        assert mapping.question_category is QuestionCategory.LEGAL_SENSITIVE
        assert mapping.route is HandlingRoute.HUMAN_REVIEW
        assert mapping.review_band is ReviewBand.RED
        assert mapping.requires_human_review is True


def test_demographic_self_identification_is_separated_from_candidate_facts() -> None:
    mapping = SemanticFieldClassifier().classify_field(
        _field(0, name="race", label="Race / Ethnicity")
    )
    assert mapping.semantic is ApplicationFieldSemantic.DEMOGRAPHIC_SELF_ID
    assert mapping.fact_key is None
    assert mapping.review_band is ReviewBand.RED
    assert mapping.requires_human_review is True


def test_preferences_remain_yellow_and_do_not_become_autofill_policy() -> None:
    page = _page(
        [
            _field(0, label="Desired salary or compensation"),
            _field(1, label="Are you willing to relocate?"),
            _field(2, label="Preferred remote or hybrid work arrangement"),
            _field(3, label="Earliest available start date", kind=BrowserFieldKind.DATE),
        ]
    )

    mappings = SemanticFieldClassifier().classify_page(page).mappings
    assert [mapping.semantic for mapping in mappings] == [
        ApplicationFieldSemantic.SALARY_EXPECTATION,
        ApplicationFieldSemantic.RELOCATION,
        ApplicationFieldSemantic.WORK_MODE,
        ApplicationFieldSemantic.START_DATE,
    ]
    for mapping in mappings:
        assert mapping.question_category is QuestionCategory.PREFERENCE
        assert mapping.review_band is ReviewBand.YELLOW
        assert mapping.requires_human_review is True


def test_open_ended_textarea_preserves_prompt_and_routes_to_narrative_review() -> None:
    prompt = "Tell us about a data pipeline you improved and how you measured success."
    mapping = SemanticFieldClassifier().classify_field(
        _field(
            0,
            name="question_123",
            label=prompt,
            kind=BrowserFieldKind.TEXTAREA,
            input_type=None,
        )
    )

    assert mapping.semantic is ApplicationFieldSemantic.NARRATIVE_QUESTION
    assert mapping.question_text == prompt
    assert mapping.question_category is QuestionCategory.NARRATIVE
    assert mapping.route is HandlingRoute.DRAFT_WITH_REVIEW
    assert mapping.review_band is ReviewBand.YELLOW


def test_unknown_field_is_escalated_instead_of_guessed() -> None:
    mapping = SemanticFieldClassifier().classify_field(
        _field(0, name="custom_thing", label="Special response")
    )
    assert mapping.semantic is ApplicationFieldSemantic.UNKNOWN
    assert mapping.source is MappingSource.UNRESOLVED
    assert mapping.confidence == 0.0
    assert mapping.route is HandlingRoute.ESCALATE
    assert mapping.review_band is ReviewBand.RED


def test_ambiguous_high_confidence_field_is_unresolved() -> None:
    mapping = SemanticFieldClassifier().classify_field(
        _field(0, label="First Name / Last Name")
    )
    assert mapping.semantic is ApplicationFieldSemantic.UNKNOWN
    assert mapping.source is MappingSource.UNRESOLVED
    assert mapping.ambiguous is True
    assert "ambiguous candidates" in mapping.matched_signals[-1]


def test_submit_control_stays_red_and_is_not_counted_as_mapped_candidate_data() -> None:
    submit = _field(
        0,
        name="submit",
        label="Submit application",
        kind=BrowserFieldKind.SUBMIT,
        input_type="submit",
        submit=True,
    )
    result = SemanticFieldClassifier().classify_page(_page([submit]))
    mapping = result.mappings[0]

    assert mapping.semantic is ApplicationFieldSemantic.SUBMIT_CONTROL
    assert mapping.review_band is ReviewBand.RED
    assert result.mapped_fields == 0
    assert result.submission_allowed is False
