from jobops.knowledge import TruthStore
from jobops.models.candidate import CandidateFact, CandidateProfile, FactRisk


def test_unknown_fact_requires_review() -> None:
    store = TruthStore(CandidateProfile())
    result = store.resolve("security_clearance")
    assert result.found is False
    assert result.requires_human_review is True


def test_high_risk_fact_still_requires_review() -> None:
    profile = CandidateProfile(
        facts=[
            CandidateFact(
                key="authorized_to_work_us",
                value=True,
                verified=True,
                risk=FactRisk.HIGH,
                evidence=["candidate-confirmed"],
            )
        ]
    )
    result = TruthStore(profile).resolve("AUTHORIZED_TO_WORK_US")
    assert result.found is True
    assert result.value is True
    assert result.verified is True
    assert result.requires_human_review is True
