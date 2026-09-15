import json
from pathlib import Path

import pytest

from jobops.knowledge import RuleBasedQuestionClassifier, TruthStore
from jobops.models.application_question import (
    HandlingRoute,
    QuestionCategory,
    ReviewBand,
)
from jobops.models.candidate import CandidateFact, CandidateProfile, FactRisk


def _truth_store() -> TruthStore:
    return TruthStore(
        CandidateProfile(
            facts=[
                CandidateFact(
                    key="certifications",
                    value=["Example Certification"],
                    evidence=["credential-record"],
                    verified=True,
                    risk=FactRisk.LOW,
                ),
                CandidateFact(
                    key="highest_education",
                    value="Bachelor of Science",
                    evidence=["degree-record"],
                    verified=False,
                    risk=FactRisk.MEDIUM,
                ),
                CandidateFact(
                    key="work_authorization",
                    value=True,
                    evidence=["candidate-confirmation"],
                    verified=True,
                    risk=FactRisk.HIGH,
                ),
                CandidateFact(
                    key="salary_expectation",
                    value=90000,
                    evidence=["candidate-preference"],
                    verified=True,
                    risk=FactRisk.MEDIUM,
                ),
            ]
        )
    )


def test_fixture_classifications_match_policy_baseline() -> None:
    classifier = RuleBasedQuestionClassifier(_truth_store())
    cases = json.loads(Path("tests/fixtures/application_questions.json").read_text())
    for case in cases:
        result = classifier.classify(case["question"])
        assert result.category.value == case["category"]
        assert result.route.value == case["route"]


def test_legal_question_never_auto_fills_even_when_truth_is_verified() -> None:
    result = RuleBasedQuestionClassifier(_truth_store()).classify(
        "Are you legally authorized to work in the United States?"
    )
    assert result.category is QuestionCategory.LEGAL_SENSITIVE
    assert result.route is HandlingRoute.HUMAN_REVIEW
    assert result.review_band is ReviewBand.RED
    assert result.fact_found is True
    assert result.fact_verified is True
    assert result.requires_human_review is True


def test_verified_low_risk_factual_question_can_auto_fill() -> None:
    result = RuleBasedQuestionClassifier(_truth_store()).classify(
        "What certifications do you currently hold?"
    )
    assert result.route is HandlingRoute.AUTO_FILL
    assert result.review_band is ReviewBand.GREEN
    assert result.matched_fact_key == "certifications"
    assert result.requires_human_review is False


def test_unverified_factual_fact_routes_to_human_review() -> None:
    result = RuleBasedQuestionClassifier(_truth_store()).classify(
        "What is your highest education level?"
    )
    assert result.category is QuestionCategory.FACTUAL
    assert result.route is HandlingRoute.HUMAN_REVIEW
    assert result.review_band is ReviewBand.YELLOW
    assert result.fact_found is True
    assert result.fact_verified is False


def test_missing_factual_fact_escalates_instead_of_guessing() -> None:
    result = RuleBasedQuestionClassifier(_truth_store()).classify(
        "Please provide your portfolio URL."
    )
    assert result.category is QuestionCategory.FACTUAL
    assert result.route is HandlingRoute.ESCALATE
    assert result.review_band is ReviewBand.RED
    assert result.fact_found is False


def test_preference_is_reviewed_even_when_known() -> None:
    result = RuleBasedQuestionClassifier(_truth_store()).classify(
        "What is your expected salary?"
    )
    assert result.category is QuestionCategory.PREFERENCE
    assert result.route is HandlingRoute.DRAFT_WITH_REVIEW
    assert result.fact_found is True
    assert result.requires_human_review is True


def test_narrative_and_numerical_routes_are_separate() -> None:
    classifier = RuleBasedQuestionClassifier(_truth_store())
    narrative = classifier.classify("Tell us about a difficult data problem you solved.")
    numerical = classifier.classify("How many years of experience do you have with SQL?")
    assert narrative.route is HandlingRoute.DRAFT_WITH_REVIEW
    assert numerical.route is HandlingRoute.CALCULATE
    assert numerical.review_band is ReviewBand.GREEN


def test_unknown_question_escalates() -> None:
    result = RuleBasedQuestionClassifier(_truth_store()).classify(
        "What fictional character best represents your work style?"
    )
    assert result.category is QuestionCategory.UNKNOWN
    assert result.route is HandlingRoute.ESCALATE
    assert result.review_band is ReviewBand.RED


def test_blank_question_is_rejected() -> None:
    with pytest.raises(ValueError, match="cannot be blank"):
        RuleBasedQuestionClassifier(_truth_store()).classify("   ")
