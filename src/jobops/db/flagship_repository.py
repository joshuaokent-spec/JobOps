from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jobops.db.models import FlagshipPreparedJobRecord, FlagshipRunRecord
from jobops.models.flagship_readiness import (
    FlagshipPreparedSnapshot,
    FlagshipReadinessSummary,
)
from jobops.models.flagship_run import FlagshipReadiness, FlagshipRunResult


class FlagshipReadinessRepository(Protocol):
    def save(
        self,
        *,
        candidate_id: str,
        result: FlagshipRunResult,
    ) -> FlagshipReadinessSummary: ...

    def latest(self, profile_id: str) -> FlagshipReadinessSummary | None: ...

    def history(
        self,
        profile_id: str,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> Sequence[FlagshipReadinessSummary]: ...

    def prepared_jobs(
        self,
        run_id: str,
        *,
        readiness: FlagshipReadiness | None = None,
    ) -> Sequence[FlagshipPreparedSnapshot]: ...

    def count_runs(self, profile_id: str) -> int: ...


class SqlAlchemyFlagshipReadinessRepository:
    def __init__(self, session: Session):
        self.session = session

    def save(
        self,
        *,
        candidate_id: str,
        result: FlagshipRunResult,
    ) -> FlagshipReadinessSummary:
        run_id = str(uuid4())
        record = FlagshipRunRecord(
            run_id=run_id,
            profile_id=result.profile_id,
            candidate_id=candidate_id,
            started_at=result.started_at,
            completed_at=result.completed_at,
            total_examined=result.total_examined,
            total_hard_eligible=result.total_hard_eligible,
            total_hard_rejected=result.total_hard_rejected,
            total_fit_eligible=result.total_fit_eligible,
            total_fit_rejected=result.total_fit_rejected,
            prepared_count=result.prepared_count,
            ready_count=result.ready_count,
            review_required_count=result.review_required_count,
            rejection_summary=dict(result.rejection_summary),
        )
        self.session.add(record)
        # Persist the parent run before prepared-job rows reference its run_id.
        # This is required on databases that enforce the foreign key immediately,
        # including PostgreSQL.
        self.session.flush()

        for prepared in result.prepared_jobs:
            evidence_ids = [
                hit.evidence.evidence_id
                for hit in prepared.evidence.hits
            ]
            self.session.add(
                FlagshipPreparedJobRecord(
                    run_id=run_id,
                    job_id=prepared.job.job_id,
                    rank=prepared.rank,
                    score=prepared.score.overall,
                    resume_family_id=prepared.resume_selection.chosen_family_id,
                    resume_selection_score=prepared.resume_selection.chosen_score,
                    resume_low_confidence=prepared.resume_selection.low_confidence,
                    readiness=prepared.readiness.value,
                    readiness_reasons=list(prepared.readiness_reasons),
                    evidence_ids=evidence_ids,
                )
            )

        self.session.flush()
        return self._to_summary(record)

    def latest(self, profile_id: str) -> FlagshipReadinessSummary | None:
        history = self.history(profile_id, limit=1)
        return history[0] if history else None

    def history(
        self,
        profile_id: str,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> Sequence[FlagshipReadinessSummary]:
        statement = (
            select(FlagshipRunRecord)
            .where(FlagshipRunRecord.profile_id == profile_id.strip())
            .order_by(
                FlagshipRunRecord.completed_at.desc(),
                FlagshipRunRecord.created_at.desc(),
                FlagshipRunRecord.run_id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return [
            self._to_summary(record)
            for record in self.session.scalars(statement).all()
        ]

    def prepared_jobs(
        self,
        run_id: str,
        *,
        readiness: FlagshipReadiness | None = None,
    ) -> Sequence[FlagshipPreparedSnapshot]:
        statement = select(FlagshipPreparedJobRecord).where(
            FlagshipPreparedJobRecord.run_id == run_id
        )
        if readiness is not None:
            statement = statement.where(
                FlagshipPreparedJobRecord.readiness == readiness.value
            )
        statement = statement.order_by(
            FlagshipPreparedJobRecord.rank.asc(),
            FlagshipPreparedJobRecord.job_id.asc(),
        )
        return [
            self._prepared_to_domain(record)
            for record in self.session.scalars(statement).all()
        ]

    def count_runs(self, profile_id: str) -> int:
        statement = (
            select(func.count())
            .select_from(FlagshipRunRecord)
            .where(FlagshipRunRecord.profile_id == profile_id.strip())
        )
        return int(self.session.scalar(statement) or 0)

    def _to_summary(self, record: FlagshipRunRecord) -> FlagshipReadinessSummary:
        return FlagshipReadinessSummary(
            run_id=record.run_id,
            profile_id=record.profile_id,
            candidate_id=record.candidate_id,
            started_at=_as_utc(record.started_at),
            completed_at=_as_utc(record.completed_at),
            total_examined=record.total_examined,
            total_hard_eligible=record.total_hard_eligible,
            total_hard_rejected=record.total_hard_rejected,
            total_fit_eligible=record.total_fit_eligible,
            total_fit_rejected=record.total_fit_rejected,
            prepared_count=record.prepared_count,
            ready_count=record.ready_count,
            review_required_count=record.review_required_count,
            rejection_summary=dict(record.rejection_summary or {}),
            prepared_jobs=list(self.prepared_jobs(record.run_id)),
        )

    @staticmethod
    def _prepared_to_domain(record: FlagshipPreparedJobRecord) -> FlagshipPreparedSnapshot:
        return FlagshipPreparedSnapshot(
            run_id=record.run_id,
            job_id=record.job_id,
            rank=record.rank,
            score=record.score,
            resume_family_id=record.resume_family_id,
            resume_selection_score=record.resume_selection_score,
            resume_low_confidence=record.resume_low_confidence,
            readiness=FlagshipReadiness(record.readiness),
            readiness_reasons=list(record.readiness_reasons or []),
            evidence_ids=list(record.evidence_ids or []),
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
