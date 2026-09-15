from typing import Any

import httpx

from jobops.ingestion.base import IngestionError
from jobops.ingestion.models import SourceJobPosting


class GreenhouseAdapter:
    """Fetch published jobs from Greenhouse's public Job Board API."""

    base_url = "https://boards-api.greenhouse.io/v1/boards"

    def __init__(self, board_token: str, company: str):
        self.board_token = board_token.strip()
        self.company = company.strip()
        if not self.board_token or not self.company:
            raise ValueError("board_token and company are required")

    async def fetch(self, client: httpx.AsyncClient | None = None) -> list[SourceJobPosting]:
        if client is not None:
            return await self._fetch(client)

        async with httpx.AsyncClient(timeout=30.0) as owned_client:
            return await self._fetch(owned_client)

    async def _fetch(self, client: httpx.AsyncClient) -> list[SourceJobPosting]:
        url = f"{self.base_url}/{self.board_token}/jobs"
        try:
            response = await client.get(url, params={"content": "true"})
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise IngestionError(f"Greenhouse fetch failed for board {self.board_token}") from exc

        return self.parse_payload(payload)

    def parse_payload(self, payload: Any) -> list[SourceJobPosting]:
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise IngestionError("Greenhouse payload is missing a jobs list")

        return [self._parse_job(item) for item in payload["jobs"]]

    def _parse_job(self, item: Any) -> SourceJobPosting:
        if not isinstance(item, dict) or item.get("id") is None or not item.get("title"):
            raise IngestionError("Greenhouse job is missing an id or title")

        location = item.get("location") or {}
        departments = item.get("departments") or []
        offices = item.get("offices") or []

        return SourceJobPosting(
            source="greenhouse",
            source_job_id=str(item["id"]),
            company=self.company,
            title=str(item["title"]),
            description=str(item.get("content") or ""),
            location=location.get("name") if isinstance(location, dict) else None,
            source_url=item.get("absolute_url"),
            source_updated_at=item.get("updated_at"),
            metadata={
                "internal_job_id": item.get("internal_job_id"),
                "requisition_id": item.get("requisition_id"),
                "language": item.get("language"),
                "departments": departments,
                "offices": offices,
            },
        )
