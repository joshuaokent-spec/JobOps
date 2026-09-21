from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select\nfrom sqlalchemy.orm import Session

from jobops.db.models import CandidateOnboardingRecord
from jobops.models.candidate import CandidateProfile
from jobops.models.onboarding import (
    CandidateOnboarding,
    CandidateOnboardingPayload,
    CandidateOnboardingStatus,
    FlagshipRunDefaults,
    ResumeAsset,
    onboarding_status,
)
from jobops.models.resume_evidence import ResumeEvidenceBase


class CandidateOnboardingRepository(Protocol):
    def save(self, payload: CandidateOnboardingPayload) -> CandidateOnboarding: ...

    def get(self, candidate_id: str) -> CandidateOnboarding | None: ...

    def status(self, candidate_id: str) -> CandidateOnboardingStatus: ...

    def delete(self, candidate_id: str) -> bool: ...

    def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[CandidateOnboarding]: ...


class SqlAlchemyCandidateOnboardingRepository:
    def __init__(self, session: Session):
        self.session = session

    def save(self, payload: CandidateOnboardingPayload) -> CandidateOnboarding:
        candidate_id = payload.candidate.candidate_id
        record = self.session.get(CandidateOnboardingRecord, candidate_id)
        now = datetime.now(UTC)
        values = {
            "candidate_profile": payload.candidate.model_dump(mode="json"),
            "resume_evidence": payload.resume_evidence.model_dump(mode="json"),
            "resume_assets": [
                asset.model_dump(mode="json") for asset in payload.resume_assets
            ],
            "run_defaults": payload.run_defaults.model_dump(mode="json"),
            "updated_at": now,
        }

        if record is None:
            record = CandidateOnboardingRecord(
                candidate_id=candidate_id,
                created_at=now,
                **values,
            )
            self.session.add(record)
        else:
            for key, value in values.items():
                setattr(record, key, value)

        self.session.flush()
        return self._to_domain(record)

    def get(self, candidate_id: str) -> CandidateOnboarding | None:
        record = self.session.get(CandidateOnboardingRecord, candidate_id.strip())
        return None if record is None else self._to_domain(record)

    def status(self, candidate_id: str) -> CandidateOnboardingStatus:
        return onboarding_status(
            self.get(candidate_id),
            candidate_id=candidate_id.strip(),
        )

    def delete(self, candidate_id: str) -> bool:
        record = self.session.get(CandidateOnboardingRecord, candidate_id.strip())
        if record is None:
            return False
        self.session.delete(record)
        self.session.flush()
        return True

    def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[CandidateOnboarding]:
        statement = (
            select(CandidateOnboardingRecord)
            .order_by(CandidateOnboardingRecord.candidate_id.asc())
            .limit(limit)
            .offset(offset)
        )
        return [
            self._to_domain(record)
            for record in self.session.scalars(statement).all()
        ]

    @staticmethod
    def _to_domain(record: CandidateOnboardingRecord) -> CandidateOnboarding:
        return CandidateOnboarding(
            candidate=CandidateProfile.model_validate(record.candidate_profile),
            resume_evidence=ResumeEvidenceBase.model_validate(record.resume_evidence),
            resume_assets=[
                ResumeAsset.model_validate(item)
                for item in (record.resume_assets or [])
            ],
            run_defaults=FlagshipRunDefaults.model_validate(record.run_defaults),
            created_at=_as_utc(record.created_at),
            updated_at=_as_utc(record.updated_at),
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
