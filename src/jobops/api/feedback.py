from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from jobops.api.dependencies import get_session
from jobops.db import SqlAlchemyFeedbackRepository, SqlAlchemyJobRepository
from jobops.feedback import (
    FeedbackEventConflictError,
    FeedbackEventError,
    FeedbackEventService,
)
from jobops.models.feedback import (
    FeedbackEvent,
    FeedbackEventCreate,
    FeedbackEventPage,
    FeedbackEventType,
)

router = APIRouter(prefix="/v1/feedback/events", tags=["feedback"])


@router.post("", response_model=FeedbackEvent, status_code=status.HTTP_201_CREATED)
def create_feedback_event(
    request: FeedbackEventCreate,
    session: Annotated[Session, Depends(get_session)],
) -> FeedbackEvent:
    if SqlAlchemyJobRepository(session).get(request.job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")

    service = FeedbackEventService(SqlAlchemyFeedbackRepository(session))
    try:
        event = service.record(request)
    except FeedbackEventConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FeedbackEventError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return event


@router.get("", response_model=FeedbackEventPage)
def list_feedback_events(
    session: Annotated[Session, Depends(get_session)],
    job_id: str | None = None,
    application_id: str | None = None,
    event_type: FeedbackEventType | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    observed_to: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FeedbackEventPage:
    repository = SqlAlchemyFeedbackRepository(session)
    filters = dict(
        job_id=job_id,
        application_id=application_id,
        event_type=event_type,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        observed_to=observed_to,
    )
    return FeedbackEventPage(
        total=repository.count(**filters),
        limit=limit,
        offset=offset,
        items=list(repository.list(**filters, limit=limit, offset=offset)),
    )


@router.get("/{event_id}", response_model=FeedbackEvent)
def get_feedback_event(
    event_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> FeedbackEvent:
    event = SqlAlchemyFeedbackRepository(session).get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="feedback event not found")
    return event
