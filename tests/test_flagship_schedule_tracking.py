import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from jobops.db.base import Base
from jobops.db.flagship_repository import SqlAlchemyFlagshipReadinessRepository
from jobops.db.models import FlagshipPreparedJobRecord, FlagshipRunRecord
from jobops.db.repositories import SqlAlchemyJobRepository
from jobops.db.search_profile_repository import SqlAlchemySearchProfileRepository
from jobops.flagship.schedule import (
    DailyFlagshipRunner,
    FlagshipRunInputError,
    PrivateFlagshipRunInputStore,
)
from jobops.flagship.tracking import FlagshipTrackingService
from jobops.models.flagship_run import FlagshipReadiness
from jobops.models.flagship_schedule import ScheduledProfileRunStatus
from jobops.models.job import JobPosting, WorkMode
from jobops.models.search_profile import SearchProfile


def _factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _profile(profile_id: str, name: str) -> SearchProfile:
    return SearchProfile(
        profile_id=profile_id,
        candidate_id="me",
        name=name,
        role_queries=["Data Engineer"],
        allowed_work_modes=[WorkMode.REMOTE],
        minimum_salary=65000,
    )


def _run_input() -> dict[str, object]:
    return {
        "candidate": {
            "candidate_id": "me",
            "target_roles": ["Data Engineer"],
            "skills": ["Python", "SQL"],
            "years_experience": 3,
            "preferred_work_modes": ["remote"],
            "minimum_salary": 65000,
        },
        "resume_evidence": {
            "candidate_id": "me",
            "sources": [
                {
                    "source_id": "resume-source",
                    "kind": "document",
                    "label": "Verified resume",
                }
            ],
            "items": [
                {
                    "evidence_id": "pipeline-project",
                    "kind": "project",
                    "claim": "Built a production data pipeline in Python and SQL.",
                    "skills": ["Python", "SQL"],
                    "role_families": ["data_engineering"],
                    "source_refs": ["resume-source"],
                    "verified": True,
                }
            ],
            "families": [
                {
                    "family_id": "data-engineer",
                    "name": "Data Engineer",
                    "role_families": ["data_engineering"],
                    "priority_skills": ["Python", "SQL"],
                    "pinned_evidence_ids": ["pipeline-project"],
                }
            ],
        },
        "discovery": {"providers": []},
        "candidate_pool": 100,
        "max_jobs": 10,
        "fallback_family_id": "data-engineer",
    }


def test_private_run_input_store_reports_missing_and_invalid_inputs(tmp_path) -> None:
    store = PrivateFlagshipRunInputStore(tmp_path)

    with pytest.raises(FlagshipRunInputError) as missing:
        store.load("profile-1")
    assert missing.value.code == "missing_input"

    (tmp_path / "profile-1.json").write_text("{not-json", encoding="utf-8")
    with pytest.raises(FlagshipRunInputError) as invalid:
        store.load("profile-1")
    assert invalid.value.code == "invalid_input"


@pytest.mark.asyncio
async def test_daily_runner_isolates_profile_inputs_and_persists_success(tmp_path) -> None:
    factory = _factory()
    with factory() as session:
        profiles = SqlAlchemySearchProfileRepository(session)
        profiles.save(_profile("profile-good", "Good"))
        profiles.save(_profile("profile-missing", "Missing"))
        profiles.save(_profile("profile-invalid", "Invalid"))
        SqlAlchemyJobRepository(session).save(
            JobPosting(
                job_id="job-1",
                company="Data Co",
                title="Data Engineer",
                work_mode=WorkMode.REMOTE,
                salary_min=80000,
                salary_max=100000,
                salary_currency="USD",
                salary_interval="year",
                required_skills=["Python", "SQL"],
            )
        )
        session.commit()

    (tmp_path / "profile-good.json").write_text(
        json.dumps(_run_input()),
        encoding="utf-8",
    )
    (tmp_path / "profile-invalid.yaml").write_text(
        "candidate: definitely-not-a-profile",
        encoding="utf-8",
    )

    result = await DailyFlagshipRunner(
        factory,
        providers={},
        input_store=PrivateFlagshipRunInputStore(tmp_path),
    ).run()

    assert result.profiles_total == 3
    assert result.profiles_succeeded == 1
    assert result.profiles_skipped == 1
    assert result.profiles_failed == 1

    by_id = {item.profile_id: item for item in result.profile_results}
    assert by_id["profile-good"].status is ScheduledProfileRunStatus.SUCCEEDED
    assert by_id["profile-good"].run_id is not None
    assert by_id["profile-good"].prepared_count == 1
    assert by_id["profile-missing"].status is ScheduledProfileRunStatus.SKIPPED
    assert by_id["profile-missing"].error_code == "missing_input"
    assert by_id["profile-invalid"].status is ScheduledProfileRunStatus.FAILED
    assert by_id["profile-invalid"].error_code == "invalid_input"

    with factory() as session:
        repo = SqlAlchemyFlagshipReadinessRepository(session)
        assert repo.count_runs("profile-good") == 1
        assert repo.count_runs("profile-missing") == 0
        assert repo.count_runs("profile-invalid") == 0
        saved = repo.latest("profile-good")
        assert saved is not None
        assert saved.prepared_count == 1
        assert saved.ready_count == 1


