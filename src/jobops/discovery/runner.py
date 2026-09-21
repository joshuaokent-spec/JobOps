from collections import Counter
from datetime import UTC, datetime

import httpx

from jobops.db.repositories import JobRepository
from jobops.discovery.base import DiscoveryProvider
from jobops.matching.hard_constraints import HardConstraintMatcher
from jobops.models.discovery import (
    DiscoveryProviderDiagnostic,
    DiscoveryProviderName,
    DiscoveryProviderStatus,
    DiscoveryRunRequest,
    DiscoveryRunResult,
)
from jobops.models.search_profile import SearchProfile
from jobops.normalization.job_normalizer import JobNormalizer


class DiscoveryService:
    """Fan out across discovery providers and persist eligible canonical jobs."""

    def __init__(
        self,
        repository: JobRepository,
        providers: dict[DiscoveryProviderName, DiscoveryProvider],
        *,
        normalizer: JobNormalizer | None = None,
        matcher: HardConstraintMatcher | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.repository = repository
        self.providers = providers
        self.normalizer = normalizer or JobNormalizer()
        self.matcher = matcher or HardConstraintMatcher()
        self.timeout_seconds = timeout_seconds

    async def run(
        self,
        profile: SearchProfile,
        request: DiscoveryRunRequest | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> DiscoveryRunResult:
        resolved = request or DiscoveryRunRequest()
        started_at = datetime.now(UTC)
        diagnostics: list[DiscoveryProviderDiagnostic] = []
        persisted_ids: list[str] = []
        seen_dedupe_keys: set[str] = set()

        if client is None:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as owned:
                await self._run_providers(
                    profile,
                    resolved,
                    owned,
                    diagnostics,
                    persisted_ids,
                    seen_dedupe_keys,
                )
        else:
            await self._run_providers(
                profile,
                resolved,
                client,
                diagnostics,
                persisted_ids,
                seen_dedupe_keys,
            )

        rejection_summary: Counter[str] = Counter()
        for diagnostic in diagnostics:
            rejection_summary.update(diagnostic.rejection_summary)

        completed_at = datetime.now(UTC)
        return DiscoveryRunResult(
            profile_id=profile.profile_id,
            started_at=started_at,
            completed_at=completed_at,
            providers_requested=len(resolved.providers),
            providers_succeeded=sum(
                item.status is DiscoveryProviderStatus.SUCCESS for item in diagnostics
            ),
            providers_failed=sum(
                item.status is DiscoveryProviderStatus.FAILED for item in diagnostics
            ),
            providers_skipped=sum(
                item.status is DiscoveryProviderStatus.SKIPPED for item in diagnostics
            ),
            fetched=sum(item.fetched for item in diagnostics),
            normalized=sum(item.normalized for item in diagnostics),
            eligible=sum(item.eligible for item in diagnostics),
            rejected=sum(item.rejected for item in diagnostics),
            persisted=sum(item.persisted for item in diagnostics),
            duplicates=sum(item.duplicates for item in diagnostics),
            rejection_summary=dict(sorted(rejection_summary.items())),
            persisted_job_ids=persisted_ids,
            provider_results=diagnostics,
        )

    async def _run_providers(
        self,
        profile: SearchProfile,
        request: DiscoveryRunRequest,
        client: httpx.AsyncClient,
        diagnostics: list[DiscoveryProviderDiagnostic],
        persisted_ids: list[str],
        seen_dedupe_keys: set[str],
    ) -> None:
        for provider_name in request.providers:
            provider = self.providers.get(provider_name)
            if provider is None:
                diagnostics.append(
                    DiscoveryProviderDiagnostic(
                        provider=provider_name,
                        status=DiscoveryProviderStatus.SKIPPED,
                        error="Provider is not configured.",
                    )
                )
                continue

            supported, reason = provider.supports(profile)
            if not supported:
                diagnostics.append(
                    DiscoveryProviderDiagnostic(
                        provider=provider_name,
                        status=DiscoveryProviderStatus.SKIPPED,
                        error=reason or "Provider does not support this profile.",
                    )
                )
                continue

            try:
                source_jobs, query_count = await provider.discover(
                    profile,
                    limit=request.limit_per_provider,
                    client=client,
                )
                normalized_jobs = [self.normalizer.normalize(job) for job in source_jobs]
            except Exception as exc:
                diagnostics.append(
                    DiscoveryProviderDiagnostic(
                        provider=provider_name,
                        status=DiscoveryProviderStatus.FAILED,
                        error=f"{type(exc).__name__}: provider discovery failed",
                    )
                )
                continue

            eligible_jobs = []
            rejection_counts: Counter[str] = Counter()
            rejected = 0
            for job in normalized_jobs:
                constraint_result = self.matcher.evaluate(profile, job)
                if constraint_result.eligible:
                    eligible_jobs.append(job)
                    continue

                rejected += 1
                rejection_counts.update(set(constraint_result.violation_codes))

            persisted = 0
            duplicates = 0
            for job in eligible_jobs:
                dedupe_key = job.dedupe_key
                if dedupe_key and dedupe_key in seen_dedupe_keys:
                    duplicates += 1
                    continue

                existing = (
                    self.repository.get_by_dedupe_key(dedupe_key)
                    if dedupe_key
                    else None
                )
                if existing is not None and existing.job_id != job.job_id:
                    duplicates += 1
                    if dedupe_key:
                        seen_dedupe_keys.add(dedupe_key)
                    continue

                saved = self.repository.save(job.model_copy(update={"active": True}))
                persisted += 1
                persisted_ids.append(saved.job_id)
                if dedupe_key:
                    seen_dedupe_keys.add(dedupe_key)

            diagnostics.append(
                DiscoveryProviderDiagnostic(
                    provider=provider_name,
                    status=DiscoveryProviderStatus.SUCCESS,
                    queries=query_count,
                    fetched=len(source_jobs),
                    normalized=len(normalized_jobs),
                    eligible=len(eligible_jobs),
                    rejected=rejected,
                    persisted=persisted,
                    duplicates=duplicates,
                    rejection_summary=dict(sorted(rejection_counts.items())),
                )
            )
