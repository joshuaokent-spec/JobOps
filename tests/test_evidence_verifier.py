import json

from jobops.agents import EvidenceVerifier
from jobops.llm import LLMProviderError
from jobops.models.application_question import HandlingRoute, ReviewBand
from jobops.models.draft_verification import (
    DraftVerificationRequest,
    VerificationStatus,
)
from jobops.models.evidence_retrieval import (
    EvidenceRetrievalFeatures,
    EvidenceRetrievalHit,
    EvidenceRetrievalResult,
)
from jobops.models.llm import ChatRequest, ChatResponse, LLMProviderStatus
from jobops.models.narrative_draft import NarrativeDraftResult
from jobops.models.resume_evidence import (
    EvidenceKind,
    EvidenceMetric,
    ResumeEvidenceItem,
    RoleFamily,
)


class FakeVerifierProvider:
    provider_name = "fake_verifier"
    model_name = "fake-local-verifier"

    def __init__(self, payload: dict[str, object] | None = None, *, fail: bool = False) -> None:
        self.payload = payload or {"needs_review": False, "unsupported_claims": []}
        self.fail = fail
        self.calls = 0
        self.last_request: ChatRequest | None = None

    def complete(self, request: ChatRequest) -> ChatResponse:
        self.calls += 1
        self.last_request = request
        if self.fail:
            raise LLMProviderError("fake verifier failure")
        return ChatResponse(
            content=json.dumps(self.payload),
            provider=self.provider_name,
            model=self.model_name,
        )

    def probe(self) -> LLMProviderStatus:
        return LLMProviderStatus(
            provider=self.provider_name,
            model=self.model_name,
            available=not self.fail,
        )

    def list_models(self) -> list[str]:
        return [self.model_name]


def _evidence(*, verified: bool = True) -> ResumeEvidenceItem:
    return ResumeEvidenceItem(
        evidence_id="project-etl",
        kind=EvidenceKind.PROJECT,
        claim="Built a Python and SQL ETL pipeline processing 500 records daily.",
        skills=["Python", "SQL", "ETL"],
        role_families=[RoleFamily.DATA_ENGINEERING],
        metrics=[EvidenceMetric(name="records", value=500, unit=" daily")],
        source_refs=["source-project"],
        verified=verified,
    )


def _context(*, verified: bool = True) -> EvidenceRetrievalResult:
    return EvidenceRetrievalResult(
        job_id="job-1",
        family_id="data-engineering",
        limit=6,
        candidates_considered=1,
        hits=[
            EvidenceRetrievalHit(
                evidence=_evidence(verified=verified),
                score=95.0,
                features=EvidenceRetrievalFeatures(
                    lexical_fit=0.9,
                    skill_fit=1.0,
                    family_fit=1.0,
                    specificity=1.0,
                ),
            )
        ],
    )


def _draft(
    text: str = "I built a Python and SQL ETL pipeline processing 500 records daily.",
    *,
    evidence_ids: list[str] | None = None,
) -> NarrativeDraftResult:
    return NarrativeDraftResult(
        question="Tell us about a data pipeline you improved.",
        job_id="job-1",
        family_id="data-engineering",
        draft=text,
        evidence_ids=evidence_ids or ["project-etl"],
        provider="foundry_local",
        model="local-model",
        word_count=len(text.split()),
        review_band=ReviewBand.YELLOW,
        route=HandlingRoute.DRAFT_WITH_REVIEW,
        requires_human_review=True,
    )


def _request(
    text: str = "I built a Python and SQL ETL pipeline processing 500 records daily.",
    *,
    evidence_ids: list[str] | None = None,
    verified: bool = True,
) -> DraftVerificationRequest:
    return DraftVerificationRequest(
        draft=_draft(text, evidence_ids=evidence_ids),
        evidence=_context(verified=verified),
    )


def test_grounded_draft_passes_deterministic_verification() -> None:
    result = EvidenceVerifier().verify(_request())
    assert result.status is VerificationStatus.PASS
    assert result.findings == []
    assert result.semantic_checked is False
    assert result.requires_human_review is True


def test_blocks_inflated_numeric_claim() -> None:
    result = EvidenceVerifier().verify(
        _request("I built a Python and SQL ETL pipeline processing 900 records daily.")
    )
    assert result.status is VerificationStatus.BLOCK
    assert "unsupported_numeric_claim" in {finding.code for finding in result.findings}


def test_blocks_numeric_claim_before_sentence_punctuation() -> None:
    result = EvidenceVerifier().verify(
        _request("I built the Python and SQL ETL pipeline and improved throughput by 900.")
    )
    assert result.status is VerificationStatus.BLOCK
    assert "unsupported_numeric_claim" in {finding.code for finding in result.findings}


def test_blocks_unsupported_technology_claim() -> None:
    result = EvidenceVerifier().verify(
        _request("I used Python, SQL, and Kubernetes to build the ETL pipeline.")
    )
    assert result.status is VerificationStatus.BLOCK
    assert "unsupported_skill_or_tool" in {finding.code for finding in result.findings}


def test_blocks_unsupported_credential_claim() -> None:
    result = EvidenceVerifier().verify(
        _request("As a certified data engineer, I built the Python and SQL ETL pipeline.")
    )
    assert result.status is VerificationStatus.BLOCK
    assert "unsupported_credential_claim" in {finding.code for finding in result.findings}


def test_blocks_unknown_evidence_id() -> None:
    result = EvidenceVerifier().verify(
        _request(evidence_ids=["invented-evidence"])
    )
    assert result.status is VerificationStatus.BLOCK
    assert "unknown_evidence" in {finding.code for finding in result.findings}


def test_blocks_unverified_cited_evidence() -> None:
    result = EvidenceVerifier().verify(_request(verified=False))
    assert result.status is VerificationStatus.BLOCK
    assert "unverified_evidence" in {finding.code for finding in result.findings}


def test_semantic_verifier_can_escalate_pass_to_review_but_not_block() -> None:
    provider = FakeVerifierProvider(
        {
            "needs_review": True,
            "unsupported_claims": ["The wording may imply ownership beyond the evidence."],
        }
    )
    result = EvidenceVerifier(provider).verify(_request())

    assert result.status is VerificationStatus.REVIEW
    assert result.semantic_checked is True
    assert "semantic_entailment_review" in {finding.code for finding in result.findings}
    assert provider.calls == 1


def test_semantic_pass_keeps_deterministic_pass() -> None:
    provider = FakeVerifierProvider()
    result = EvidenceVerifier(provider).verify(_request())

    assert result.status is VerificationStatus.PASS
    assert result.semantic_checked is True
    assert provider.calls == 1


def test_semantic_provider_failure_escalates_to_review() -> None:
    provider = FakeVerifierProvider(fail=True)
    result = EvidenceVerifier(provider).verify(_request())

    assert result.status is VerificationStatus.REVIEW
    assert "semantic_verifier_unavailable" in {finding.code for finding in result.findings}


def test_deterministic_block_skips_semantic_provider() -> None:
    provider = FakeVerifierProvider()
    result = EvidenceVerifier(provider).verify(
        _request("I used Kubernetes to process 900 records daily.")
    )

    assert result.status is VerificationStatus.BLOCK
    assert provider.calls == 0
    assert result.semantic_checked is False


def test_context_mismatch_blocks_verification() -> None:
    request = _request()
    request.evidence.job_id = "different-job"
    result = EvidenceVerifier().verify(request)

    assert result.status is VerificationStatus.BLOCK
    assert "job_context_mismatch" in {finding.code for finding in result.findings}
