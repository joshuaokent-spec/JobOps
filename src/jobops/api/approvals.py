from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from jobops.api.dependencies import get_session
from jobops.approvals import (
    ApprovalDecisionError,
    ApprovalNotFoundError,
    ApprovalQueue,
    InvalidApprovalTransitionError,
)
from jobops.db import SqlAlchemyApprovalRepository, SqlAlchemyJobRepository
from jobops.models.approval import (
    ApprovalCreate,
    ApprovalDecision,
    ApprovalItem,
    ApprovalPage,
    ApprovalStatus,
)

router = APIRouter(prefix="/v1/approvals", tags=["approvals"])


@router.post("", response_model=ApprovalItem, status_code=status.HTTP_201_CREATED)
def create_approval(
    request: ApprovalCreate,
    session: Annotated[Session, Depends(get_session)],
) -> ApprovalItem:
    if SqlAlchemyJobRepository(session).get(request.job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")

    queue = ApprovalQueue(SqlAlchemyApprovalRepository(session))
    item = queue.enqueue(request)
    session.commit()
    return item


@router.get("", response_model=ApprovalPage)
def list_approvals(
    session: Annotated[Session, Depends(get_session)],
    approval_status: Annotated[ApprovalStatus | None, Query(alias="status")] = None,
    job_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ApprovalPage:
    repo = SqlAlchemyApprovalRepository(session)
    return ApprovalPage(
        total=repo.count(status=approval_status, job_id=job_id),
        limit=limit,
        offset=offset,
        items=list(
            repo.list(
                status=approval_status,
                job_id=job_id,
                limit=limit,
                offset=offset,
            )
        ),
    )


@router.get("/{approval_id}", response_model=ApprovalItem)
def get_approval(
    approval_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApprovalItem:
    item = SqlAlchemyApprovalRepository(session).get(approval_id)
    if item is None:
        raise HTTPException(status_code=404, detail="approval item not found")
    return item


@router.post("/{approval_id}/decision", response_model=ApprovalItem)
def decide_approval(
    approval_id: str,
    request: ApprovalDecision,
    session: Annotated[Session, Depends(get_session)],
) -> ApprovalItem:
    queue = ApprovalQueue(SqlAlchemyApprovalRepository(session))
    try:
        item = queue.decide(approval_id, request)
    except ApprovalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidApprovalTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ApprovalDecisionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return item
