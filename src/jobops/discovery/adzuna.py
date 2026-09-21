import math
from typing import Any

import httpx

from jobops.discovery.base import DiscoveryError
from jobops.ingestion.models import SourceJobPosting
from jobops.models.job import WorkMode
from jobops.models.search_profile import SearchProfile

_COUNTRY_CURRENCY = {
    "us": "USD",
    "gb": "GBP",
    "ca": "CAD",
    "au": "AUD",
    "de": "EUR",
    "fr": "EUR",
    "nl": "EUR",
}


class AdzunaDiscoveryProvider:
    provider_name = "adzuna"
    base_url = "https://api.adzuna.com/v1/api/jobs"

    def __init__(
        self,
        *,
        app_id: str,
        app_key: str,
        country: str = "us",
        page_size: int = 50,
    ) -> None:
        self.app_id = app_id.strip()
        self.app_key = app_key.strip()
        self.country = country.strip().casefold()
        self.page_size = page_size
        if not self.app_id or not self.app_key:
            raise ValueError("Adzuna app_id and app_key are required")
        if not self.country:
            raise ValueError("Adzuna country is required")
        if page_size < 1 or page_size > 50:
            raise ValueError("Adzuna page_size must be between 1 and 50")

    def supports(self, profile: SearchProfile) -> tuple[bool, str | None]:
        return True, None

    async def discover(
        self,
        profile: SearchProfile,
        *,
        limit: int,
        client: httpx.AsyncClient,
    ) -> tuple[list[SourceJobPosting], int]:
        specs = _query_specs(profile)
        per_query = max(1, math.ceil(limit / len(specs)))
        collected: dict[str, SourceJobPosting] = {}
        queries = 0

        for term, where, mode_hint in specs:
            pages = max(1, math.ceil(per_query / self.page_size))
            for page in range(1, pages + 1):
                queries += 1
                payload = await self._get_page(
                    client,
                    profile=profile,
                    term=term,
                    where=where,
                    mode_hint=mode_hint,
                    page=page,
                    page_limit=min(self.page_size, per_query),
                )
                results = payload.get("results")
                if not isinstance(results, list):
                    raise DiscoveryError("Adzuna payload is missing a results list")
                for item in results:
                    posting = self._parse_job(item)
                    collected.setdefault(posting.source_job_id, posting)
                    if len(collected) >= limit:
                        return list(collected.values()), queries
                if len(results) < min(self.page_size, per_query):
                    break

        return list(collected.values()), queries

    async def _get_page(
        self,
        client: httpx.AsyncClient,
        *,
        profile: SearchProfile,
        term: str | None,
        where: str | None,
        mode_hint: str | None,
        page: int,
        page_limit: int,
    ) -> dict[str, Any]:
        params: dict[str, str | int] = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": page_limit,
            "content-type": "application/json",
        }
        if term:
            query = term if mode_hint is None else f"{term} {mode_hint}"
            params["what"] = query
        elif mode_hint:
            params["what"] = mode_hint
        if where:
            params["where"] = where
        if profile.minimum_salary is not None:
            params["salary_min"] = profile.minimum_salary
        if profile.excluded_keywords:
            params["what_exclude"] = " ".join(profile.excluded_keywords[:5])

        url = f"{self.base_url}/{self.country}/search/{page}"
        try:
            response = await client.get(
                url,
                params=params,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise DiscoveryError("Adzuna discovery request failed") from exc
        if not isinstance(payload, dict):
            raise DiscoveryError("Adzuna response is not a JSON object")
        return payload

    def _parse_job(self, item: Any) -> SourceJobPosting:
        if not isinstance(item, dict):
            raise DiscoveryError("Adzuna job is not an object")
        company = item.get("company")
        location = item.get("location")
        if not isinstance(company, dict):
            company = {}
        if not isinstance(location, dict):
            location = {}

        job_id = item.get("id")
        title = item.get("title")
        company_name = company.get("display_name")
        if job_id is None or not title or not company_name:
            raise DiscoveryError("Adzuna job is missing id, title, or company")

        predicted = bool(item.get("salary_is_predicted"))
        salary_min = None if predicted else _number(item.get("salary_min"))
        salary_max = None if predicted else _number(item.get("salary_max"))
        display_location = _optional_string(location.get("display_name"))
        description = str(item.get("description") or "")
        workplace_type = _workplace_type(str(title), display_location, description)
        redirect_url = _optional_string(item.get("redirect_url"))
        category = item.get("category")
        if not isinstance(category, dict):
            category = {}

        return SourceJobPosting(
            source=self.provider_name,
            source_scope=self.country,
            source_job_id=str(job_id),
            company=str(company_name),
            title=str(title),
            description=description,
            location=display_location,
            workplace_type=workplace_type,
            employment_type=_optional_string(
                item.get("contract_time") or item.get("contract_type")
            ),
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=_COUNTRY_CURRENCY.get(self.country),
            salary_interval="year" if salary_min is not None or salary_max is not None else None,
            source_url=redirect_url,
            apply_url=redirect_url,
            source_updated_at=item.get("created"),
            metadata={
                "attribution": "Adzuna",
                "salary_is_predicted": predicted,
                "predicted_salary_min": item.get("salary_min") if predicted else None,
                "predicted_salary_max": item.get("salary_max") if predicted else None,
                "category_label": category.get("label"),
                "category_tag": category.get("tag"),
                "location_area": location.get("area") or [],
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
            },
            raw_payload=dict(item),
        )


def _search_terms(profile: SearchProfile) -> list[str | None]:
    terms: list[str] = []
    seen: set[str] = set()
    for value in [*profile.role_queries, *profile.required_keywords]:
        clean = " ".join(value.split()).strip()
        key = clean.casefold()
        if not clean or key in seen:
            continue
        seen.add(key)
        terms.append(clean)
        if len(terms) >= 20:
            break
    return terms or [None]


def _query_specs(
    profile: SearchProfile,
    *,
    max_queries: int = 40,
) -> list[tuple[str | None, str | None, str | None]]:
    terms = _search_terms(profile)
    modes = set(profile.allowed_work_modes)
    if not modes:
        where = profile.locations[0] if profile.locations else None
        return [(term, where, None) for term in terms][:max_queries]

    specs: list[tuple[str | None, str | None, str | None]] = []
    if WorkMode.REMOTE in modes:
        specs.extend((term, None, "remote") for term in terms)

    if WorkMode.HYBRID in modes:
        locations = [hub.label for hub in profile.hybrid_location_hubs]
        if not locations:
            locations = list(profile.locations)
        if not locations:
            locations = [None]
        round_index = 0
        while len(specs) < max_queries:
            added = False
            for term_index, term in enumerate(terms):
                location = locations[(term_index + round_index) % len(locations)]
                spec = (term, location, "hybrid")
                if spec not in specs:
                    specs.append(spec)
                    added = True
                    if len(specs) >= max_queries:
                        break
            if not added or round_index + 1 >= len(locations):
                break
            round_index += 1

    if WorkMode.ONSITE in modes and len(specs) < max_queries:
        locations = list(profile.locations) or [None]
        for term_index, term in enumerate(terms):
            location = locations[term_index % len(locations)]
            specs.append((term, location, None))
            if len(specs) >= max_queries:
                break

    return specs[:max_queries] or [(term, None, None) for term in terms][:max_queries]


def _workplace_type(
    title: str,
    location: str | None,
    description: str,
) -> str | None:
    text = " ".join([title, location or "", description]).casefold()
    if "hybrid" in text:
        return "hybrid"
    if "remote" in text:
        return "remote"
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
