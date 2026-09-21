from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from jobops.db import Base, SqlAlchemyFeedbackRepository, SqlAlchemyJobRepository
from jobops.models.feedback import FeedbackEventCreate, FeedbackEventSource, FeedbackEventType
from jobops.models.job import JobPosting

_BASE = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def _event(
    event_id: str,
    event_type: FeedbackEventType,
    *,
    occurred_at: datetime,
    idempotency_key: str,
    application_id: str | None = "app-1",
) -> FeedbackEventCreate:
    return FeedbackEventCreate(
        event_id=event_id,
        event_type=event_type,
        job_id="job-1",
        application_id=application_id,
        candidate_id="candidate-1",
        resume_family_id="data-engineering",
        occurred_at=occurred_at,
        source=FeedbackEventSource.SYSTEM,
        actor="jobops",
        idempotency_key=idempotency_key,
        metadata={"surface": "test"},
        model_name="ranking-baseline",
        model_version="v0",
        experiment_id="exp-1",
    )


def test_feedback_repository_orders_and_filters_temporal_history() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        SqlAlchemyJobRepository(session).save(
            JobPosting(job_id="job-1", company="Synthetic Co", title="Data Engineer")
        )
        repository = SqlAlchemyFeedbackRepository(session)

        late_observed = repository.create(
            _event(
                "event-2",
                FeedbackEventType.RECRUITER_RESPONSE,
                occurred_at=_BASE + timedelta(hours=2),
                idempotency_key="response-1",
            ),
            observed_at=_BASE + timedelta(hours=3),
        )
        early = repository.create(
            _event(
                "event-1",
                FeedbackEventType.APPLICATION_SUBMITTED,
                occurred_at=_BASE,
                idempotency_key="submitted-1",
            ),
            observed_at=_BASE + timedelta(minutes=1),
        )
        session.commit()

        events = list(repository.list(job_id="job-1"))
        assert [item.event_id for item in events] == ["event-1", "event-2"]
        assert events[0].occurred_at == early.occurred_at
        assert events[1].observed_at == late_observed.observed_at

        cutoff = list(
            repository.list(
                job_id="job-1",
                observed_to=_BASE + timedelta(hours=1),
            )
        )
        assert [item.event_id for item in cutoff] == ["event-1"]

        responses = list(
            repository.list(
                application_id="app-1",
                event_type=FeedbackEventType.RECRUITER_RESPONSE,
            )
        )
        assert [item.event_id for item in responses] == ["event-2"]
        assert repository.count(event_type=FeedbackEventType.RECRUITER_RESPONSE) == 1


def test_feedback_repository_idempotency_key_is_unique() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        SqlAlchemyJobRepository(session).save(
            JobPosting(job_id="job-1", company="Synthetic Co", title="Data Engineer")
        )
        repository = SqlAlchemyFeedbackRepository(session)
        first = repository.create(
            _event(
                "event-1",
                FeedbackEventType.JOB_SAVED,
                occurred_at=_BASE,
                idempotency_key="same-key",
            ),
            observed_at=_BASE + timedelta(seconds=1),
        )
        second = repository.create(
            _event(
                "event-2",
                FeedbackEventType.JOB_SAVED,
                occurred_at=_BASE,
                idempotency_key="same-key",
            ),
            observed_at=_BASE + timedelta(seconds=2),
        )

        assert first.event_id == "event-1"
        assert second.event_id == "event-1"
        assert repository.count() == 1
