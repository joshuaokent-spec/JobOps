import hashlib
import html
import re
from html.parser import HTMLParser
from typing import Final

from jobops.ingestion.models import SourceJobPosting
from jobops.models.job import JobPosting, WorkMode

_WHITESPACE_RE: Final = re.compile(r"\s+")
_KEY_RE: Final = re.compile(r"[^a-z0-9+#.]+")

_ANNUAL_MULTIPLIERS: Final[dict[str, float]] = {
    "annual": 1.0,
    "annually": 1.0,
    "year": 1.0,
    "yearly": 1.0,
    "per-year": 1.0,
    "per-year-salary": 1.0,
    "hour": 2080.0,
    "hourly": 2080.0,
    "per-hour": 2080.0,
    "month": 12.0,
    "monthly": 12.0,
    "per-month": 12.0,
    "week": 52.0,
    "weekly": 52.0,
    "per-week": 52.0,
    "day": 260.0,
    "daily": 260.0,
    "per-day": 260.0,
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def clean_display_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _WHITESPACE_RE.sub(" ", value).strip()
    cleaned = re.sub(r"\s+([.,;:!?])", r"\1", cleaned)
    return cleaned or None


def text_key(value: str | None) -> str:
    cleaned = clean_display_text(value)
    if cleaned is None:
        return ""
    return _KEY_RE.sub(" ", cleaned.casefold()).strip()


def strip_html(value: str) -> str:
    if not value:
        return ""
    parser = _TextExtractor()
    parser.feed(html.unescape(value))
    return clean_display_text(" ".join(parser.parts)) or ""


def normalize_skills(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = clean_display_text(value)
        if cleaned is None:
            continue
        key = cleaned.casefold()
        if key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def canonical_work_mode(
    workplace_type: str | None,
    location: str | None,
) -> WorkMode:
    explicit = text_key(workplace_type)
    if explicit in {"remote", "fully remote"}:
        return WorkMode.REMOTE
    if explicit in {"hybrid", "hybrid remote"}:
        return WorkMode.HYBRID
    if explicit in {"onsite", "on site", "in office", "office"}:
        return WorkMode.ONSITE

    location_key = text_key(location)
    if "hybrid" in location_key.split():
        return WorkMode.HYBRID
    if "remote" in location_key.split():
        return WorkMode.REMOTE
    return WorkMode.UNKNOWN


def source_identity(source: str, source_job_id: str) -> str:
    material = f"{text_key(source)}\0{source_job_id.strip()}".encode()
    return f"job_{hashlib.sha256(material).hexdigest()[:24]}"


def dedupe_fingerprint(
    company: str,
    title: str,
    location: str | None,
    work_mode: WorkMode,
) -> str:
    location_key = "remote" if work_mode is WorkMode.REMOTE else text_key(location)
    material = "\0".join(
        (text_key(company), text_key(title), location_key)
    ).encode()
    return hashlib.sha256(material).hexdigest()[:32]


def _normalize_compensation(
    minimum: float | None,
    maximum: float | None,
    currency: str | None,
    interval: str | None,
) -> tuple[int | None, int | None, str | None, str | None]:
    normalized_currency = clean_display_text(currency)
    if normalized_currency is not None:
        normalized_currency = normalized_currency.upper()

    interval_key = text_key(interval).replace(" ", "-")
    multiplier = _ANNUAL_MULTIPLIERS.get(interval_key)

    if multiplier is None:
        normalized_min = None if minimum is None else round(minimum)
        normalized_max = None if maximum is None else round(maximum)
        return (
            normalized_min,
            normalized_max,
            normalized_currency,
            clean_display_text(interval),
        )

    normalized_min = None if minimum is None else round(minimum * multiplier)
    normalized_max = None if maximum is None else round(maximum * multiplier)
    return normalized_min, normalized_max, normalized_currency, "year"


class JobNormalizer:
    def __init__(self, company_aliases: dict[str, str] | None = None):
        self.company_aliases = {
            text_key(key): clean_display_text(value) or value
            for key, value in (company_aliases or {}).items()
        }

    def normalize(self, source_job: SourceJobPosting) -> JobPosting:
        source = clean_display_text(source_job.source) or source_job.source
        source_scope = clean_display_text(source_job.source_scope)
        source_job_id = source_job.source_job_id.strip()
        company = clean_display_text(source_job.company) or source_job.company
        company = self.company_aliases.get(text_key(company), company)
        title = clean_display_text(source_job.title) or source_job.title
        location = clean_display_text(source_job.location)
        work_mode = canonical_work_mode(source_job.workplace_type, location)
        salary_min, salary_max, salary_currency, salary_interval = _normalize_compensation(
            source_job.salary_min,
            source_job.salary_max,
            source_job.salary_currency,
            source_job.salary_interval,
        )

        return JobPosting(
            job_id=source_identity(source, source_job_id),
            company=company,
            title=title,
            description=strip_html(source_job.description),
            location=location,
            work_mode=work_mode,
            employment_type=clean_display_text(source_job.employment_type),
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=salary_currency,
            salary_interval=salary_interval,
            required_skills=normalize_skills(source_job.required_skills),
            preferred_skills=normalize_skills(source_job.preferred_skills),
            source=source.casefold(),
            source_scope=source_scope,
            source_job_id=source_job_id,
            source_url=clean_display_text(source_job.source_url),
            apply_url=clean_display_text(source_job.apply_url),
            source_updated_at=source_job.source_updated_at,
            dedupe_key=dedupe_fingerprint(company, title, location, work_mode),
            source_metadata={
                "adapter_metadata": source_job.metadata,
                "raw_payload": source_job.raw_payload,
                "original_compensation": {
                    "min": source_job.salary_min,
                    "max": source_job.salary_max,
                    "currency": source_job.salary_currency,
                    "interval": source_job.salary_interval,
                },
            },
        )
