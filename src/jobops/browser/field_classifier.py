import re
from dataclasses import dataclass
from typing import Final

from jobops.models.application_question import HandlingRoute, QuestionCategory, ReviewBand
from jobops.models.browser import BrowserFieldDescriptor, BrowserFieldKind, BrowserPageSnapshot
from jobops.models.form_mapping import (
    ApplicationFieldSemantic,
    MappingSource,
    SemanticFieldMapping,
    SemanticPageMapping,
)


@dataclass(frozen=True, slots=True)
class _SemanticRule:
    semantic: ApplicationFieldSemantic
    pattern: re.Pattern[str]
    confidence: float
    fact_key: str | None = None
    allowed_kinds: frozenset[BrowserFieldKind] | None = None


def _rule(
    semantic: ApplicationFieldSemantic,
    pattern: str,
    confidence: float,
    *,
    fact_key: str | None = None,
    allowed_kinds: set[BrowserFieldKind] | None = None,
) -> _SemanticRule:
    return _SemanticRule(
        semantic=semantic,
        pattern=re.compile(pattern, re.IGNORECASE),
        confidence=confidence,
        fact_key=fact_key,
        allowed_kinds=frozenset(allowed_kinds) if allowed_kinds else None,
    )


_URL_KINDS = {BrowserFieldKind.URL, BrowserFieldKind.TEXT}
_TEXT_KINDS = {
    BrowserFieldKind.TEXT,
    BrowserFieldKind.EMAIL,
    BrowserFieldKind.TELEPHONE,
    BrowserFieldKind.URL,
    BrowserFieldKind.NUMBER,
    BrowserFieldKind.DATE,
    BrowserFieldKind.TEXTAREA,
    BrowserFieldKind.SELECT,
    BrowserFieldKind.CHECKBOX,
    BrowserFieldKind.RADIO,
}

