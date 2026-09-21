from collections.abc import Sequence
from typing import Protocol

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from jobops.db.models import JobRecord
from jobops.models.job import JobPosting, WorkMode
from jobops.models.query import JobSearchFilters


class JobRepository(Protocol):
    def save(self, job: JobPosting) -> JobPosting: ...

    def get(self, job_id: str) -> JobPosting | None: ...

    def get_by_dedupe_key(self, dedupe_key: str) -> JobPosting | None: ...

    def list(self, *, limit: int = 100, offset: int = 0) -> Sequence[JobPosting]: ...

    def search(
        self,
        filters: JobSearchFilters,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[JobPosting]: ...

    def count(self, filters: JobSearchFilters) -> int: ...

    def deactivate_missing(
        self,
        *,
        source: str,
        source_scope: str,
        active_ids: set[str],
    ) -> int: ...


class SqlAlchemyJobRepository:
    def __init__(self, session: Session):
        self.session = session

    def save(self, job: JobPosting) -> JobPosting:
        record = self.session.get(JobRecord, job.job_id)
        values = self._to_record_values(job)

        if record is None:
            record = JobRecord(**values)
            self.session.add(record)
        else:
            for key, value in values.items():
                setattr(record, key, value)

        self.session.flush()
        return self._to_domain(record)

    def get(self, job_id: str) -> JobPosting | None:
        record = self.session.get(JobRecord, job_id)
        return None if record is None else self._to_domain(record)

    def get_by_dedupe_key(self, dedupe_key: str) -> JobPosting | None:
        statement = (
            select(JobRecord)
            .where(
                JobRecord.dedupe_key == dedupe_key,
                JobRecord.active.is_(True),
            )
            .order_by(JobRecord.created_at.asc(), JobRecord.job_id)
            .limit(1)
        )
        record = self.session.scalar(statement)
        return None if record is None else self._to_domain(record)

    def list(self, *, limit: int = 100, offset: int = 0) -> Sequence[JobPosting]:
        return self.search(
            JobSearchFilters(active=None),
            limit=limit,
            offset=offset,
        )

    def search(
        self,
        filters: JobSearchFilters,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[JobPosting]:
        statement = self._apply_filters(select(JobRecord), filters)
        statement = (
            statement.order_by(JobRecord.updated_at.desc(), JobRecord.job_id)
            .limit(limit)
            .offset(offset)
        )
        records = self.session.scalars(statement).all()
        return [self._to_domain(record) for record in records]

    def count(self, filters: JobSearchFilters) -> int:
        statement = select(func.count()).select_from(JobRecord)
        statement = self._apply_filters(statement, filters)
        return int(self.session.scalar(statement) or 0)

    def deactivate_missing(
        self,
        *,
        source: str,
        source_scope: str,
        active_ids: set[str],
    ) -> int:
        conditions = [
            JobRecord.source == source,
            JobRecord.source_scope == source_scope,
            JobRecord.active.is_(True),
        ]
        if active_ids:
            conditions.append(JobRecord.job_id.not_in(active_ids))

        statement = update(JobRecord).where(*conditions).values(active=False)
        result = self.session.execute(statement)
        self.session.flush()
        return int(result.rowcount or 0)

    @staticmethod
    def _apply_filters(
        statement: Select,
        filters: JobSearchFilters,
    ) -> Select:
        if filters.title:
            statement = statement.where(
                JobRecord.title.ilike(f"%{filters.title.strip()}%")
            )
        if filters.company:
            statement = statement.where(
                JobRecord.company.ilike(f"%{filters.company.strip()}%")
            )
        if filters.location:
            statement = statement.where(
                JobRecord.location.ilike(f"%{filters.location.strip()}%")
            )
        if filters.work_mode is not None:
            statement = statement.where(JobRecord.work_mode == filters.work_mode.value)
        if filters.min_salary is not None:
            statement = statement.where(
                or_(
                    JobRecord.salary_max >= filters.min_salary,
                    (
                        JobRecord.salary_max.is_(None)
                        & (JobRecord.salary_min >= filters.min_salary)
                    ),
                )
            )
        if filters.source:
            statement = statement.where(
                JobRecord.source == filters.source.strip().casefold()
            )
        if filters.active is not None:
            statement = statement.where(JobRecord.active.is_(filters.active))
        return statement

    @staticmethod
    def _to_record_values(job: JobPosting) -> dict[str, object]:
        return {
            "job_id": job.job_id,
            "company": job.company,
            "title": job.title,
            "description": job.description,
            "location": job.location,
            "work_mode": job.work_mode.value,
            "employment_type": job.employment_type,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "salary_currency": job.salary_currency,
            "salary_interval": job.salary_interval,
            "required_skills": list(job.required_skills),
            "preferred_skills": list(job.preferred_skills),
            "minimum_years_experience": job.minimum_years_experience,
            "source": job.source,
            "source_scope": job.source_scope,
            "source_job_id": job.source_job_id,
            "source_url": job.source_url,
            "apply_url": job.apply_url,
            "source_updated_at": job.source_updated_at,
            "dedupe_key": job.dedupe_key,
            "source_metadata": dict(job.source_metadata),
            "active": job.active,
        }

    @staticmethod
    def _to_domain(record: JobRecord) -> JobPosting:
        return JobPosting(
            job_id=record.job_id,
            company=record.company,
            title=record.title,
            description=record.description,
            location=record.location,
            work_mode=WorkMode(record.work_mode),
            employment_type=record.employment_type,
            salary_min=record.salary_min,
            salary_max=record.salary_max,
            salary_currency=record.salary_currency,
            salary_interval=record.salary_interval,
            required_skills=list(record.required_skills or []),
            preferred_skills=list(record.preferred_skills or []),
            minimum_years_experience=record.minimum_years_experience,
            source=record.source,
            source_scope=record.source_scope,
            source_job_id=record.source_job_id,
            source_url=record.source_url,
            apply_url=record.apply_url,
            source_updated_at=record.source_updated_at,
            dedupe_key=record.dedupe_key,
            source_metadata=dict(record.source_metadata or {}),
            active=record.active,
        )
