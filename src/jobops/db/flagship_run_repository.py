from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobops.db.models import FlagshipRunJobRecord, FlagshipRunRecord
from jobops.models.flagship_inbox import (
    FlagshipReadinessSummary,
    FlagshipRunJobSnapshot,
)
from jobops.models.flagship_run import FlagshipReadiness, FlagshipRunResult


class FlagshipRunRepository(Protocol):
    def save(self, result: FlagshipRunResult, *, candidate_id: str) -> FlagshipReadinessSummary: ...

    def latest(self, profile_id: str) -> FlagshipReadinessSummary | None: ...


class SqlAlchemyFlagshipRunRepository:
    def __init__(self, session: Session):
        self.session = session

    def save(
        self,
        result: FlagshipRunResult,
        *,
        candidate_id: str,
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

        for item in result.prepared_jobs:
            self.session.add(
                FlagshipRunJobRecord(
                    run_job_id=f"{run_id}:{item.job.job_id}",
                    run_id=run_id,
                    job_id=item.job.job_id,
                    rank=item.rank,
                    company=item.job.company,
                    title=item.job.title,
                    score=item.score.overall,
                    family_id=item.resume_selection.chosen_family_id,
                    family_score=item.resume_selection.chosen_score,
                    readiness=item.readiness.value,
                    readiness_reasons=list(item.readiness_reasons),
                    evidence_ids=[
                        hit.evidence.evidence_id for hit in item.evidence.hits
                    ],
                )
            )

        self.session.flush()
        return self._to_summary(record, self._jobs(run_id))

    def latest(self, profile_id: str) -> FlagshipReadinessSummary | None:
        statement = (
            select(FlagshipRunRecord)
            .where(FlagshipRunRecord.profile_id == profile_id)
            .order_by(
                FlagshipRunRecord.completed_at.desc(),
                FlagshipRunRecord.created_at.desc(),
                FlagshipRunRecord.run_id.desc(),
            )
            .limit(1)
        )
        record = self.session.scalar(statement)
        if record is None:
            return None
        return self._to_summary(record, self._jobs(record.run_id))

    def _jobs(self, run_id: str) -> Sequence[FlagshipRunJobRecord]:
        statement = (
            select(FlagshipRunJobRecord)
            .where(FlagshipRunJobRecord.run_id == run_id)
            .order_by(
                FlagshipRunJobRecord.rank.asc(),
                FlagshipRunJobRecord.job_id.asc(),
            )
        )
        return self.session.scalars(statement).all()

    @staticmethod
    def _to_summary(
        record: FlagshipRunRecord,
        jobs: Sequence[FlagshipRunJobRecord],
    ) -> FlagshipReadinessSummary:
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
            jobs=[
                FlagshipRunJobSnapshot(
                    run_id=item.run_id,
                    job_id=item.job_id,
                    rank=item.rank,
                    company=item.company,
                    title=item.title,
                    score=item.score,
                    family_id=item.family_id,
                    family_score=item.family_score,
                    readiness=FlagshipReadiness(item.readiness),
                    readiness_reasons=list(item.readiness_reasons or []),
                    evidence_ids=list(item.evidence_ids or []),
                )
                for item in jobs
            ],
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
