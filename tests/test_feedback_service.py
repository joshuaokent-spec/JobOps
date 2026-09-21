from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from jobops.feedback import (
    FeedbackEventConflictError,
    FeedbackEventError,
    FeedbackEventService,
)
from jobops.models.feedback import (
    FeedbackEvent,
    FeedbackEventCreate,
    FeedbackEventSource,
    FeedbackEventType,
)

_NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


class MemoryFeedbackRepository:
    def __init__(self) -> None:
        self.by_idempotency: dict[str, FeedbackEvent] = {}

    def create(
        self,
        event: FeedbackEventCreate,
        *,
        observed_at: datetime,
    ) -> FeedbackEvent:
        existing = self.by_idempotency.get(event.idempotency_key)
        if existing is not None:
            return existing
        created = FeedbackEvent(
            **event.model_dump(),
            observed_at=observed_at,
        )
        self.by_idempotency[event.idempotency_key] = created
        return created

    def get_by_idempotency_key(self, idempotency_key: str) -> FeedbackEvent | None:
        return self.by_idempotency.get(idempotency_key)


def _event(**updates: object) -> FeedbackEventCreate:
    payload = {
        "event_type": FeedbackEventType.JOB_SAVED,
        "job_id": "job-1",
        "candidate_id": "candidate-1",
        "occurred_at": _NOW - timedelta(minutes=5),
        "source": FeedbackEventSource.USER,
        "actor": "candidate",
        "idempotency_key": "save-job-1",
        "metadata": {"surface": "ranking"},
    }
    payload.update(updates)
    return FeedbackEventCreate.model_validate(payload)


def test_semantic_idempotency_ignores_regenerated_event_id() -> None:
    repository = MemoryFeedbackRepository()
    service = FeedbackEventService(repository)

    first = service.record(_event(event_id="event-1"), observed_at=_NOW)
    replay = service.record(_event(event_id="event-2"), observed_at=_NOW + timedelta(seconds=2))

    assert replay.event_id == first.event_id
    assert len(repository.by_idempotency) == 1


def test_idempotency_key_conflict_is_rejected() -> None:
    service = FeedbackEventService(MemoryFeedbackRepository())
    service.record(_event(event_id="event-1"), observed_at=_NOW)

    with pytest.raises(FeedbackEventConflictError, match="different event"):
        service.record(
            _event(
                event_id="event-2",
                event_type=FeedbackEventType.JOB_SKIPPED,
            ),
            observed_at=_NOW + timedelta(seconds=1),
        )


def test_future_event_time_is_rejected() -> None:
    service = FeedbackEventService(MemoryFeedbackRepository())

    with pytest.raises(FeedbackEventError, match="later than observed_at"):
        service.record(
            _event(occurred_at=_NOW + timedelta(minutes=1)),
            observed_at=_NOW,
        )


@pytest.mark.parametrize(
    "metadata",
    [
        {"candidate_answer": "private"},
        {"recruiter_message": "private"},
        {"session_token": "secret"},
        {"phone_number": "5175550000"},
        {"work_authorization": "yes"},
    ],
)
def test_sensitive_metadata_keys_are_rejected(metadata: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="metadata key is not allowed"):
        _event(metadata=metadata)


def test_model_version_requires_model_name() -> None:
    with pytest.raises(ValidationError, match="model_version requires model_name"):
        _event(model_version="v1")
