import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from jobops.db.base import Base
from jobops.db.repositories import SqlAlchemyJobRepository
from jobops.ingestion.models import SourceJobPosting
from jobops.ingestion.runner import IngestionRunner
from jobops.models.query import JobSearchFilters


class FakeAdapter:
    source_name = "lever"
    source_scope = "acme"
    company = "Acme"

    def __init__(self, jobs=None, error=None):
        self.jobs = jobs or []
        self.error = error

    async def fetch(self, client=None):
        if self.error:
            raise self.error
        return self.jobs


def source_job(job_id: str, title: str) -> SourceJobPosting:
    return SourceJobPosting(
        source="lever",
        source_scope="acme",
        source_job_id=job_id,
        company="Acme",
        title=title,
    )


@pytest.mark.asyncio
async def test_refresh_is_idempotent_and_deactivates_stale_jobs() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    runner = IngestionRunner(factory)

    first = await runner.run(
        [FakeAdapter([source_job("1", "Data Engineer"), source_job("2", "Analyst")])]
    )
    assert first.upserted == 2

    second = await runner.run([FakeAdapter([source_job("1", "Data Engineer")])])
    assert second.upserted == 1
    assert second.deactivated == 1

    with factory() as session:
        repo = SqlAlchemyJobRepository(session)
        assert repo.count(JobSearchFilters(active=True)) == 1
        assert repo.count(JobSearchFilters(active=False)) == 1


@pytest.mark.asyncio
async def test_failed_fetch_does_not_deactivate_existing_jobs() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    runner = IngestionRunner(factory)

    await runner.run([FakeAdapter([source_job("1", "Data Engineer")])])
    result = await runner.run([FakeAdapter(error=RuntimeError("network"))])

    assert result.sources_failed == 1
    with factory() as session:
        assert SqlAlchemyJobRepository(session).count(JobSearchFilters(active=True)) == 1
