from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from jobops.api.dependencies import get_session
from jobops.db.onboarding_repository import SqlAlchemyCandidateOnboardingRepository
from jobops.models.onboarding import (
    CandidateOnboarding,
    CandidateOnboardingPayload,
    CandidateOnboardingStatus,
    ResumeAsset,
)

router = APIRouter(prefix="/v1/candidates", tags=["candidate-onboarding"])


@router.put("/{candidate_id}/onboarding", response_model=CandidateOnboarding)
def upsert_candidate_onboarding(
    candidate_id: str,
    payload: CandidateOnboardingPayload,
    session: Annotated[Session, Depends(get_session)],
) -> CandidateOnboarding:
    if payload.candidate.candidate_id != candidate_id:
        raise HTTPException(
            status_code=422,
            detail="candidate id does not match onboarding payload owner",
        )

    saved = SqlAlchemyCandidateOnboardingRepository(session).save(payload)
    session.commit()
    return saved


@router.get("/{candidate_id}/onboarding", response_model=CandidateOnboarding)
def get_candidate_onboarding(
    candidate_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> CandidateOnboarding:
    onboarding = SqlAlchemyCandidateOnboardingRepository(session).get(candidate_id)
    if onboarding is None:
        raise HTTPException(status_code=404, detail="candidate onboarding not found")
    return onboarding


@router.get(
    "/{candidate_id}/onboarding/status",
    response_model=CandidateOnboardingStatus,
)
def get_candidate_onboarding_status(
    candidate_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> CandidateOnboardingStatus:
    return SqlAlchemyCandidateOnboardingRepository(session).status(candidate_id)


@router.get(
    "/{candidate_id}/onboarding/resume-assets/{family_id}",
    response_model=ResumeAsset,
)
def get_candidate_resume_asset(
    candidate_id: str,
    family_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ResumeAsset:
    onboarding = SqlAlchemyCandidateOnboardingRepository(session).get(candidate_id)
    if onboarding is None:
        raise HTTPException(status_code=404, detail="candidate onboarding not found")
    asset = onboarding.resume_asset(family_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="resume asset not found")
    return asset


@router.delete(
    "/{candidate_id}/onboarding",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_candidate_onboarding(
    candidate_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    if not SqlAlchemyCandidateOnboardingRepository(session).delete(candidate_id):
        raise HTTPException(status_code=404, detail="candidate onboarding not found")
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
