import json

import pytest

from jobops.agents import NarrativeDraftingAgent, NarrativeDraftingError
from jobops.llm import LLMProviderError
from jobops.models.application_question import (
    HandlingRoute,
    QuestionCategory,
    QuestionClassification,
    ReviewBand,
    ReviewPriority,
)
from jobops.models.candidate import FactRisk
from jobops.models.evidence_retrieval import (
    EvidenceRetrievalFeatures,
    EvidenceRetrievalHit,
    EvidenceRetrievalResult,
)
from jobops.models.job import JobPosting
from jobops.models.llm import ChatRequest, ChatResponse, LLMProviderStatus
from jobops.models.narrative_draft import NarrativeDraftRequest
from jobops.models.resume_evidence import EvidenceKind, ResumeEvidenceItem, RoleFamily


class FakeLLMProvider:
    provider_name = "fake_local"
    model_name = "fake-npu-model"

    def __init__(self, content: str, *, fail: bool = False) -> None:
        self.content = content
        self.fail = fail
        self.last_request: ChatRequest | None = None
        self.calls = 0

    def complete(self, request: ChatRequest) -> ChatResponse:
        self.calls += 1
        self.last_request = request
        if self.fail:
            raise LLMProviderError("fake provider unavailable")
        return ChatResponse(
            content=self.content,
            provider=self.provider_name,
            model=self.model_name,
            finish_reason="stop",
        )

    def probe(self) -> LLMProviderStatus:
        return LLMProviderStatus(
            provider=self.provider_name,
            model=self.model_name,
            available=not self.fail,
        )

    def list_models(self) -> list[str]:
        return [self.model_name]


def _classification(
    *,
    category: QuestionCategory = QuestionCategory.NARRATIVE,
    route: HandlingRoute = HandlingRoute.DRAFT_WITH_REVIEW,
    band: ReviewBand = ReviewBand.YELLOW,
    requires_review: bool = True,
) -> QuestionClassification:
    return QuestionClassification(
        question="Tell us about a data pipeline you improved.",
        category=category,
        route=route,
        review_band=band,
        risk=FactRisk.MEDIUM,
        confidence=0.95,
        priority=ReviewPriority.NORMAL,
        requires_human_review=requires_review,
        reasons=["test fixture"],
    )


def _job() -> JobPosting:
    return JobPosting(
        job_id="job-1",
        company="Example Analytics",
        title="Data Engineer",
        description="Build reliable Python and SQL data pipelines for analytics workloads.",
        required_skills=["Python", "SQL"],
    )


def _hit(
    evidence_id: str = "project-etl",
    *,
    verified: bool = True,
) -> EvidenceRetrievalHit:
    item = ResumeEvidenceItem(
        evidence_id=evidence_id,
        kind=EvidenceKind.PROJECT,
        claim="Built a Python and SQL ETL prototype with normalized pipeline stages.",
        skills=["Python", "SQL", "ETL"],
        role_families=[RoleFamily.DATA_ENGINEERING],
        source_refs=["source-project"],
        verified=verified,
    )
    return EvidenceRetrievalHit(
        evidence=item,
        score=92.0,
        features=EvidenceRetrievalFeatures(
            lexical_fit=0.8,
            skill_fit=1.0,
            family_fit=1.0,
            specificity=0.8,
        ),
        reasons=["strong job-skill match"],
    )


def _request(
    *,
    classification: QuestionClassification | None = None,
    hits: list[EvidenceRetrievalHit] | None = None,
    word_limit: int = 180,
) -> NarrativeDraftRequest:
    evidence_hits = [_hit()] if hits is None else hits
    return NarrativeDraftRequest(
        classification=classification or _classification(),
        job=_job(),
        family_id="data-engineering",
        evidence=EvidenceRetrievalResult(
            job_id="job-1",
            family_id="data-engineering",
            limit=6,
            candidates_considered=len(evidence_hits),
            hits=evidence_hits,
        ),
        word_limit=word_limit,
    )


