import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from jobops.db.base import Base
from jobops.db.repositories import SqlAlchemyJobRepository
from jobops.discovery.runner import DiscoveryService
from jobops.ingestion.models import SourceJobPosting
from jobops.models.discovery import DiscoveryProviderName, DiscoveryRunRequest
from jobops.models.job import WorkMode
from jobops.models.search_profile import SearchProfile


class FakeProvider:
    provider_name = "jobicy"

    def __init__(self, jobs: list[SourceJobPosting]):
        self.jobs = jobs

    def supports(self, profile: SearchProfile) -> tuple[bool, str | None]:
        return True, None

    async def discover(self, profile, *, limit, client):
        return self.jobs[:limit], 1


def _profile() -> SearchProfile:
    return SearchProfile(
        profile_id="profile-constraints",
        candidate_id="me",
        name="Remote Data",
        role_queries=["Data Engineer"],
        allowed_work_modes=[WorkMode.REMOTE],
        minimum_salary=65000,
    )


async def _unused_client_handler(request):
    raise AssertionError("fake provider should not use HTTP")


@pytest.mark.asyncio
async def test_discovery_reapplies_hard_constraints_after_normalization() -> None:
    eligible = SourceJobPosting(
        source="jobicy",
        source_scope="public-remote",
        source_job_id="eligible",
        company="GoodCo",
        title="Data Engineer",
        location="Remote",
        workplace_type="remote",
        salary_min=90000,
        salary_max=110000,
        salary_currency="USD",
        salary_interval="year",
    )
    below_floor = SourceJobPosting(
        source="jobicy",
        source_scope="public-remote",
        source_job_id="below-floor",
        company="LowCo",
        title="Data Engineer",
        location="Remote",
        workplace_type="remote",
        salary_min=60000,
        salary_max=90000,
        salary_currency="USD",
        salary_interval="year",
    )
    onsite = SourceJobPosting(
        source="jobicy",
        source_scope="public-remote",
        source_job_id="onsite",
        company="OfficeCo",
        title="Data Engineer",
        location="Detroit, MI",
        workplace_type="onsite",
        salary_min=90000,
        salary_max=110000,
        salary_currency="USD",
        salary_interval="year",
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        repo = SqlAlchemyJobRepository(session)
        service = DiscoveryService(
            repo,
            {
                DiscoveryProviderName.JOBICY: FakeProvider(
                    [eligible, below_floor, onsite]
                )
            },
        )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_unused_client_handler)
        ) as client:
            result = await service.run(
                _profile(),
                DiscoveryRunRequest(
                    providers=[DiscoveryProviderName.JOBICY],
                    limit_per_provider=20,
                ),
                client=client,
            )
        session.commit()

        assert result.fetched == 3
        assert result.normalized == 3
        assert result.eligible == 1
        assert result.rejected == 2
        assert result.persisted == 1
        assert result.rejection_summary == {
            "salary_floor": 1,
            "work_mode": 1,
        }
        stored = repo.list()
        assert len(stored) == 1
        assert stored[0].company == "GoodCo"

        diagnostic = result.provider_results[0]
        assert diagnostic.eligible == 1
        assert diagnostic.rejected == 2
        assert diagnostic.rejection_summary == {
            "salary_floor": 1,
            "work_mode": 1,
        }
