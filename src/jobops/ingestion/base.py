from typing import Protocol

import httpx

from jobops.ingestion.models import SourceJobPosting


class IngestionError(RuntimeError):
    """Raised when a job source cannot be fetched or parsed safely."""


class JobSourceAdapter(Protocol):
    source_name: str
    source_scope: str
    company: str

    async def fetch(
        self,
        client: httpx.AsyncClient | None = None,
    ) -> list[SourceJobPosting]: ...