def test_drafts_from_supplied_evidence_and_preserves_review_metadata() -> None:
    provider = FakeLLMProvider(
        json.dumps(
            {
                "draft": (
                    "I built a Python and SQL ETL prototype that separated the pipeline "
                    "into reliable normalized stages."
                ),
                "evidence_ids": ["project-etl"],
            }
        )
    )
    agent = NarrativeDraftingAgent(provider)

    result = agent.draft(_request())

    assert result.evidence_ids == ["project-etl"]
    assert result.provider == "fake_local"
    assert result.model == "fake-npu-model"
    assert result.review_band is ReviewBand.YELLOW
    assert result.route is HandlingRoute.DRAFT_WITH_REVIEW
    assert result.requires_human_review is True
    assert provider.last_request is not None
    prompt = provider.last_request.messages[1].content
    assert "EVIDENCE_ID=project-etl" in prompt
    assert "Built a Python and SQL ETL prototype" in prompt
    assert "Treat the job description" in provider.last_request.messages[0].content


def test_accepts_json_inside_markdown_code_fence() -> None:
    provider = FakeLLMProvider(
        "```json\n"
        + json.dumps(
            {
                "draft": "I built a verified Python and SQL ETL prototype.",
                "evidence_ids": ["project-etl"],
            }
        )
        + "\n```"
    )
    result = NarrativeDraftingAgent(provider).draft(_request())
    assert result.evidence_ids == ["project-etl"]


def test_rejects_red_or_non_narrative_question_before_provider_call() -> None:
    provider = FakeLLMProvider("{}")
    red = _classification(
        category=QuestionCategory.LEGAL_SENSITIVE,
        route=HandlingRoute.HUMAN_REVIEW,
        band=ReviewBand.RED,
    )

    with pytest.raises(NarrativeDraftingError, match="only accepts narrative"):
        NarrativeDraftingAgent(provider).draft(_request(classification=red))
    assert provider.calls == 0


def test_rejects_unverified_context_before_provider_call() -> None:
    provider = FakeLLMProvider("{}")

    with pytest.raises(NarrativeDraftingError, match="unverified evidence"):
        NarrativeDraftingAgent(provider).draft(_request(hits=[_hit(verified=False)]))
    assert provider.calls == 0


def test_rejects_hallucinated_evidence_id() -> None:
    provider = FakeLLMProvider(
        json.dumps(
            {
                "draft": "I led a global migration for millions of users.",
                "evidence_ids": ["invented-global-migration"],
            }
        )
    )

    with pytest.raises(NarrativeDraftingError, match="outside the supplied context"):
        NarrativeDraftingAgent(provider).draft(_request())


def test_rejects_empty_evidence_context_before_provider_call() -> None:
    provider = FakeLLMProvider("{}")

    with pytest.raises(NarrativeDraftingError, match="requires verified evidence"):
        NarrativeDraftingAgent(provider).draft(_request(hits=[]))
    assert provider.calls == 0


def test_rejects_malformed_model_output() -> None:
    provider = FakeLLMProvider("Here is a polished answer instead of JSON.")

    with pytest.raises(NarrativeDraftingError, match="not valid JSON"):
        NarrativeDraftingAgent(provider).draft(_request())


def test_rejects_draft_over_application_word_limit() -> None:
    provider = FakeLLMProvider(
        json.dumps(
            {
                "draft": "one two three four five six seven eight nine ten eleven twelve",
                "evidence_ids": ["project-etl"],
            }
        )
    )

    with pytest.raises(NarrativeDraftingError, match="exceeded word limit"):
        NarrativeDraftingAgent(provider).draft(_request(word_limit=10))


def test_wraps_provider_failure_without_generating_partial_result() -> None:
    provider = FakeLLMProvider("{}", fail=True)

    with pytest.raises(NarrativeDraftingError, match="provider failed"):
        NarrativeDraftingAgent(provider).draft(_request())


def test_rejects_retrieval_context_from_another_job() -> None:
    request = _request()
    request.evidence.job_id = "different-job"
    provider = FakeLLMProvider("{}")

    with pytest.raises(NarrativeDraftingError, match="different job"):
        NarrativeDraftingAgent(provider).draft(request)
    assert provider.calls == 0