_RULES: Final[tuple[_SemanticRule, ...]] = (
    _rule(
        ApplicationFieldSemantic.DEMOGRAPHIC_SELF_ID,
        r"\b(?:race|ethnicity|ethnic|gender|sexual orientation|disability|disabled|veteran status|"
        r"self[- ]identif(?:y|ication)|eeo|equal employment opportunity)\b",
        0.99,
    ),
    _rule(
        ApplicationFieldSemantic.CONSENT_ATTESTATION,
        r"\b(?:consent|i certify|certify that|attest|acknowledge|privacy policy|data retention|"
        r"retain my data|agree to (?:the )?terms|terms and conditions)\b",
        0.99,
        allowed_kinds={
            BrowserFieldKind.CHECKBOX,
            BrowserFieldKind.RADIO,
            BrowserFieldKind.SELECT,
            BrowserFieldKind.TEXT,
        },
    ),
    _rule(
        ApplicationFieldSemantic.WORK_AUTHORIZATION,
        r"\b(?:work authorization|authorized to work|authorised to work|legally (?:authorized|"
        r"authorised|eligible) to work|right to work|work eligibility)\b",
        0.99,
        fact_key="work_authorization",
    ),
    _rule(
        ApplicationFieldSemantic.SPONSORSHIP,
        r"\b(?:visa sponsorship|sponsorship|require sponsor|requires sponsor|need sponsor|"
        r"immigration sponsorship)\b",
        0.99,
        fact_key="requires_sponsorship",
    ),
    _rule(
        ApplicationFieldSemantic.SECURITY_CLEARANCE,
        r"\b(?:security clearance|clearance level|active clearance)\b",
        0.99,
        fact_key="security_clearance",
    ),
    _rule(
        ApplicationFieldSemantic.PRIOR_EMPLOYMENT,
        r"\b(?:previously employed|prior employment|worked (?:for|at) (?:this|our) company|"
        r"former employee|employee before)\b",
        0.98,
        fact_key="prior_company_employment",
    ),
    _rule(
        ApplicationFieldSemantic.RESUME,
        r"\b(?:resume|résumé|curriculum vitae|\bcv\b)\b",
        0.99,
        fact_key="selected_resume",
        allowed_kinds={BrowserFieldKind.FILE},
    ),
    _rule(
        ApplicationFieldSemantic.COVER_LETTER,
        r"\bcover letter\b",
        0.99,
        allowed_kinds={BrowserFieldKind.FILE, BrowserFieldKind.TEXTAREA, BrowserFieldKind.TEXT},
    ),
    _rule(
        ApplicationFieldSemantic.LINKEDIN_URL,
        r"\blinked\s*in\b",
        0.99,
        fact_key="linkedin_url",
        allowed_kinds=_URL_KINDS,
    ),
    _rule(
        ApplicationFieldSemantic.GITHUB_URL,
        r"\bgithub\b",
        0.99,
        fact_key="github_url",
        allowed_kinds=_URL_KINDS,
    ),
    _rule(
        ApplicationFieldSemantic.PORTFOLIO_URL,
        r"\b(?:portfolio|work samples?)\b",
        0.97,
        fact_key="portfolio_url",
        allowed_kinds=_URL_KINDS,
    ),
    _rule(
        ApplicationFieldSemantic.PERSONAL_WEBSITE,
        r"\b(?:personal website|website url|homepage|personal site)\b",
        0.94,
        fact_key="personal_website",
        allowed_kinds=_URL_KINDS,
    ),
    _rule(
        ApplicationFieldSemantic.FIRST_NAME,
        r"\b(?:first|given|forename) name\b|\bfirst_name\b|\bfname\b",
        0.99,
        fact_key="first_name",
    ),
    _rule(
        ApplicationFieldSemantic.LAST_NAME,
        r"\b(?:last|family|surname) name\b|\blast_name\b|\blname\b",
        0.99,
        fact_key="last_name",
    ),
    _rule(
        ApplicationFieldSemantic.FULL_NAME,
        r"\b(?:full|legal|preferred) name\b|\bcandidate name\b|^name$",
        0.94,
        fact_key="full_name",
    ),
    _rule(
        ApplicationFieldSemantic.EMAIL,
        r"\b(?:email|e-mail)\b",
        0.99,
        fact_key="email",
        allowed_kinds={BrowserFieldKind.EMAIL, BrowserFieldKind.TEXT},
    ),
    _rule(
        ApplicationFieldSemantic.PHONE,
        r"\b(?:phone|telephone|mobile|cell(?: phone)?)\b",
        0.98,
        fact_key="phone",
        allowed_kinds={BrowserFieldKind.TELEPHONE, BrowserFieldKind.TEXT},
    ),
    _rule(
        ApplicationFieldSemantic.POSTAL_CODE,
        r"\b(?:zip|zip code|postal|postal code|postcode)\b",
        0.98,
        fact_key="postal_code",
    ),
    _rule(
        ApplicationFieldSemantic.STREET_ADDRESS,
        r"\b(?:street address|address line|address 1|address1|mailing address|home address)\b",
        0.96,
        fact_key="street_address",
    ),
    _rule(
        ApplicationFieldSemantic.CITY,
        r"\bcity\b",
        0.96,
        fact_key="city",
    ),
    _rule(
        ApplicationFieldSemantic.REGION,
        r"\b(?:state|province|state/province|region)\b",
        0.92,
        fact_key="region",
    ),
    _rule(
        ApplicationFieldSemantic.COUNTRY,
        r"\bcountry\b",
        0.97,
        fact_key="country",
    ),
    _rule(
        ApplicationFieldSemantic.SALARY_EXPECTATION,
        r"\b(?:salary|compensation|desired pay|expected pay|pay range|salary expectation)\b",
        0.98,
        fact_key="salary_expectation",
    ),
    _rule(
        ApplicationFieldSemantic.RELOCATION,
        r"\b(?:relocate|relocation|willing to move)\b",
        0.98,
        fact_key="willing_to_relocate",
    ),
    _rule(
        ApplicationFieldSemantic.WORK_MODE,
        r"\b(?:remote|hybrid|on[- ]?site|work mode|work arrangement|location preference)\b",
        0.90,
        fact_key="preferred_work_mode",
    ),
    _rule(
        ApplicationFieldSemantic.TRAVEL,
        r"\b(?:willing to travel|travel percentage|travel requirement|how much travel)\b",
        0.97,
        fact_key="travel_willingness",
    ),
    _rule(
        ApplicationFieldSemantic.START_DATE,
        r"\b(?:start date|available to start|availability date|notice period|earliest start)\b",
        0.97,
        fact_key="availability",
    ),
    _rule(
        ApplicationFieldSemantic.CERTIFICATIONS,
        r"\b(?:certification|certifications|certificate|professional credential|licensed?)\b",
        0.94,
        fact_key="certifications",
    ),
    _rule(
        ApplicationFieldSemantic.EDUCATION,
        r"\b(?:education|degree|university|college|school|major|field of study)\b",
        0.91,
        fact_key="highest_education",
    ),
    _rule(
        ApplicationFieldSemantic.NARRATIVE_QUESTION,
        r"\b(?:tell us about|tell me about|describe|explain|give (?:us |me )?(?:an? )?example|"
        r"share (?:an? )?example|why (?:do|are|would|should)|why this|why our|"
        r"what interests you|what excites you|walk (?:us|me) through|how did you|"
        r"how have you)\b",
        0.92,
        allowed_kinds={BrowserFieldKind.TEXTAREA, BrowserFieldKind.TEXT},
    ),
)


