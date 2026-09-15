import json
from pathlib import Path

import httpx
import pytest

from jobops.ingestion import IngestionError, LeverAdapter

FIXTURES = Path(__file__).parent / "fixtures"


def test_lever_fixture_parses_to_source_contract() -> None:
    payload = json.loads((FIXTURES / "lever_jobs.json").read_text())
    jobs = LeverAdapter("example", "Example AI").parse_payload(payload)

    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "lever"
    assert job.source_job_id == "abc-123"
    assert job.workplace_type == "hybrid"
    assert job.employment_type == "Full-time"
    assert job.salary_min == 110000
    assert job.salary_max == 145000
    assert job.salary_currency == "USD"


@pytest.mark.asyncio
async def test_lever_fetch_paginates_until_short_page() -> None:
    requests: list[int] = []

    def posting(identifier: str) -> dict[str, object]:
        return {
            "id": identifier,
            "text": f"Engineer {identifier}",
            "categories": {"location": "Remote"},
            "descriptionPlain": "Build things.",
        }

    def handler(request: httpx.Request) -> httpx.Response:
        skip = int(request.url.params["skip"])
        requests.append(skip)
        if skip == 0:
            return httpx.Response(200, json=[posting("1"), posting("2")])
        return httpx.Response(200, json=[posting("3")])

    adapter = LeverAdapter("example", "Example AI", page_size=2)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        jobs = await adapter.fetch(client)

    assert requests == [0, 2]
    assert [job.source_job_id for job in jobs] == ["1", "2", "3"]


@pytest.mark.asyncio
async def test_lever_http_failure_is_wrapped() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(IngestionError, match="Lever fetch failed"):
            await LeverAdapter("example", "Example AI").fetch(client)


def test_lever_missing_optional_fields_are_safe() -> None:
    jobs = LeverAdapter("example", "Example AI").parse_payload(
        [{"id": "minimal-1", "text": "Data Scientist"}]
    )
    assert jobs[0].location is None
    assert jobs[0].salary_min is None
    assert jobs[0].metadata["all_locations"] == []


def test_lever_malformed_payload_is_rejected() -> None:
    with pytest.raises(IngestionError, match="not a postings list"):
        LeverAdapter("example", "Example AI").parse_payload({"jobs": []})
