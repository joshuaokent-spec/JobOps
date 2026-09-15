import re
from dataclasses import dataclass
from typing import Final

from jobops.knowledge.truth_store import FactResolution, TruthStore
from jobops.models.application_question import (
    HandlingRoute,
    QuestionCategory,
    QuestionClassification,
    ReviewBand,
    ReviewPriority,
)
from jobops.models.candidate import FactRisk


@dataclass(frozen=True, slots=True)
class _Rule:
    pattern: re.Pattern[str]
    label: str
    fact_key: str | None = None


def _rule(pattern: str, label: str, fact_key: str | None = None) -> _Rule:
    return _Rule(re.compile(pattern, re.IGNORECASE), label, fact_key)


_LEGAL_RULES: Final[tuple[_Rule, ...]] = (
    _rule(
        r"authori[sz](?:ed|ation).*work|legally.*work",
        "work authorization",
        "work_authorization",
    ),
    _rule(
        r"sponsor(?:ship)?|visa sponsorship|immigration status",
        "employment sponsorship",
        "requires_sponsorship",
    ),
    _rule(
        r"security clearance|clearance level",
        "security clearance",
        "security_clearance",
    ),
    _rule(
        r"criminal|convict(?:ed|ion)|felony|misdemeanor",
        "criminal-history attestation",
        "criminal_history",
    ),
    _rule(
        r"previously employed|worked (?:for|at) (?:this|our) company",
        "prior-employment attestation",
        "prior_company_employment",
    ),
    _rule(
        r"race|ethnicity|gender|sex|sexual orientation|disab(?:ility|led)|veteran status",
        "protected or sensitive self-identification",
    ),
)

_PREFERENCE_RULES: Final[tuple[_Rule, ...]] = (
    _rule(
        r"relocat(?:e|ion)|willing to move",
        "relocation preference",
        "willing_to_relocate",
    ),
    _rule(
        r"salary|compensation|pay range|desired pay|expected pay",
        "compensation preference",
        "salary_expectation",
    ),
    _rule(
        r"remote|hybrid|on[- ]?site|work location preference",
        "work-mode preference",
        "preferred_work_mode",
    ),
    _rule(
        r"willing to travel|travel percentage|how much travel",
        "travel preference",
        "travel_willingness",
    ),
    _rule(
        r"start date|available to start|notice period",
        "start-date preference",
        "availability",
    ),
)

_NARRATIVE_RULES: Final[tuple[_Rule, ...]] = (
    _rule(r"\btell (?:us|me) about\b", "open-ended experience prompt"),
    _rule(r"\bdescribe\b", "open-ended description prompt"),
    _rule(r"\bgive (?:us |me )?(?:an? )?example\b", "behavioral example prompt"),
    _rule(r"\bshare (?:an? )?example\b", "behavioral example prompt"),
    _rule(
        r"\bwhy (?:do|are|would|should|did)\b|\bwhy this\b|\bwhy our\b",
        "motivation/reasoning prompt",
    ),
    _rule(r"\bwhat interests you\b|\bwhat excites you\b", "motivation prompt"),
    _rule(r"\bwalk (?:us|me) through\b", "open-ended process prompt"),
    _rule(r"\bhow did you\b|\bhow have you\b", "experience narrative prompt"),
)

_NUMERICAL_RULES: Final[tuple[_Rule, ...]] = (
    _rule(
        r"how many years|number of years|years of experience",
        "experience-duration calculation",
    ),
    _rule(
        r"how many (?:projects|people|reports|records|customers|users)",
        "numeric experience calculation",
    ),
)

_FACTUAL_RULES: Final[tuple[_Rule, ...]] = (
    _rule(r"certif(?:ication|ied)|license[ds]?", "certification fact", "certifications"),
    _rule(
        r"highest (?:degree|education)|education level|degree (?:do you|have you)",
        "education fact",
        "highest_education",
    ),
    _rule(r"portfolio|github|website url|linkedin", "candidate-link fact", "portfolio_links"),
)


