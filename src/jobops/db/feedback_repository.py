from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from jobops.db.models import FeedbackEventRecord
from jobops.models.feedback import (
    FeedbackEvent,
    FeedbackEventCreate,
    FeedbackEventSource,
    FeedbackEventType,
)


class FeedbackRepository(Protocol):
    def create(
        self,
        event: FeedbackEventCreate,
        *,
        observed_at: datetime,
    ) -> FeedbackEvent: ...

    def get(self, event_id: str) -> FeedbackEvent | None: ...

    def get_by_idempotency_key(self, idempotency_key: str) -> FeedbackEvent | None: ...

    def list(
        self,
        *,
        job_id: str | None = None,
        application_id: str | None = None,
        event_type: FeedbackEventType | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
        observed_to: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[FeedbackEvent]: ...

    def count(
        self,
        *,
        job_id: str | None = None,
        application_id: str | None = None,
        event_type: FeedbackEventType | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
        observed_to: datetime | None = None,
    ) -> int: ...


class SqlAlchemyFeedbackRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        event: FeedbackEventCreate,
        *,
        observed_at: datetime,
    ) -> FeedbackEvent:
        record = FeedbackEventRecord(
            event_id=event.event_id,
            event_type=event.event_type.value,
            job_id=event.job_id,
            application_id=event.application_id,
            candidate_id=event.candidate_id,
            resume_family_id=event.resume_family_id,
            occurred_at=event.occurred_at,
            observed_at=observed_at,
            source=event.source.value,
            actor=event.actor,
            idempotency_key=event.idempotency_key,
            schema_version=event.schema_version,
            metadata_json=dict(event.metadata),
            model_name=event.model_name,
            model_version=event.model_version,
            experiment_id=event.experiment_id,
        )
        try:
            with self.session.begin_nested():
                self.session.add(record)
                self.session.flush()
        except IntegrityError:
            existing = self.get_by_idempotency_key(event.idempotency_key)
            if existing is not None:
                return existing
            raise
        return self._to_domain(record)

    def get(self, event_id: str) -> FeedbackEvent | None:
        record = self.session.get(FeedbackEventRecord, event_id)
        return None if record is None else self._to_domain(record)

    def get_by_idempotency_key(self, idempotency_key: str) -> FeedbackEvent | None:
        record = self.session.scalar(
            select(FeedbackEventRecord).where(
                FeedbackEventRecord.idempotency_key == idempotency_key
            )
        )
        return None if record is None else self._to_domain(record)

    def list(
        self,
        *,
        job_id: str | None = None,
        application_id: str | None = None,
        event_type: FeedbackEventType | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
        observed_to: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[FeedbackEvent]:
        statement = select(FeedbackEventRecord)
        statement = self._filters(
            statement,
            job_id=job_id,
            application_id=application_id,
            event_type=event_type,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
            observed_to=observed_to,
        )
        statement = (
            statement.order_by(
                FeedbackEventRecord.occurred_at.asc(),
                FeedbackEventRecord.observed_at.asc(),
                FeedbackEventRecord.event_id.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return [self._to_domain(row) for row in self.session.scalars(statement).all()]

    def count(
        self,
        *,
        job_id: str | None = None,
        application_id: str | None = None,
        event_type: FeedbackEventType | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
        observed_to: datetime | None = None,
    ) -> int:
        statement = select(func.count()).select_from(FeedbackEventRecord)
        statement = self._filters(
            statement,
            job_id=job_id,
            application_id=application_id,
            event_type=event_type,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
            observed_to=observed_to,
        )
        return int(self.session.scalar(statement) or 0)

    @staticmethod
    def _filters(
        statement,
        *,
        job_id: str | None,
        application_id: str | None,
        event_type: FeedbackEventType | None,
        occurred_from: datetime | None,
        occurred_to: datetime | None,
        observed_to: datetime | None,
    ):
        if job_id:
            statement = statement.where(FeedbackEventRecord.job_id == job_id.strip())
        if application_id:
            statement = statement.where(
                FeedbackEventRecord.application_id == application_id.strip()
            )
        if event_type is not None:
            statement = statement.where(FeedbackEventRecord.event_type == event_type.value)
        if occurred_from is not None:
            statement = statement.where(FeedbackEventRecord.occurred_at >= occurred_from)
        if occurred_to is not None:
            statement = statement.where(FeedbackEventRecord.occurred_at <= occurred_to)
        if observed_to is not None:
            statement = statement.where(FeedbackEventRecord.observed_at <= observed_to)
        return statement

    @staticmethod
    def _to_domain(record: FeedbackEventRecord) -> FeedbackEvent:
        return FeedbackEvent(
            event_id=record.event_id,
            event_type=FeedbackEventType(record.event_type),
            job_id=record.job_id,
            application_id=record.application_id,
            candidate_id=record.candidate_id,
            resume_family_id=record.resume_family_id,
            occurred_at=_as_utc(record.occurred_at),
            observed_at=_as_utc(record.observed_at),
            source=FeedbackEventSource(record.source),
            actor=record.actor,
            idempotency_key=record.idempotency_key,
            schema_version=record.schema_version,
            metadata=dict(record.metadata_json or {}),
            model_name=record.model_name,
            model_version=record.model_version,
            experiment_id=record.experiment_id,
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
