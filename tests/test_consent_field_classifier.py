from jobops.browser import SemanticFieldClassifier
from jobops.models.application_question import HandlingRoute, ReviewBand
from jobops.models.browser import BrowserFieldDescriptor, BrowserFieldKind
from jobops.models.form_mapping import ApplicationFieldSemantic


def test_consent_attestation_is_red_human_review() -> None:
    field = BrowserFieldDescriptor(
        form_index=0,
        field_index=0,
        tag="input",
        kind=BrowserFieldKind.CHECKBOX,
        input_type="checkbox",
        name="data-retention-consent",
        element_id="retention",
        label="I consent to retain my data for employment consideration.",
        accessible_name="I consent to retain my data for employment consideration.",
        selector="#retention",
    )

    mapping = SemanticFieldClassifier().classify_field(field)

    assert mapping.semantic is ApplicationFieldSemantic.CONSENT_ATTESTATION
    assert mapping.route is HandlingRoute.HUMAN_REVIEW
    assert mapping.review_band is ReviewBand.RED
    assert mapping.requires_human_review is True
    assert mapping.question_text == field.label
