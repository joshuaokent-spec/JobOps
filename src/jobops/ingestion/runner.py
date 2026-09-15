import json
import logging
from datetime import UTC, datetime
from time import perf_counter

import httpx
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from jobops.db.repositories import SqlAlchemyJobRepository
from jobops.ingestion.base import JobSourceAdapter
from jobops.normalization.job_normalizer import JobNormalizer

logger = logging.getLogger(__name__)


class SourceIngestionMetrics(BaseModel):
    source: str
    source_scope: str
    company: str
    fetched: int = 0
    upserted: int = 0
    deactivated: int = 0
    success: bool = True
    error: str | None = None
    duration_seconds: float = 0.0


class IngestionRunMetrics(BaseModel):
    started_at: datetime
    completed_at: datetime
    sources_total: int
    sources_succeeded: int
    sources_failed: int
    fetched: int
    upserted: int
    deactivated: int
    source_results: list[SourceIngestionMetrics] = Field(default_factory=list)


class IngestionRunner:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        normalizer: JobNormalizer | None = None,
    ):
        self.session_factory = session_factory
        self.normalizer = normalizer or JobNormalizer()

    async def run(self, adapters: list[JobSourceAdapter]) -> IngestionRunMetrics:
        started_at = datetime.now(UTC)
        results: list[SourceIngestionMetrics] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for adapter in adapters:
                result = await self._run_source(adapter, client)
                results.append(result)
                self._log_event("ingestion_source_complete", result.model_dump())

        completed_at = datetime.now(UTC)
        metrics = IngestionRunMetrics(
            started_at=started_at,
            completed_at=completed_at,
            sources_total=len(results),
            sources_succeeded=sum(result.success for result in results),
            sources_failed=sum(not result.success for result in results),
            fetched=sum(result.fetched for result in results),
            upserted=sum(result.upserted for result in results),
            deactivated=sum(result.deactivated for result in results),
            source_results=results,
        )
        self._log_event("ingestion_run_complete", metrics.model_dump())
        return metrics

    async def _run_source(
        self,
        adapter: JobSourceAdapter,
        client: httpx.AsyncClient,
    ) -> SourceIngestionMetrics:
        started = perf_counter()
        try:
            source_jobs = await adapter.fetch(client)
            jobs = [
                self.normalizer.normalize(
                    source_job.model_copy(
                        update={
                            "source": adapter.source_name,
                            "source_scope": adapter.source_scope,
                            "company": adapter.company,
                        }
                    )
                )
                for source_job in source_jobs
            ]
            session = self.session_factory()
            try:
                repo = SqlAlchemyJobRepository(session)
                for job in jobs:
                    repo.save(job.model_copy(update={"active": True}))
                active_ids = {job.job_id for job in jobs}
                deactivated = repo.deactivate_missing(
                    source=adapter.source_name,
                    source_scope=adapter.source_scope,
                    active_ids=active_ids,
                )
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

            return SourceIngestionMetrics(
                source=adapter.source_name,
                source_scope=adapter.source_scope,
                company=adapter.company,
                fetched=len(source_jobs),
                upserted=len(jobs),
                deactivated=deactivated,
                duration_seconds=round(perf_counter() - started, 4),
            )
        except Exception as exc:
            return SourceIngestionMetrics(
                source=adapter.source_name,
                source_scope=adapter.source_scope,
                company=adapter.company,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                duration_seconds=round(perf_counter() - started, 4),
            )

    @staticmethod
    def _log_event(event: str, payload: dict[str, object]) -> None:
        logger.info(json.dumps({"event": event, **payload}, default=str, sort_keys=True))
