import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from jobops.db.base import Base
from jobops.db.repositories import SqlAlchemyJobRepository
from jobops.discovery.base import DiscoveryError
from jobops.discovery.runner import DiscoveryService
from jobops.ingestion.models import SourceJobPosting
from jobops.models.discovery import DiscoveryProviderName, DiscoveryRunRequest
from jobops.models.job import WorkMode
from jobops.models.search_profile import SearchProfile
from jobops.normalization.job_normalizer import JobNormalizer


class FakeProvider:
    provider_name = "jobicy"

    def __init__(self, jobs: list[SourceJobPosting]):
        self.jobs = jobs

    def supports(self, profile: SearchProfile) -> tuple[bool, str | None]:
        return True, None

    async def discover(self, profile, *, limit, client):
        return self.jobs[:limit], 1


class FailingProvider:
    provider_name = "adzuna"

    def supports(self, profile: SearchProfile) -> tuple[bool, str | None]:
        return True, None

    async def discover(self, profile, *, limit, client):
        raise DiscoveryError("synthetic provider failure containing private details")


def _profile() -> SearchProfile:
    return SearchProfile(
        profile_id="profile-1",
        candidate_id="me",
        name="Remote Data",
        role_queries=["Data Engineer"],
        allowed_work_modes=[WorkMode.REMOTE],
        minimum_salary=65000,
    )


async def _unused_client_handler(request):
    raise AssertionError("fake providers should not use HTTP")


@pytest.mark.asyncio
async def test_discovery_fanout_prefers_existing_canonical_job_and_survives_provider_failure() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    normalizer = JobNormalizer()

    direct = normalizer.normalize(
        SourceJobPosting(
            source="greenhouse",
            source_scope="direct",
            source_job_id="direct-1",
            company="SameCo",
            title="Data Engineer",
            location="Remote",
            workplace_type="remote",
            salary_min=90000,
            salary_max=120000,
            salary_currency="USD",
            salary_interval="year",
        )
    )
    duplicate = SourceJobPosting(
        source="jobicy",
        source_scope="public-remote",
        source_job_id="agg-duplicate",
        company="SameCo",
        title="Data Engineer",
        location="Remote",
        workplace_type="remote",
        salary_min=90000,
        salary_max=120000,
        salary_currency="USD",
        salary_interval="year",
    )
    unique = SourceJobPosting(
        source="jobicy",
        source_scope="public-remote",
        source_job_id="agg-unique",
        company="NewCo",
        title="Senior Data Engineer",
        location="Remote",
        workplace_type="remote",
        salary_min=100000,
        salary_max=130000,
        salary_currency="USD",
        salary_interval="year",
    )

    with Session(engine) as session:
        repo = SqlAlchemyJobRepository(session)
        repo.save(direct)
        session.commit()

        service = DiscoveryService(
            repo,
            {
                DiscoveryProviderName.JOBICY: FakeProvider([duplicate, unique]),
                DiscoveryProviderName.ADZUNA: FailingProvider(),
            },
        )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_unused_client_handler)
        ) as client:
            result = await service.run(
                _profile(),
                DiscoveryRunRequest(limit_per_provider=20),
                client=client,
            )
        session.commit()

        assert result.providers_succeeded == 1
        assert result.providers_failed == 1
        assert result.persisted == 1
        assert result.duplicates == 1
        assert len(result.persisted_job_ids) == 1
        canonical = repo.get_by_dedupe_key(direct.dedupe_key)
        assert canonical is not None
        assert canonical.source == "greenhouse"

        failed = next(
            item
            for item in result.provider_results
            if item.provider is DiscoveryProviderName.ADZUNA
        )
        assert failed.error == "DiscoveryError: provider discovery failed"