def _add_run(
    session: Session,
    *,
    run_id: str,
    profile_id: str,
    completed_at: datetime,
    prepared: list[tuple[str, FlagshipReadiness]],
) -> None:
    ready = sum(readiness is FlagshipReadiness.READY for _, readiness in prepared)
    session.add(
        FlagshipRunRecord(
            run_id=run_id,
            profile_id=profile_id,
            candidate_id="me",
            started_at=completed_at - timedelta(seconds=3),
            completed_at=completed_at,
            total_examined=len(prepared),
            total_hard_eligible=len(prepared),
            total_hard_rejected=0,
            total_fit_eligible=len(prepared),
            total_fit_rejected=0,
            prepared_count=len(prepared),
            ready_count=ready,
            review_required_count=len(prepared) - ready,
            rejection_summary={},
        )
    )
    for rank, (job_id, readiness) in enumerate(prepared, start=1):
        session.add(
            FlagshipPreparedJobRecord(
                run_id=run_id,
                job_id=job_id,
                rank=rank,
                score=90 - rank,
                resume_family_id="data-engineer",
                resume_selection_score=85,
                resume_low_confidence=(
                    readiness is FlagshipReadiness.REVIEW_REQUIRED
                ),
                readiness=readiness.value,
                readiness_reasons=[],
                evidence_ids=["pipeline-project"],
            )
        )


def test_tracking_compares_latest_run_to_previous_deterministically() -> None:
    factory = _factory()
    base = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)

    with factory() as session:
        SqlAlchemySearchProfileRepository(session).save(
            _profile("profile-1", "Daily Data")
        )
        jobs = SqlAlchemyJobRepository(session)
        for job_id in ("job-a", "job-b", "job-c"):
            jobs.save(
                JobPosting(
                    job_id=job_id,
                    company="Data Co",
                    title="Data Engineer",
                    work_mode=WorkMode.REMOTE,
                )
            )
        _add_run(
            session,
            run_id="run-1",
            profile_id="profile-1",
            completed_at=base,
            prepared=[
                ("job-a", FlagshipReadiness.READY),
                ("job-b", FlagshipReadiness.REVIEW_REQUIRED),
            ],
        )
        _add_run(
            session,
            run_id="run-2",
            profile_id="profile-1",
            completed_at=base + timedelta(days=1),
            prepared=[
                ("job-a", FlagshipReadiness.REVIEW_REQUIRED),
                ("job-c", FlagshipReadiness.READY),
            ],
        )
        session.commit()

        tracking = FlagshipTrackingService(
            SqlAlchemyFlagshipReadinessRepository(session)
        ).latest("profile-1")

        assert tracking is not None
        assert tracking.latest_run_id == "run-2"
        assert tracking.previous_run_id == "run-1"
        assert tracking.has_previous_run is True
        assert tracking.new_job_ids == ["job-c"]
        assert tracking.no_longer_prepared_job_ids == ["job-b"]
        assert tracking.newly_ready_job_ids == ["job-c"]
        assert tracking.newly_review_required_job_ids == ["job-a"]
        assert tracking.readiness_changed_job_ids == ["job-a"]
