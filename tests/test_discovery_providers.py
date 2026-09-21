import httpx
import pytest

from jobops.discovery.adzuna import AdzunaDiscoveryProvider
from jobops.discovery.jobicy import JobicyDiscoveryProvider
from jobops.models.job import WorkMode
from jobops.models.search_profile import SearchProfile


def _profile(**overrides) -> SearchProfile:
    values = {
        "profile_id": "profile-1",
        "candidate_id": "me",
        "name": "Remote Data Engineering",
        "role_queries": ["Data Engineer"],
        "allowed_work_modes": [WorkMode.REMOTE],
        "locations": ["United States"],
        "minimum_salary": 65000,
    }
    values.update(overrides)
    return SearchProfile(**values)


@pytest.mark.asyncio
async def test_jobicy_discovers_structured_remote_jobs() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["tag"] == "Data Engineer"
        assert request.url.params["geo"] == "usa"
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": 123,
                        "url": "https://jobicy.com/jobs/data-engineer",
                        "jobTitle": "Senior Data Engineer",
                        "companyName": "Example Remote",
                        "jobIndustry": ["Data Science"],
                        "jobType": ["full-time"],
                        "jobGeo": "USA",
                        "jobLevel": "Senior",
                        "jobDescription": "<p>Build Python data pipelines.</p>",
                        "pubDate": "2026-09-20T12:00:00+00:00",
                        "salaryMin": 90000,
                        "salaryMax": 120000,
                        "salaryCurrency": "USD",
                        "salaryPeriod": "yearly",
                    }
                ]
            },
        )

    provider = JobicyDiscoveryProvider()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        jobs, queries = await provider.discover(_profile(), limit=20, client=client)

    assert queries == 1
    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "jobicy"
    assert job.company == "Example Remote"
    assert job.workplace_type == "remote"
    assert job.salary_min == 90000
    assert job.salary_interval == "yearly"
    assert job.source_url == "https://jobicy.com/jobs/data-engineer"
    assert job.apply_url is None


def test_jobicy_skips_non_remote_only_profiles() -> None:
    provider = JobicyDiscoveryProvider()
    supported, reason = provider.supports(
        _profile(allowed_work_modes=[WorkMode.ONSITE])
    )
    assert supported is False
    assert reason is not None


@pytest.mark.asyncio
async def test_adzuna_does_not_promote_predicted_salary_to_verified_salary() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["app_id"] == "test-app"
        assert request.url.params["app_key"] == "test-key"
        assert request.url.params["salary_min"] == "65000"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "predicted",
                        "title": "Remote Data Engineer",
                        "description": "Remote Python data role",
                        "created": "2026-09-20T12:00:00Z",
                        "redirect_url": "https://adzuna.example/predicted",
                        "salary_min": 95000,
                        "salary_max": 125000,
                        "salary_is_predicted": 1,
                        "company": {"display_name": "Predicted Co"},
                        "location": {"display_name": "Remote"},
                        "contract_time": "full_time",
                    },
                    {
                        "id": "verified",
                        "title": "Data Engineer",
                        "description": "Python and SQL",
                        "created": "2026-09-20T12:00:00Z",
                        "redirect_url": "https://adzuna.example/verified",
                        "salary_min": 80000,
                        "salary_max": 100000,
                        "salary_is_predicted": 0,
                        "company": {"display_name": "Verified Co"},
                        "location": {"display_name": "United States"},
                        "contract_time": "full_time",
                    },
                ]
            },
        )

    provider = AdzunaDiscoveryProvider(
        app_id="test-app",
        app_key="test-key",
        country="us",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        jobs, queries = await provider.discover(_profile(), limit=10, client=client)

    assert queries == 1
    predicted = next(job for job in jobs if job.source_job_id == "predicted")
    verified = next(job for job in jobs if job.source_job_id == "verified")
    assert predicted.salary_min is None
    assert predicted.salary_max is None
    assert predicted.metadata["salary_is_predicted"] is True
    assert predicted.metadata["predicted_salary_min"] == 95000
    assert verified.salary_min == 80000
    assert verified.salary_currency == "USD"
    assert verified.salary_interval == "year"


@pytest.mark.asyncio
async def test_adzuna_fans_remote_and_hybrid_queries_across_hubs() -> None:
    seen: list[tuple[str | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.params.get("what"), request.url.params.get("where")))
        return httpx.Response(200, json={"results": []})

    profile = _profile(
        role_queries=["Data Engineer"],
        allowed_work_modes=[WorkMode.REMOTE, WorkMode.HYBRID],
        locations=[],
        hybrid_location_hubs=[
            {
                "label": "Seattle, WA",
                "latitude": 47.6062,
                "longitude": -122.3321,
                "radius_miles": 50,
            },
            {
                "label": "Lansing, MI",
                "latitude": 42.7325,
                "longitude": -84.5555,
                "radius_miles": 50,
            },
        ],
    )
    provider = AdzunaDiscoveryProvider(
        app_id="test-app",
        app_key="test-key",
        country="us",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        _, queries = await provider.discover(profile, limit=20, client=client)

    assert queries == 3
    assert ("Data Engineer remote", None) in seen
    assert ("Data Engineer hybrid", "Seattle, WA") in seen
    assert ("Data Engineer hybrid", "Lansing, MI") in seen
