from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from jobops.api.dependencies import get_session
from jobops.db import SqlAlchemyJobRepository, SqlAlchemySubmissionRepository
from jobops.models.submission import (
    PreparedSubmissionState,
    SubmissionAttempt,
    SubmissionReadinessResult,
    SubmitAuthorization,
    SubmitAuthorizationCreate,
    SubmitAuthorizationRevoke,
)
from jobops.submissions import (
    DuplicateSubmissionError,
    SubmissionAuthorizationInvalidError,
    SubmissionAuthorizationNotFoundError,
    SubmissionGate,
    SubmissionNotReadyError,
)

router = APIRouter(prefix="/v1/submissions", tags=["submissions"])


@router.post("/readiness", response_model=SubmissionReadinessResult)
def evaluate_submission_readiness(
    request: PreparedSubmissionState,
) -> SubmissionReadinessResult:
    return SubmissionGate(_ReadOnlySubmissionRepository()).evaluate(request)


@router.post(
    "/authorizations",
    response_model=SubmitAuthorization,
    status_code=status.HTTP_201_CREATED,
)
def create_submit_authorization(
    request: SubmitAuthorizationCreate,
    session: Annotated[Session, Depends(get_session)],
) -> SubmitAuthorization:
    if SqlAlchemyJobRepository(session).get(request.state.job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")

    gate = SubmissionGate(SqlAlchemySubmissionRepository(session))
    try:
        authorization = gate.authorize(request)
    except SubmissionNotReadyError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "blockers": [blocker.value for blocker in exc.readiness.blockers],
            },
        ) from exc
    except DuplicateSubmissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return authorization


@router.get("/authorizations/{authorization_id}", response_model=SubmitAuthorization)
def get_submit_authorization(
    authorization_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> SubmitAuthorization:
    item = SqlAlchemySubmissionRepository(session).get_authorization(authorization_id)
    if item is None:
        raise HTTPException(status_code=404, detail="submit authorization not found")
    return item


@router.post(
    "/authorizations/{authorization_id}/revoke",
    response_model=SubmitAuthorization,
)
def revoke_submit_authorization(
    authorization_id: str,
    request: SubmitAuthorizationRevoke,
    session: Annotated[Session, Depends(get_session)],
) -> SubmitAuthorization:
    gate = SubmissionGate(SqlAlchemySubmissionRepository(session))
    try:
        item = gate.revoke(authorization_id, request)
    except SubmissionAuthorizationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SubmissionAuthorizationInvalidError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return item


@router.get("/attempts/{attempt_id}", response_model=SubmissionAttempt)
def get_submission_attempt(
    attempt_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> SubmissionAttempt:
    item = SqlAlchemySubmissionRepository(session).get_attempt(attempt_id)
    if item is None:
        raise HTTPException(status_code=404, detail="submission attempt not found")
    return item


class _ReadOnlySubmissionRepository:
    """Readiness evaluation cannot create or consume submission authority."""

    def create_authorization(self, item):
        raise RuntimeError("readiness evaluation cannot create authorization")

    def get_authorization(self, authorization_id):
        return None

    def claim_authorization(self, authorization_id, *, attempt_id, consumed_at):
        return None

    def revoke_authorization(
        self,
        authorization_id,
        *,
        revoked_at,
        revoked_by,
        revoke_note,
    ):
        return None

    def get_successful_attempt(self, application_id):
        return None

    def create_attempt(self, attempt):
        raise RuntimeError("readiness evaluation cannot create attempt")

    def finalize_attempt(self, attempt_id, *, outcome, completed_at):
        return None
