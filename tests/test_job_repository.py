from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from jobops.db import Base, SqlAlchemyJobRepository
from jobops.ingestion import SourceJobPosting
from jobops.models.job import JobPosting, WorkMode
from jobops.normalization import JobNormalizer


def test_repository_round_trip_and_update() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        repository = SqlAlchemyJobRepository(session)
        original = JobPosting(
            job_id="job-1",
            company="Example Analytics",
            title="Data Engineer",
            description="Build pipelines.",
            location="Remote",
            work_mode=WorkMode.REMOTE,
            salary_min=90000,
            salary_max=120000,
            required_skills=["Python", "SQL"],
            preferred_skills=["PostgreSQL"],
            minimum_years_experience=2,
            source="fixture",
            source_url="https://example.test/jobs/1",
        )

        repository.save(original)
        session.commit()

        stored = repository.get("job-1")
        assert stored == original

        updated = original.model_copy(update={"salary_max": 130000})
        repository.save(updated)
        session.commit()

        assert repository.get("job-1") == updated
        assert list(repository.list()) == [updated]


def test_repository_round_trips_normalization_metadata() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    canonical = JobNormalizer().normalize(
        SourceJobPosting(
            source="lever",
            source_job_id="lever-42",
            company="Example AI",
            title="AI Engineer",
            location="Remote",
            workplace_type="remote",
            employment_type="Full-time",
            salary_min=100000,
            salary_max=130000,
            salary_currency="USD",
            salary_interval="yearly",
            source_url="https://jobs.example.test/42",
            apply_url="https://jobs.example.test/42/apply",
            raw_payload={"id": "lever-42"},
        )
    )

    with Session(engine) as session:
        repository = SqlAlchemyJobRepository(session)
        repository.save(canonical)
        session.commit()
        assert repository.get(canonical.job_id) == canonical
