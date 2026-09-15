from collections.abc import Sequence
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobops.db.models import JobRecord
from jobops.models.job import JobPosting, WorkMode


class JobRepository(Protocol):
    def save(self, job: JobPosting) -> JobPosting: ...

    def get(self, job_id: str) -> JobPosting | None: ...

    def list(self, *, limit: int = 100, offset: int = 0) -> Sequence[JobPosting]: ...


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

    def list(self, *, limit: int = 100, offset: int = 0) -> Sequence[JobPosting]:
        statement = (
            select(JobRecord)
            .order_by(JobRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        records = self.session.scalars(statement).all()
        return [self._to_domain(record) for record in records]

    @staticmethod
    def _to_record_values(job: JobPosting) -> dict[str, object]:
        return {
            "job_id": job.job_id,
            "company": job.company,
            "title": job.title,
            "description": job.description,
            "location": job.location,
            "work_mode": job.work_mode.value,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "required_skills": list(job.required_skills),
            "preferred_skills": list(job.preferred_skills),
            "minimum_years_experience": job.minimum_years_experience,
            "source": job.source,
            "source_url": job.source_url,
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
            salary_min=record.salary_min,
            salary_max=record.salary_max,
            required_skills=list(record.required_skills or []),
            preferred_skills=list(record.preferred_skills or []),
            minimum_years_experience=record.minimum_years_experience,
            source=record.source,
            source_url=record.source_url,
        )
