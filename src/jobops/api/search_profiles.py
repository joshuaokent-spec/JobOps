from collections import Counter
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from jobops.api.dependencies import get_session
from jobops.config import get_settings
from jobops.db import (
    SqlAlchemyApprovalRepository,
    SqlAlchemyFlagshipReadinessRepository,
    SqlAlchemyJobRepository,
)
from jobops.db.onboarding_repository import SqlAlchemyCandidateOnboardingRepository
from jobops.db.search_profile_repository import SqlAlchemySearchProfileRepository
from jobops.discovery.base import DiscoveryProvider
from jobops.discovery.factory import build_discovery_providers
from jobops.discovery.runner import DiscoveryService
from jobops.flagship import FlagshipReadinessService, FlagshipRunError, FlagshipRunService
from jobops.flagship.tracking import FlagshipTrackingService
from jobops.matching import BaselineJobScorer
from jobops.matching.hard_constraints import HardConstraintMatcher
from jobops.models.discovery import (
    DiscoveryProviderName,
    DiscoveryRunRequest,
    DiscoveryRunResult,
)
from jobops.models.flagship_readiness import FlagshipExceptionInbox, FlagshipReadinessSummary
from jobops.models.flagship_run import FlagshipRunRequest, FlagshipRunResult
from jobops.models.flagship_tracking import FlagshipTrackingSummary
from jobops.models.query import JobSearchFilters
from jobops.models.search_profile import (
    SearchProfile,
    SearchProfileCreate,
    SearchProfilePage,
    SearchProfilePreview,
    SearchProfilePreviewRequest,
    SearchProfileRankedJob,
    SearchProfileRejectedJob,
    SearchProfileRunFilters,
    SearchProfileUpdate,
)

router = APIRouter(prefix="/v1/search-profiles", tags=["search-profiles"])


def get_discovery_providers() -> dict[DiscoveryProviderName, DiscoveryProvider]:
    return build_discovery_providers(get_settings())


