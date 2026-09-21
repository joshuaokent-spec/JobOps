import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from jobops.db.flagship_repository import SqlAlchemyFlagshipReadinessRepository
from jobops.db.onboarding_repository import SqlAlchemyCandidateOnboardingRepository
from jobops.db.repositories import SqlAlchemyJobRepository
from jobops.db.search_profile_repository import SqlAlchemySearchProfileRepository
from jobops.discovery.base import DiscoveryProvider
from jobops.discovery.runner import DiscoveryService
from jobops.flagship.runner import FlagshipRunError, FlagshipRunService
from jobops.models.discovery import DiscoveryProviderName
from jobops.models.flagship_run import FlagshipRunRequest
from jobops.models.flagship_schedule import (
    ScheduledFlagshipBatchResult,
    ScheduledProfileRunResult,
    ScheduledProfileRunStatus,
)

_SAFE_PROFILE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class FlagshipRunInputError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PrivateFlagshipRunInputStore:
    """Load gitignored per-profile FlagshipRunRequest payloads from local disk."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def load(self, profile_id: str) -> FlagshipRunRequest:
        if not _SAFE_PROFILE_ID.fullmatch(profile_id):
            raise FlagshipRunInputError(
                "unsafe_profile_id",
                "search profile id cannot be mapped to a private input filename",
            )

        path = self._resolve(profile_id)
        if path is None:
            raise FlagshipRunInputError(
                "missing_input",
                "private flagship run input is missing",
            )

        try:
            raw = path.read_text(encoding="utf-8")
            if path.suffix.casefold() == ".json":
                payload = json.loads(raw)
            else:
                payload = yaml.safe_load(raw)
            if not isinstance(payload, dict):
                raise ValueError("run input must be an object")
            return FlagshipRunRequest.model_validate(payload)
        except (
            OSError,
            json.JSONDecodeError,
            yaml.YAMLError,
            ValidationError,
            ValueError,
        ) as exc:
            raise FlagshipRunInputError(
                "invalid_input",
                f"private flagship run input is invalid ({type(exc).__name__})",
            ) from exc

    def _resolve(self, profile_id: str) -> Path | None:
        for suffix in (".json", ".yaml", ".yml"):
            candidate = self.root / f"{profile_id}{suffix}"
            if candidate.is_file():
                return candidate
        return None


class DailyFlagshipRunner:
    """Run every active search profile once, isolating each profile failure."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        providers: dict[DiscoveryProviderName, DiscoveryProvider],
        input_store: PrivateFlagshipRunInputStore,
        *,
        discovery_timeout_seconds: float = 30.0,
    ) -> None:
        self.session_factory = session_factory
        self.providers = providers
        self.input_store = input_store
        self.discovery_timeout_seconds = discovery_timeout_seconds

    async def run(self) -> ScheduledFlagshipBatchResult:
        started_at = datetime.now(UTC)
        profiles = self._active_profiles()
        results: list[ScheduledProfileRunResult] = []

        async with httpx.AsyncClient(timeout=self.discovery_timeout_seconds) as client:
            for profile in profiles:
                results.append(
                    await self._run_profile(profile.profile_id, profile.name, client)
                )

        completed_at = datetime.now(UTC)
        return ScheduledFlagshipBatchResult(
            started_at=started_at,
            completed_at=completed_at,
            profiles_total=len(results),
            profiles_succeeded=sum(
                result.status is ScheduledProfileRunStatus.SUCCEEDED for result in results
            ),
            profiles_skipped=sum(
                result.status is ScheduledProfileRunStatus.SKIPPED for result in results
            ),
            profiles_failed=sum(
                result.status is ScheduledProfileRunStatus.FAILED for result in results
            ),
            profile_results=results,
        )

    def _active_profiles(self):
        session = self.session_factory()
        try:
            return list(
                SqlAlchemySearchProfileRepository(session).list(
                    active=True,
                    limit=1000,
                    offset=0,
                )
            )
        finally:
            session.close()

    async def _run_profile(
        self,
        profile_id: str,
        profile_name: str,
        client: httpx.AsyncClient,
    ) -> ScheduledProfileRunResult:
        session = self.session_factory()
        try:
            profile = SqlAlchemySearchProfileRepository(session).get(profile_id)
            if profile is None or not profile.active:
                return ScheduledProfileRunResult(
                    profile_id=profile_id,
                    profile_name=profile_name,
                    status=ScheduledProfileRunStatus.SKIPPED,
                    error_code="profile_inactive",
                    error="search profile is no longer active",
                )

            onboarding_repository = SqlAlchemyCandidateOnboardingRepository(session)
            onboarding = onboarding_repository.get(profile.candidate_id)
            if onboarding is not None:
                readiness = onboarding_repository.status(profile.candidate_id)
                if not readiness.ready_to_run:
                    return ScheduledProfileRunResult(
                        profile_id=profile_id,
                        profile_name=profile_name,
                        status=ScheduledProfileRunStatus.FAILED,
                        error_code="onboarding_not_ready",
                        error="candidate onboarding exists but is not ready to run",
                    )
                request = onboarding.build_run_request()
            else:
                try:
                    request = self.input_store.load(profile_id)
                except FlagshipRunInputError as exc:
                    status = (
                        ScheduledProfileRunStatus.SKIPPED
                        if exc.code == "missing_input"
                        else ScheduledProfileRunStatus.FAILED
                    )
                    return ScheduledProfileRunResult(
                        profile_id=profile_id,
                        profile_name=profile_name,
                        status=status,
                        error_code=exc.code,
                        error=str(exc),
                    )

            jobs = SqlAlchemyJobRepository(session)
            discovery = DiscoveryService(
                jobs,
                self.providers,
                timeout_seconds=self.discovery_timeout_seconds,
            )
            result = await FlagshipRunService(jobs, discovery).run(
                profile,
                request,
                client=client,
            )
            snapshot = SqlAlchemyFlagshipReadinessRepository(session).save(
                candidate_id=profile.candidate_id,
                result=result,
            )
            session.commit()
            return ScheduledProfileRunResult(
                profile_id=profile.profile_id,
                profile_name=profile.name,
                status=ScheduledProfileRunStatus.SUCCEEDED,
                run_id=snapshot.run_id,
                prepared_count=result.prepared_count,
                ready_count=result.ready_count,
                review_required_count=result.review_required_count,
            )
        except FlagshipRunError as exc:
            session.rollback()
            return ScheduledProfileRunResult(
                profile_id=profile_id,
                profile_name=profile_name,
                status=ScheduledProfileRunStatus.FAILED,
                error_code="run_validation",
                error=str(exc),
            )
        except Exception as exc:
            session.rollback()
            return ScheduledProfileRunResult(
                profile_id=profile_id,
                profile_name=profile_name,
                status=ScheduledProfileRunStatus.FAILED,
                error_code="run_failed",
                error=f"{type(exc).__name__}: scheduled flagship run failed",
            )
        finally:
            session.close()
