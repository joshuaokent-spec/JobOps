import math
from typing import Any

import httpx

from jobops.discovery.base import DiscoveryError
from jobops.ingestion.models import SourceJobPosting
from jobops.models.job import WorkMode
from jobops.models.search_profile import SearchProfile


class JobicyDiscoveryProvider:
    provider_name = "jobicy"
    base_url = "https://jobicy.com/api/v2/remote-jobs"

    def __init__(self, *, source_scope: str = "public-remote") -> None:
        self.source_scope = source_scope

    def supports(self, profile: SearchProfile) -> tuple[bool, str | None]:
        if (
            profile.allowed_work_modes
            and WorkMode.REMOTE not in profile.allowed_work_modes
        ):
            return False, "Jobicy is a remote-only provider."
        return True, None

    async def discover(
        self,
        profile: SearchProfile,
        *,
        limit: int,
        client: httpx.AsyncClient,
    ) -> tuple[list[SourceJobPosting], int]:
        queries = _search_terms(profile)
        count_per_query = min(200, max(1, math.ceil(limit / len(queries))))
        geo = _geo_slug(profile)
        collected: dict[str, SourceJobPosting] = {}

        for term in queries:
            params: dict[str, str | int] = {"count": count_per_query}
            if term is not None:
                params["tag"] = term[:50]
            if geo is not None:
                params["geo"] = geo

            payload = await self._get(client, params)
            jobs = payload.get("jobs")
            if not isinstance(jobs, list):
                raise DiscoveryError("Jobicy payload is missing a jobs list")

            for item in jobs:
                posting = self._parse_job(item)
                collected.setdefault(posting.source_job_id, posting)
                if len(collected) >= limit:
                    return list(collected.values()), len(queries)

        return list(collected.values()), len(queries)

    async def _get(
        self,
        client: httpx.AsyncClient,
        params: dict[str, str | int],
    ) -> dict[str, Any]:
        try:
            response = await client.get(
                self.base_url,
                params=params,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise DiscoveryError("Jobicy discovery request failed") from exc
        if not isinstance(payload, dict):
            raise DiscoveryError("Jobicy response is not a JSON object")
        return payload

    def _parse_job(self, item: Any) -> SourceJobPosting:
        if not isinstance(item, dict):
            raise DiscoveryError("Jobicy job is not an object")
        if item.get("id") is None or not item.get("jobTitle") or not item.get("companyName"):
            raise DiscoveryError("Jobicy job is missing id, title, or company")

        job_types = item.get("jobType")
        if not isinstance(job_types, list):
            job_types = []
        industries = item.get("jobIndustry")
        if not isinstance(industries, list):
            industries = []

        url = item.get("url")
        return SourceJobPosting(
            source=self.provider_name,
            source_scope=self.source_scope,
            source_job_id=str(item["id"]),
            company=str(item["companyName"]),
            title=str(item["jobTitle"]),
            description=str(item.get("jobDescription") or item.get("jobExcerpt") or ""),
            location=str(item.get("jobGeo") or "Remote"),
            workplace_type="remote",
            employment_type=str(job_types[0]) if job_types else None,
            salary_min=_number(item.get("salaryMin")),
            salary_max=_number(item.get("salaryMax")),
            salary_currency=_optional_string(item.get("salaryCurrency")),
            salary_interval=_optional_string(item.get("salaryPeriod")),
            source_url=_optional_string(url),
            apply_url=None,
            source_updated_at=item.get("pubDate"),
            metadata={
                "attribution": "Jobicy",
                "canonical_url": url,
                "job_industry": industries,
                "job_types": job_types,
                "job_level": item.get("jobLevel"),
                "job_geo": item.get("jobGeo"),
                "company_logo": item.get("companyLogo"),
            },
            raw_payload=dict(item),
        )


def _search_terms(profile: SearchProfile) -> list[str | None]:
    values = [*profile.role_queries, *profile.required_keywords]
    terms: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = " ".join(value.split()).strip()
        key = clean.casefold()
        if not clean or key in seen:
            continue
        seen.add(key)
        terms.append(clean)
        if len(terms) >= 5:
            break
    return terms or [None]


def _geo_slug(profile: SearchProfile) -> str | None:
    if not profile.locations:
        return None
    normalized = {value.strip().casefold() for value in profile.locations}
    aliases = {
        "us": "usa",
        "usa": "usa",
        "united states": "usa",
        "united states of america": "usa",
        "canada": "canada",
        "europe": "europe",
        "apac": "apac",
        "anywhere": "anywhere",
    }
    for value in normalized:
        slug = aliases.get(value)
        if slug is not None:
            return slug
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
