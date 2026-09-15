import json
from pathlib import Path

import httpx
import pytest

from jobops.ingestion import GreenhouseAdapter, IngestionError

FIXTURES = Path(__file__).parent / "fixtures"


def test_greenhouse_fixture_parses_to_source_contract() -> None:
    payload = json.loads((FIXTURES / "greenhouse_jobs.json").read_text())
    jobs = GreenhouseAdapter("example", "Example Analytics").parse_payload(payload)

    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "greenhouse"
    assert job.source_job_id == "127817"
    assert job.company == "Example Analytics"
    assert job.title == "Data Engineer"
    assert job.location == "Remote - US"
    assert job.metadata["requisition_id"] == "DE-50"


@pytest.mark.asyncio
async def test_greenhouse_fetch_uses_public_content_endpoint() -> None:
    payload = json.loads((FIXTURES / "greenhouse_jobs.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/boards/example/jobs"
        assert request.url.params["content"] == "true"
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        jobs = await GreenhouseAdapter("example", "Example Analytics").fetch(client)

    assert [job.source_job_id for job in jobs] == ["127817"]


@pytest.mark.asyncio
async def test_greenhouse_http_failure_is_wrapped() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(IngestionError, match="Greenhouse fetch failed"):
            await GreenhouseAdapter("example", "Example Analytics").fetch(client)


def test_greenhouse_missing_optional_fields_are_safe() -> None:
    jobs = GreenhouseAdapter("example", "Example Analytics").parse_payload(
        {"jobs": [{"id": 9, "title": "ML Engineer"}]}
    )
    assert jobs[0].location is None
    assert jobs[0].description == ""
    assert jobs[0].metadata["departments"] == []


def test_greenhouse_malformed_payload_is_rejected() -> None:
    with pytest.raises(IngestionError, match="missing a jobs list"):
        GreenhouseAdapter("example", "Example Analytics").parse_payload({"results": []})