class SemanticFieldClassifier:
    """Map structural browser controls to application semantics without creating answers."""

    def classify_page(self, page: BrowserPageSnapshot) -> SemanticPageMapping:
        mappings = [
            self.classify_field(field)
            for form in page.forms
            for field in form.fields
        ]
        mapped = sum(
            mapping.semantic
            not in {ApplicationFieldSemantic.UNKNOWN, ApplicationFieldSemantic.SUBMIT_CONTROL}
            for mapping in mappings
        )
        unresolved = sum(
            mapping.semantic is ApplicationFieldSemantic.UNKNOWN for mapping in mappings
        )
        sensitive = sum(mapping.review_band is ReviewBand.RED for mapping in mappings)
        return SemanticPageMapping(
            page=page,
            mappings=mappings,
            mapped_fields=mapped,
            unresolved_fields=unresolved,
            sensitive_fields=sensitive,
            submission_allowed=False,
        )

    def classify_field(self, field: BrowserFieldDescriptor) -> SemanticFieldMapping:
        if field.is_submit_control or field.kind is BrowserFieldKind.SUBMIT:
            return self._mapping(
                field,
                semantic=ApplicationFieldSemantic.SUBMIT_CONTROL,
                confidence=1.0,
                source=MappingSource.DETERMINISTIC,
                matched_signals=["structural: submit-capable control"],
            )

        signal_text, signals = self._signals(field)
        candidates = [
            rule
            for rule in _RULES
            if (rule.allowed_kinds is None or field.kind in rule.allowed_kinds)
            and rule.pattern.search(signal_text)
        ]
        if not candidates:
            return self._mapping(
                field,
                semantic=ApplicationFieldSemantic.UNKNOWN,
                confidence=0.0,
                source=MappingSource.UNRESOLVED,
                matched_signals=signals,
                ambiguous=False,
            )

        ranked = sorted(candidates, key=lambda rule: rule.confidence, reverse=True)
        best = ranked[0]
        ambiguous = any(
            rule.semantic is not best.semantic and best.confidence - rule.confidence <= 0.03
            for rule in ranked[1:]
        )
        if ambiguous:
            semantics = sorted(
                {
                    rule.semantic.value
                    for rule in ranked
                    if best.confidence - rule.confidence <= 0.03
                }
            )
            return self._mapping(
                field,
                semantic=ApplicationFieldSemantic.UNKNOWN,
                confidence=best.confidence,
                source=MappingSource.UNRESOLVED,
                matched_signals=[*signals, f"ambiguous candidates: {', '.join(semantics)}"],
                ambiguous=True,
            )

        return self._mapping(
            field,
            semantic=best.semantic,
            confidence=best.confidence,
            source=MappingSource.DETERMINISTIC,
            matched_signals=[*signals, f"matched semantic rule: {best.semantic.value}"],
            fact_key=best.fact_key,
            question_text=self._question_text(field, best.semantic),
        )

    @staticmethod
    def _signals(field: BrowserFieldDescriptor) -> tuple[str, list[str]]:
        raw = {
            "label": field.label,
            "accessible_name": field.accessible_name,
            "name": field.name,
            "id": field.element_id,
            "placeholder": field.placeholder,
            "input_type": field.input_type,
        }
        signals = [f"{key}: {value}" for key, value in raw.items() if value]
        option_text = " ".join(option.label for option in field.options if option.label)
        if option_text:
            signals.append(f"options: {option_text}")
        normalized = " | ".join(signals).replace("_", " ").replace("-", " ")
        return normalized, signals

    @staticmethod
    def _question_text(
        field: BrowserFieldDescriptor,
        semantic: ApplicationFieldSemantic,
    ) -> str | None:
        if semantic not in {
            ApplicationFieldSemantic.NARRATIVE_QUESTION,
            ApplicationFieldSemantic.WORK_AUTHORIZATION,
            ApplicationFieldSemantic.SPONSORSHIP,
            ApplicationFieldSemantic.SECURITY_CLEARANCE,
            ApplicationFieldSemantic.PRIOR_EMPLOYMENT,
            ApplicationFieldSemantic.DEMOGRAPHIC_SELF_ID,
            ApplicationFieldSemantic.CONSENT_ATTESTATION,
            ApplicationFieldSemantic.SALARY_EXPECTATION,
            ApplicationFieldSemantic.RELOCATION,
            ApplicationFieldSemantic.WORK_MODE,
            ApplicationFieldSemantic.TRAVEL,
            ApplicationFieldSemantic.START_DATE,
        }:
            return None
        return field.label or field.accessible_name or field.placeholder or field.name

    @classmethod
    def _mapping(
        cls,
        field: BrowserFieldDescriptor,
        *,
        semantic: ApplicationFieldSemantic,
        confidence: float,
        source: MappingSource,
        matched_signals: list[str],
        fact_key: str | None = None,
        question_text: str | None = None,
        ambiguous: bool = False,
    ) -> SemanticFieldMapping:
        category, route, band, review = cls._policy(semantic)
        return SemanticFieldMapping(
            field=field,
            semantic=semantic,
            confidence=confidence,
            source=source,
            matched_signals=matched_signals,
            fact_key=fact_key,
            question_text=question_text,
            question_category=category,
            route=route,
            review_band=band,
            requires_human_review=review,
            ambiguous=ambiguous,
        )

    @staticmethod
    def _policy(
        semantic: ApplicationFieldSemantic,
    ) -> tuple[QuestionCategory, HandlingRoute, ReviewBand, bool]:
        if semantic in {
            ApplicationFieldSemantic.WORK_AUTHORIZATION,
            ApplicationFieldSemantic.SPONSORSHIP,
            ApplicationFieldSemantic.PRIOR_EMPLOYMENT,
            ApplicationFieldSemantic.SECURITY_CLEARANCE,
            ApplicationFieldSemantic.DEMOGRAPHIC_SELF_ID,
            ApplicationFieldSemantic.CONSENT_ATTESTATION,
        }:
            return (
                QuestionCategory.LEGAL_SENSITIVE,
                HandlingRoute.HUMAN_REVIEW,
                ReviewBand.RED,
                True,
            )
        if semantic in {
            ApplicationFieldSemantic.SALARY_EXPECTATION,
            ApplicationFieldSemantic.RELOCATION,
            ApplicationFieldSemantic.WORK_MODE,
            ApplicationFieldSemantic.TRAVEL,
            ApplicationFieldSemantic.START_DATE,
        }:
            return (
                QuestionCategory.PREFERENCE,
                HandlingRoute.DRAFT_WITH_REVIEW,
                ReviewBand.YELLOW,
                True,
            )
        if semantic in {
            ApplicationFieldSemantic.NARRATIVE_QUESTION,
            ApplicationFieldSemantic.COVER_LETTER,
        }:
            return (
                QuestionCategory.NARRATIVE,
                HandlingRoute.DRAFT_WITH_REVIEW,
                ReviewBand.YELLOW,
                True,
            )
        if semantic in {
            ApplicationFieldSemantic.UNKNOWN,
            ApplicationFieldSemantic.SUBMIT_CONTROL,
        }:
            return (
                QuestionCategory.UNKNOWN,
                HandlingRoute.ESCALATE,
                ReviewBand.RED,
                True,
            )
        return (
            QuestionCategory.FACTUAL,
            HandlingRoute.AUTO_FILL,
            ReviewBand.GREEN,
            False,
        )