class RuleBasedQuestionClassifier:
    """Classify application questions before any answer generation occurs."""

    def __init__(self, truth_store: TruthStore | None = None):
        self.truth_store = truth_store

    def classify(self, question: str) -> QuestionClassification:
        text = " ".join(question.split()).strip()
        if not text:
            raise ValueError("question cannot be blank")

        legal = self._first_match(text, _LEGAL_RULES)
        if legal is not None:
            resolution = self._resolve(legal.fact_key)
            return self._result(
                text,
                category=QuestionCategory.LEGAL_SENSITIVE,
                route=HandlingRoute.HUMAN_REVIEW,
                band=ReviewBand.RED,
                risk=FactRisk.HIGH,
                confidence=0.99,
                priority=ReviewPriority.CRITICAL,
                requires_review=True,
                rule=legal,
                resolution=resolution,
                reason="Consequential or sensitive questions are never auto-answered.",
            )

        preference = self._first_match(text, _PREFERENCE_RULES)
        if preference is not None:
            resolution = self._resolve(preference.fact_key)
            return self._result(
                text,
                category=QuestionCategory.PREFERENCE,
                route=HandlingRoute.DRAFT_WITH_REVIEW,
                band=ReviewBand.YELLOW,
                risk=FactRisk.MEDIUM,
                confidence=0.94,
                priority=ReviewPriority.NORMAL,
                requires_review=True,
                rule=preference,
                resolution=resolution,
                reason="Preferences may be contextual and require candidate confirmation.",
            )

        narrative = self._first_match(text, _NARRATIVE_RULES)
        if narrative is not None:
            return self._result(
                text,
                category=QuestionCategory.NARRATIVE,
                route=HandlingRoute.DRAFT_WITH_REVIEW,
                band=ReviewBand.YELLOW,
                risk=FactRisk.MEDIUM,
                confidence=0.92,
                priority=ReviewPriority.NORMAL,
                requires_review=True,
                rule=narrative,
                resolution=None,
                reason="Narrative prompts require evidence-grounded drafting and review.",
            )

        numerical = self._first_match(text, _NUMERICAL_RULES)
        if numerical is not None:
            return self._result(
                text,
                category=QuestionCategory.NUMERICAL,
                route=HandlingRoute.CALCULATE,
                band=ReviewBand.GREEN,
                risk=FactRisk.LOW,
                confidence=0.90,
                priority=ReviewPriority.LOW,
                requires_review=False,
                rule=numerical,
                resolution=None,
                reason=(
                    "The question should be answered by deterministic calculation, "
                    "not generation."
                ),
            )

        factual = self._first_match(text, _FACTUAL_RULES)
        if factual is not None:
            return self._classify_factual(text, factual)

        return QuestionClassification(
            question=text,
            category=QuestionCategory.UNKNOWN,
            route=HandlingRoute.ESCALATE,
            review_band=ReviewBand.RED,
            risk=FactRisk.MEDIUM,
            confidence=0.35,
            priority=ReviewPriority.HIGH,
            requires_human_review=True,
            reasons=[
                "No deterministic classifier rule matched the question.",
                "Unresolved questions are escalated rather than guessed.",
            ],
        )

    def _classify_factual(self, text: str, rule: _Rule) -> QuestionClassification:
        resolution = self._resolve(rule.fact_key)
        if resolution is None or not resolution.found:
            return self._result(
                text,
                category=QuestionCategory.FACTUAL,
                route=HandlingRoute.ESCALATE,
                band=ReviewBand.RED,
                risk=FactRisk.LOW,
                confidence=0.90,
                priority=ReviewPriority.HIGH,
                requires_review=True,
                rule=rule,
                resolution=resolution,
                reason=(
                    "The question maps to a fact key, but no verified answer "
                    "is safely available."
                ),
            )

        if resolution.requires_human_review:
            band = ReviewBand.RED if resolution.risk is FactRisk.HIGH else ReviewBand.YELLOW
            priority = (
                ReviewPriority.CRITICAL
                if resolution.risk is FactRisk.HIGH
                else ReviewPriority.HIGH
            )
            return self._result(
                text,
                category=QuestionCategory.FACTUAL,
                route=HandlingRoute.HUMAN_REVIEW,
                band=band,
                risk=resolution.risk or FactRisk.MEDIUM,
                confidence=0.96,
                priority=priority,
                requires_review=True,
                rule=rule,
                resolution=resolution,
                reason="The mapped fact exists but TruthStore requires human review.",
            )

        return self._result(
            text,
            category=QuestionCategory.FACTUAL,
            route=HandlingRoute.AUTO_FILL,
            band=ReviewBand.GREEN,
            risk=resolution.risk or FactRisk.LOW,
            confidence=0.98,
            priority=ReviewPriority.LOW,
            requires_review=False,
            rule=rule,
            resolution=resolution,
            reason="A verified low-risk TruthStore fact is available for auto-fill.",
        )

    def _resolve(self, fact_key: str | None) -> FactResolution | None:
        if fact_key is None or self.truth_store is None:
            return None
        return self.truth_store.resolve(fact_key)

    @staticmethod
    def _first_match(text: str, rules: tuple[_Rule, ...]) -> _Rule | None:
        return next((rule for rule in rules if rule.pattern.search(text)), None)

    @staticmethod
    def _result(
        question: str,
        *,
        category: QuestionCategory,
        route: HandlingRoute,
        band: ReviewBand,
        risk: FactRisk,
        confidence: float,
        priority: ReviewPriority,
        requires_review: bool,
        rule: _Rule,
        resolution: FactResolution | None,
        reason: str,
    ) -> QuestionClassification:
        reasons = [f"Matched rule: {rule.label}.", reason]
        if resolution is not None:
            if resolution.found:
                reasons.append(
                    "TruthStore match is verified."
                    if resolution.verified
                    else "TruthStore match is not verified."
                )
            else:
                reasons.append("No TruthStore value exists for the mapped fact key.")

        return QuestionClassification(
            question=question,
            category=category,
            route=route,
            review_band=band,
            risk=risk,
            confidence=confidence,
            priority=priority,
            requires_human_review=requires_review,
            matched_fact_key=rule.fact_key,
            fact_found=bool(resolution and resolution.found),
            fact_verified=bool(resolution and resolution.verified),
            reasons=reasons,
        )
