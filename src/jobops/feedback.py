from datetime import UTC, datetime

from jobops.models.feedback import FeedbackEvent, FeedbackEventCreate


class FeedbackEventError(RuntimeError):
    pass


class FeedbackEventConflictError(FeedbackEventError):
    pass


class FeedbackEventRepository:
    def create(
        self,
        event: FeedbackEventCreate,
        *,
        observed_at: datetime,
    ) -> FeedbackEvent:
        raise NotImplementedError

    def get_by_idempotency_key(self, idempotency_key: str) -> FeedbackEvent | None:
        raise NotImplementedError


class FeedbackEventService:
    """Append-only ingestion service for learning feedback and hiring outcomes."""

    def __init__(self, repository: FeedbackEventRepository) -> None:
        self.repository = repository

    def record(
        self,
        event: FeedbackEventCreate,
        *,
        observed_at: datetime | None = None,
    ) -> FeedbackEvent:
        observed = _as_utc(observed_at or datetime.now(UTC))
        occurred = _as_utc(event.occurred_at)
        if occurred > observed:
            raise FeedbackEventError("occurred_at cannot be later than observed_at")

        existing = self.repository.get_by_idempotency_key(event.idempotency_key)
        if existing is not None:
            if self._same_event(existing, event):
                return existing
            raise FeedbackEventConflictError(
                f"idempotency key already belongs to a different event: {event.idempotency_key}"
            )
        return self.repository.create(event, observed_at=observed)

    @staticmethod
    def _same_event(existing: FeedbackEvent, requested: FeedbackEventCreate) -> bool:
        return (
            existing.event_id == requested.event_id
            and existing.event_type is requested.event_type
            and existing.job_id == requested.job_id
            and existing.application_id == requested.application_id
            and existing.candidate_id == requested.candidate_id
            and existing.resume_family_id == requested.resume_family_id
            and _as_utc(existing.occurred_at) == _as_utc(requested.occurred_at)
            and existing.source is requested.source
            and existing.actor == requested.actor
            and existing.idempotency_key == requested.idempotency_key
            and existing.schema_version == requested.schema_version
            and existing.metadata == requested.metadata
            and existing.model_name == requested.model_name
            and existing.model_version == requested.model_version
            and existing.experiment_id == requested.experiment_id
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