def _apply_run_filters(
    profile: SearchProfile,
    filters: SearchProfileRunFilters | None,
) -> SearchProfile:
    if filters is None:
        return profile

    data = profile.model_dump(exclude={"created_at", "updated_at"})
    if filters.role_queries is not None:
        data["role_queries"] = filters.role_queries
    if filters.allowed_work_modes is not None:
        data["allowed_work_modes"] = filters.allowed_work_modes
    if filters.hybrid_location_hubs is not None:
        data["hybrid_location_hubs"] = filters.hybrid_location_hubs
    if filters.clear_minimum_salary:
        data["minimum_salary"] = None
    elif filters.minimum_salary is not None:
        data["minimum_salary"] = filters.minimum_salary
    if filters.clear_minimum_fit_score:
        data["minimum_fit_score"] = None
    elif filters.minimum_fit_score is not None:
        data["minimum_fit_score"] = filters.minimum_fit_score

    return SearchProfile(
        **data,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


async def _execute_flagship_run(
    *,
    profile: SearchProfile,
    request: FlagshipRunRequest,
    session: Session,
    providers: dict[DiscoveryProviderName, DiscoveryProvider],
) -> FlagshipRunResult:
    settings = get_settings()
    job_repository = SqlAlchemyJobRepository(session)
    discovery = DiscoveryService(
        job_repository,
        providers,
        timeout_seconds=settings.discovery_timeout_seconds,
    )
    service = FlagshipRunService(job_repository, discovery)

    try:
        result = await service.run(profile, request)
    except FlagshipRunError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    SqlAlchemyFlagshipReadinessRepository(session).save(
        candidate_id=profile.candidate_id,
        result=result,
    )
    session.commit()
    return result


@router.post("", response_model=SearchProfile, status_code=status.HTTP_201_CREATED)
def create_search_profile(
    request: SearchProfileCreate,
    session: Annotated[Session, Depends(get_session)],
) -> SearchProfile:
    profile = SearchProfile(
        profile_id=str(uuid4()),
        **request.model_dump(),
    )
    saved = SqlAlchemySearchProfileRepository(session).save(profile)
    session.commit()
    return saved


@router.get("", response_model=SearchProfilePage)
def list_search_profiles(
    session: Annotated[Session, Depends(get_session)],
    candidate_id: str | None = None,
    active: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SearchProfilePage:
    repo = SqlAlchemySearchProfileRepository(session)
    return SearchProfilePage(
        total=repo.count(candidate_id=candidate_id, active=active),
        limit=limit,
        offset=offset,
        items=list(
            repo.list(
                candidate_id=candidate_id,
                active=active,
                limit=limit,
                offset=offset,
            )
        ),
    )


@router.get("/{profile_id}", response_model=SearchProfile)
def get_search_profile(
    profile_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> SearchProfile:
    profile = SqlAlchemySearchProfileRepository(session).get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="search profile not found")
    return profile


@router.patch("/{profile_id}", response_model=SearchProfile)
def update_search_profile(
    profile_id: str,
    request: SearchProfileUpdate,
    session: Annotated[Session, Depends(get_session)],
) -> SearchProfile:
    repo = SqlAlchemySearchProfileRepository(session)
    existing = repo.get(profile_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="search profile not found")

    data = existing.model_dump(exclude={"created_at", "updated_at"})
    updates = request.model_dump(
        exclude_unset=True,
        exclude={"clear_minimum_salary", "clear_minimum_fit_score"},
    )
    data.update(updates)
    if request.clear_minimum_salary:
        data["minimum_salary"] = None
    if request.clear_minimum_fit_score:
        data["minimum_fit_score"] = None

    updated = SearchProfile(
        **data,
        created_at=existing.created_at,
    )
    saved = repo.save(updated)
    session.commit()
    return saved


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_search_profile(
    profile_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    deleted = SqlAlchemySearchProfileRepository(session).delete(profile_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="search profile not found")
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{profile_id}/preview", response_model=SearchProfilePreview)
def preview_search_profile(
    profile_id: str,
    request: SearchProfilePreviewRequest,
    session: Annotated[Session, Depends(get_session)],
) -> SearchProfilePreview:
    profile = SqlAlchemySearchProfileRepository(session).get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="search profile not found")
    if request.candidate.candidate_id != profile.candidate_id:
        raise HTTPException(
            status_code=422,
            detail="candidate does not match search profile owner",
        )

    jobs = list(
        SqlAlchemyJobRepository(session).search(
            JobSearchFilters(active=True),
            limit=request.candidate_pool,
            offset=0,
        )
    )
    matcher = HardConstraintMatcher()
    scorer = BaselineJobScorer()
    ranked: list[SearchProfileRankedJob] = []
    rejected: list[SearchProfileRejectedJob] = []
    rejection_counts: Counter[str] = Counter()

    for job in jobs:
        result = matcher.evaluate(profile, job)
        if not result.eligible:
            rejection_counts.update(set(result.violation_codes))
            if len(rejected) < 25:
                rejected.append(
                    SearchProfileRejectedJob(
                        job_id=job.job_id,
                        company=job.company,
                        title=job.title,
                        reasons=result.reasons,
                    )
                )
            continue

        score = scorer.score(request.candidate, job)
        if (
            profile.minimum_fit_score is not None
            and score.overall < profile.minimum_fit_score
        ):
            rejection_counts["fit_score"] += 1
            if len(rejected) < 25:
                rejected.append(
                    SearchProfileRejectedJob(
                        job_id=job.job_id,
                        company=job.company,
                        title=job.title,
                        reasons=[
                            f"Fit score {score.overall} is below required threshold "
                            f"{profile.minimum_fit_score}."
                        ],
                    )
                )
            continue
        ranked.append(SearchProfileRankedJob(job=job, score=score))

    ranked.sort(key=lambda item: (-item.score.overall, item.job.job_id))
    total_eligible = len(ranked)
    total_rejected = len(jobs) - total_eligible
    return SearchProfilePreview(
        profile_id=profile.profile_id,
        total_examined=len(jobs),
        total_eligible=total_eligible,
        total_rejected=total_rejected,
        ranked=ranked[: request.limit],
        rejected_sample=rejected,
        rejection_summary=dict(sorted(rejection_counts.items())),
    )


@router.post("/{profile_id}/discover", response_model=DiscoveryRunResult)
async def discover_for_search_profile(
    profile_id: str,
    request: DiscoveryRunRequest,
    session: Annotated[Session, Depends(get_session)],
    providers: Annotated[
        dict[DiscoveryProviderName, DiscoveryProvider],
        Depends(get_discovery_providers),
    ],
) -> DiscoveryRunResult:
    profile = SqlAlchemySearchProfileRepository(session).get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="search profile not found")
    if not profile.active:
        raise HTTPException(status_code=409, detail="search profile is inactive")

    settings = get_settings()
    service = DiscoveryService(
        SqlAlchemyJobRepository(session),
        providers,
        timeout_seconds=settings.discovery_timeout_seconds,
    )
    result = await service.run(profile, request)
    session.commit()
    return result


@router.get("/{profile_id}/readiness", response_model=FlagshipReadinessSummary)
def get_flagship_readiness(
    profile_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> FlagshipReadinessSummary:
    profile = SqlAlchemySearchProfileRepository(session).get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="search profile not found")

    service = FlagshipReadinessService(
        SqlAlchemyFlagshipReadinessRepository(session),
        SqlAlchemyApprovalRepository(session),
    )
    summary = service.latest(profile_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="no flagship run snapshot found")
    return summary


@router.get("/{profile_id}/exceptions", response_model=FlagshipExceptionInbox)
def get_flagship_exceptions(
    profile_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> FlagshipExceptionInbox:
    profile = SqlAlchemySearchProfileRepository(session).get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="search profile not found")

    service = FlagshipReadinessService(
        SqlAlchemyFlagshipReadinessRepository(session),
        SqlAlchemyApprovalRepository(session),
    )
    inbox = service.exceptions(profile_id)
    if inbox is None:
        raise HTTPException(status_code=404, detail="no flagship run snapshot found")
    return inbox


@router.get("/{profile_id}/tracking", response_model=FlagshipTrackingSummary)
def get_flagship_tracking(
    profile_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> FlagshipTrackingSummary:
    profile = SqlAlchemySearchProfileRepository(session).get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="search profile not found")

    summary = FlagshipTrackingService(
        SqlAlchemyFlagshipReadinessRepository(session)
    ).latest(profile_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="no flagship run snapshot found")
    return summary


@router.post("/{profile_id}/run", response_model=FlagshipRunResult)
async def run_flagship_for_search_profile(
    profile_id: str,
    request: FlagshipRunRequest,
    session: Annotated[Session, Depends(get_session)],
    providers: Annotated[
        dict[DiscoveryProviderName, DiscoveryProvider],
        Depends(get_discovery_providers),
    ],
) -> FlagshipRunResult:
    profile = SqlAlchemySearchProfileRepository(session).get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="search profile not found")
    if not profile.active:
        raise HTTPException(status_code=409, detail="search profile is inactive")

    return await _execute_flagship_run(
        profile=profile,
        request=request,
        session=session,
        providers=providers,
    )


@router.post("/{profile_id}/run-onboarded", response_model=FlagshipRunResult)
async def run_onboarded_flagship_for_search_profile(
    profile_id: str,
    session: Annotated[Session, Depends(get_session)],
    providers: Annotated[
        dict[DiscoveryProviderName, DiscoveryProvider],
        Depends(get_discovery_providers),
    ],
    filters: SearchProfileRunFilters | None = None,
) -> FlagshipRunResult:
    profile = SqlAlchemySearchProfileRepository(session).get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="search profile not found")
    if not profile.active:
        raise HTTPException(status_code=409, detail="search profile is inactive")

    onboarding_repository = SqlAlchemyCandidateOnboardingRepository(session)
    onboarding = onboarding_repository.get(profile.candidate_id)
    if onboarding is None:
        raise HTTPException(status_code=409, detail="candidate onboarding is missing")

    readiness = onboarding_repository.status(profile.candidate_id)
    if not readiness.ready_to_run:
        raise HTTPException(status_code=409, detail="candidate onboarding is not ready")

    run_profile = _apply_run_filters(profile, filters)
    return await _execute_flagship_run(
        profile=run_profile,
        request=onboarding.build_run_request(),
        session=session,
        providers=providers,
    )
