from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, sessionmaker

from jobops.config import get_settings
from jobops.db import SqlAlchemyJobRepository, build_engine, build_session_factory
from jobops.matching import BaselineJobScorer
from jobops.models.job import WorkMode
from jobops.models.query import (
    JobPage,
    JobSearchFilters,
    RankedJob,
    RankedJobPage,
    RankJobsRequest,
)

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    engine = build_engine(get_settings().database_url)
    return build_session_factory(engine)


def get_session() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@router.get("", response_model=JobPage)
def list_jobs(
    session: Annotated[Session, Depends(get_session)],
    title: str | None = None,
    company: str | None = None,
    location: str | None = None,
    work_mode: WorkMode | None = None,
    min_salary: Annotated[int | None, Query(ge=0)] = None,
    source: str | None = None,
    active: bool | None = True,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JobPage:
    filters = JobSearchFilters(
        title=title,
        company=company,
        location=location,
        work_mode=work_mode,
        min_salary=min_salary,
        source=source,
        active=active,
    )
    repo = SqlAlchemyJobRepository(session)
    return JobPage(
        total=repo.count(filters),
        limit=limit,
        offset=offset,
        items=list(repo.search(filters, limit=limit, offset=offset)),
    )


@router.post("/rank", response_model=RankedJobPage)
def rank_jobs(
    request: RankJobsRequest,
    session: Annotated[Session, Depends(get_session)],
) -> RankedJobPage:
    repo = SqlAlchemyJobRepository(session)
    total_available = repo.count(request.filters)
    jobs = list(repo.search(request.filters, limit=request.candidate_pool, offset=0))
    scorer = BaselineJobScorer()
    ranked = [
        RankedJob(job=job, score=scorer.score(request.candidate, job))
        for job in jobs
    ]
    ranked.sort(key=lambda item: (-item.score.overall, item.job.job_id))
    page = ranked[request.offset : request.offset + request.limit]
    return RankedJobPage(
        total_available=total_available,
        total_considered=len(ranked),
        limit=request.limit,
        offset=request.offset,
        items=page,
    )
