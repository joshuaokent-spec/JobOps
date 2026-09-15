from dataclasses import dataclass
from typing import Any

from jobops.models.candidate import CandidateFact, CandidateProfile, FactRisk


@dataclass(frozen=True, slots=True)
class FactResolution:
    key: str
    found: bool
    value: Any = None
    verified: bool = False
    risk: FactRisk | None = None
    evidence: tuple[str, ...] = ()
    requires_human_review: bool = True


class TruthStore:
    """Canonical evidence-backed candidate facts.

    The store deliberately separates *known* from *safe to auto-answer*. A fact may exist but
    still require human review if it is unverified or marked high-risk.
    """

    def __init__(self, profile: CandidateProfile):
        self._facts: dict[str, CandidateFact] = {
            fact.key.casefold(): fact for fact in profile.facts
        }

    def resolve(self, key: str) -> FactResolution:
        fact = self._facts.get(key.casefold())
        if fact is None:
            return FactResolution(key=key, found=False)

        review_required = (not fact.verified) or fact.risk is FactRisk.HIGH
        return FactResolution(
            key=fact.key,
            found=True,
            value=fact.value,
            verified=fact.verified,
            risk=fact.risk,
            evidence=tuple(fact.evidence),
            requires_human_review=review_required,
        )
