from jobops.config import Settings, get_settings
from jobops.discovery.adzuna import AdzunaDiscoveryProvider
from jobops.discovery.base import DiscoveryProvider
from jobops.discovery.jobicy import JobicyDiscoveryProvider
from jobops.models.discovery import DiscoveryProviderName


def build_discovery_providers(
    settings: Settings | None = None,
) -> dict[DiscoveryProviderName, DiscoveryProvider]:
    resolved = settings or get_settings()
    providers: dict[DiscoveryProviderName, DiscoveryProvider] = {}

    if resolved.jobicy_enabled:
        providers[DiscoveryProviderName.JOBICY] = JobicyDiscoveryProvider()

    if resolved.adzuna_app_id and resolved.adzuna_app_key:
        providers[DiscoveryProviderName.ADZUNA] = AdzunaDiscoveryProvider(
            app_id=resolved.adzuna_app_id,
            app_key=resolved.adzuna_app_key,
            country=resolved.adzuna_country,
        )

    return providers
