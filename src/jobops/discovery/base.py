from typing import Protocol

import httpx

from jobops.ingestion.models import SourceJobPosting
from jobops.models.search_profile import SearchProfile


class DiscoveryError(RuntimeError):
    """Raised when a discovery provider cannot safely return jobs."""


class DiscoveryProvider(Protocol):
    provider_name: str

    def supports(self, profile: SearchProfile) -> tuple[bool, str | None]: ...

    async def discover(
        self,
        profile: SearchProfile,
        *,
        limit: int,
        client: httpx.AsyncClient,
    ) -> tuple[list[SourceJobPosting], int]: ...
