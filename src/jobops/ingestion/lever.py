from typing import Any

import httpx

from jobops.ingestion.base import IngestionError
from jobops.ingestion.models import SourceJobPosting


class LeverAdapter:
    """Fetch published jobs from Lever's public Postings API."""

    default_base_url = "https://api.lever.co/v0/postings"

    def __init__(
        self,
        site: str,
        company: str,
        *,
        base_url: str = default_base_url,
        page_size: int = 100,
        max_pages: int = 100,
    ):
        self.site = site.strip()
        self.company = company.strip()
        self.base_url = base_url.rstrip("/")
        self.page_size = page_size
        self.max_pages = max_pages
        if not self.site or not self.company:
            raise ValueError("site and company are required")
        if page_size < 1 or max_pages < 1:
            raise ValueError("page_size and max_pages must be positive")

    async def fetch(self, client: httpx.AsyncClient | None = None) -> list[SourceJobPosting]:
        if client is not None:
            return await self._fetch(client)

        async with httpx.AsyncClient(timeout=30.0) as owned_client:
            return await self._fetch(owned_client)

    async def _fetch(self, client: httpx.AsyncClient) -> list[SourceJobPosting]:
        collected: list[SourceJobPosting] = []
        skip = 0

        for _ in range(self.max_pages):
            payload = await self._get_page(client, skip=skip)
            page = self.parse_payload(payload)
            collected.extend(page)

            if len(page) < self.page_size:
                return collected
            skip += len(page)

        raise IngestionError(
            f"Lever pagination exceeded {self.max_pages} pages for site {self.site}"
        )

    async def _get_page(self, client: httpx.AsyncClient, *, skip: int) -> Any:
        url = f"{self.base_url}/{self.site}"
        try:
            response = await client.get(
                url,
                params={"mode": "json", "skip": skip, "limit": self.page_size},
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise IngestionError(f"Lever fetch failed for site {self.site}") from exc

    def parse_payload(self, payload: Any) -> list[SourceJobPosting]:
        if not isinstance(payload, list):
            raise IngestionError("Lever payload is not a postings list")
        return [self._parse_job(item) for item in payload]

    def _parse_job(self, item: Any) -> SourceJobPosting:
        if not isinstance(item, dict) or not item.get("id") or not item.get("text"):
            raise IngestionError("Lever job is missing an id or title")

        categories = item.get("categories") or {}
        salary = item.get("salaryRange") or {}
        if not isinstance(categories, dict):
            categories = {}
        if not isinstance(salary, dict):
            salary = {}

        return SourceJobPosting(
            source="lever",
            source_job_id=str(item["id"]),
            company=self.company,
            title=str(item["text"]),
            description=str(item.get("descriptionPlain") or item.get("description") or ""),
            location=categories.get("location"),
            workplace_type=item.get("workplaceType"),
            employment_type=categories.get("commitment"),
            salary_min=salary.get("min"),
            salary_max=salary.get("max"),
            salary_currency=salary.get("currency"),
            salary_interval=salary.get("interval"),
            source_url=item.get("hostedUrl"),
            apply_url=item.get("applyUrl"),
            metadata={
                "team": categories.get("team"),
                "department": categories.get("department"),
                "all_locations": categories.get("allLocations") or [],
                "country": item.get("country"),
            },
        )
