import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from jobops.db import SqlAlchemyJobRepository
from jobops.models.job import JobPosting, WorkMode

TEST_DATABASE_URL = os.getenv("JOBOPS_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="JOBOPS_TEST_DATABASE_URL is only configured in PostgreSQL integration CI.",
)


def test_repository_against_postgres() -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL)

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM jobs"))

    with Session(engine) as session:
        repository = SqlAlchemyJobRepository(session)
        job = JobPosting(
            job_id="postgres-job-1",
            company="Example",
            title="AI Engineer",
            work_mode=WorkMode.HYBRID,
            required_skills=["Python"],
            source="integration-test",
        )
        repository.save(job)
        session.commit()
        assert repository.get(job.job_id) == job
