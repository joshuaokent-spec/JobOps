from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from jobops.db.base import Base
from jobops.db.repositories import SqlAlchemyJobRepository
from jobops.models.job import JobPosting, WorkMode
from jobops.models.query import JobSearchFilters


def make_repo() -> tuple[Session, SqlAlchemyJobRepository]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    return session, SqlAlchemyJobRepository(session)


def test_search_filters_and_pagination() -> None:
    session, repository = make_repo()
    repository.save(
        JobPosting(
            job_id="1",
            company="Acme",
            title="Data Engineer",
            location="Remote",
            work_mode=WorkMode.REMOTE,
            salary_min=90000,
            salary_max=120000,
            source="lever",
            source_scope="acme",
        )
    )
    repository.save(
        JobPosting(
            job_id="2",
            company="Acme",
            title="Analyst",
            location="Detroit",
            work_mode=WorkMode.ONSITE,
            salary_min=60000,
            salary_max=70000,
            source="greenhouse",
            source_scope="acme",
        )
    )
    session.commit()

    filters = JobSearchFilters(
        company="acm",
        work_mode=WorkMode.REMOTE,
        min_salary=100000,
    )
    assert repository.count(filters) == 1
    assert [job.job_id for job in repository.search(filters, limit=10)] == ["1"]
    session.close()


def test_deactivate_missing_is_scoped() -> None:
    session, repository = make_repo()
    jobs = [
        JobPosting(
            job_id="1",
            company="A",
            title="One",
            source="lever",
            source_scope="a",
        ),
        JobPosting(
            job_id="2",
            company="A",
            title="Two",
            source="lever",
            source_scope="a",
        ),
        JobPosting(
            job_id="3",
            company="B",
            title="Three",
            source="lever",
            source_scope="b",
        ),
    ]
    for job in jobs:
        repository.save(job)

    assert repository.deactivate_missing(
        source="lever",
        source_scope="a",
        active_ids={"1"},
    ) == 1
    session.commit()
    assert repository.get("1").active is True
    assert repository.get("2").active is False
    assert repository.get("3").active is True
    session.close()
