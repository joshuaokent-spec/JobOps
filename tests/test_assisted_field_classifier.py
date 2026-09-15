import json

from jobops.browser.assisted_field_classifier import AssistedSemanticFieldClassifier
from jobops.models.application_question import HandlingRoute, ReviewBand
from jobops.models.browser import BrowserFieldDescriptor, BrowserFieldKind
from jobops.models.form_mapping import ApplicationFieldSemantic, MappingSource
from jobops.models.llm import ChatRequest, ChatResponse, LLMProviderStatus


class FakeProvider:
    provider_name = "fake_local"
    model_name = "fake-npu"

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls = 0
        self.last_request: ChatRequest | None = None

    def complete(self, request: ChatRequest) -> ChatResponse:
        self.calls += 1
        self.last_request = request
        return ChatResponse(
            content=json.dumps(self.payload),
            provider=self.provider_name,
            model=self.model_name,
        )

    def probe(self) -> LLMProviderStatus:
        return LLMProviderStatus(
            provider=self.provider_name,
            model=self.model_name,
            available=True,
        )

    def list_models(self) -> list[str]:
        return [self.model_name]


def _field(label: str) -> BrowserFieldDescriptor:
    return BrowserFieldDescriptor(
        form_index=0,
        field_index=0,
        tag="input",
        kind=BrowserFieldKind.TEXT,
        input_type="text",
        name="custom_field_92",
        label=label,
        selector="#custom-field",
    )


def test_model_assists_only_unresolved_field_and_keeps_review_gate() -> None:
    provider = FakeProvider(
        {
            "semantic": "portfolio_url",
            "confidence": 0.91,
            "reason": "The label asks for a link showing the applicant's work.",
        }
    )
    mapping = AssistedSemanticFieldClassifier(provider).classify_field(
        _field("Link to examples of your work")
    )

    assert provider.calls == 1
    assert mapping.semantic is ApplicationFieldSemantic.PORTFOLIO_URL
    assert mapping.source is MappingSource.MODEL_ASSISTED
    assert mapping.fact_key == "portfolio_url"
    assert mapping.review_band is ReviewBand.YELLOW
    assert mapping.route is HandlingRoute.DRAFT_WITH_REVIEW
    assert mapping.requires_human_review is True


def test_model_is_not_called_when_deterministic_rule_resolves_field() -> None:
    provider = FakeProvider(
        {
            "semantic": "personal_website",
            "confidence": 0.99,
            "reason": "irrelevant",
        }
    )
    mapping = AssistedSemanticFieldClassifier(provider).classify_field(_field("Email address"))

    assert provider.calls == 0
    assert mapping.semantic is ApplicationFieldSemantic.EMAIL
    assert mapping.source is MappingSource.DETERMINISTIC
    assert mapping.review_band is ReviewBand.GREEN


def test_model_identified_sensitive_semantic_remains_red() -> None:
    provider = FakeProvider(
        {
            "semantic": "work_authorization",
            "confidence": 0.94,
            "reason": "The unusual wording appears to ask about permission to work.",
        }
    )
    mapping = AssistedSemanticFieldClassifier(provider).classify_field(
        _field("Do you hold the employment permission needed for this role?")
    )

    assert mapping.semantic is ApplicationFieldSemantic.WORK_AUTHORIZATION
    assert mapping.review_band is ReviewBand.RED
    assert mapping.route is HandlingRoute.HUMAN_REVIEW
    assert mapping.requires_human_review is True


def test_low_confidence_model_answer_does_not_resolve_unknown_field() -> None:
    provider = FakeProvider(
        {
            "semantic": "city",
            "confidence": 0.41,
            "reason": "Weak guess based on little context.",
        }
    )
    mapping = AssistedSemanticFieldClassifier(provider).classify_field(_field("Special response"))

    assert mapping.semantic is ApplicationFieldSemantic.UNKNOWN
    assert mapping.source is MappingSource.UNRESOLVED
    assert mapping.review_band is ReviewBand.RED
    assert mapping.confidence == 0.41


def test_prompt_explicitly_forbids_answering_or_inventing_candidate_facts() -> None:
    provider = FakeProvider(
        {
            "semantic": "city",
            "confidence": 0.90,
            "reason": "Location-oriented field.",
        }
    )
    AssistedSemanticFieldClassifier(provider).classify_field(_field("Primary municipality"))

    assert provider.last_request is not None
    system = provider.last_request.messages[0].content
    assert "Do not answer the field" in system
    assert "do not infer candidate facts" in system
