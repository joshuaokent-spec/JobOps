from datetime import UTC, datetime, timedelta

from jobops.ml import RankingDatasetBuilder
from jobops.models.candidate import CandidateProfile
from jobops.models.feedback import FeedbackEvent, FeedbackEventSource, FeedbackEventType
from jobops.models.job import JobPosting, WorkMode
from pydantic import ValidationError
import pytest

from jobops.models.training_dataset import (
    DatasetSplit,
    RankingDatasetSpec,
    RankingLabelDisposition,
    RankingPredictionPoint,
)

_BASE = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _candidate() -> CandidateProfile:
    return CandidateProfile(
        candidate_id="candidate-1",
        target_roles=["Data Engineer"],
        skills=["Python", "SQL", "PostgreSQL"],
        years_experience=3,
        preferred_work_modes=["remote"],
        minimum_salary=90000,
    )


def _job(job_id: str = "job-1") -> JobPosting:
    return JobPosting(
        job_id=job_id,
        company="Synthetic Analytics",
        title="Data Engineer",
        work_mode=WorkMode.REMOTE,
        salary_min=95000,
        salary_max=120000,
        salary_currency="USD",
        salary_interval="year",
        required_skills=["Python", "SQL"],
        preferred_skills=["PostgreSQL"],
        minimum_years_experience=2,
        source="greenhouse",
        source_updated_at=_BASE - timedelta(days=2),
    )


def _point(
    *,
    job_id: str = "job-1",
    cutoff: datetime = _BASE,
) -> RankingPredictionPoint:
    return RankingPredictionPoint(
        candidate=_candidate(),
        job=_job(job_id),
        prediction_cutoff=cutoff,
        candidate_snapshot_observed_at=cutoff - timedelta(minutes=2),
        job_snapshot_observed_at=cutoff - timedelta(minutes=1),
        resume_family_id="data-engineering",
    )


def _event(
    event_id: str,
    event_type: FeedbackEventType,
    *,
    job_id: str = "job-1",
    occurred_at: datetime,
    observed_at: datetime | None = None,
) -> FeedbackEvent:
    return FeedbackEvent(
        event_id=event_id,
        event_type=event_type,
        job_id=job_id,
        candidate_id="candidate-1",
        occurred_at=occurred_at,
        observed_at=observed_at or occurred_at,
        source=FeedbackEventSource.USER,
        actor="candidate",
        idempotency_key=f"key-{event_id}",
        schema_version=1,
    )


def test_pre_cutoff_events_become_features_and_future_label_does_not() -> None:
    events = [
        _event(
            "prior-save",
            FeedbackEventType.JOB_SAVED,
            job_id="older-job",
            occurred_at=_BASE - timedelta(days=2),
        ),
        _event(
            "future-submit",
            FeedbackEventType.APPLICATION_SUBMITTED,
            occurred_at=_BASE + timedelta(hours=2),
        ),
    ]

    build = RankingDatasetBuilder().build(
        [_point()],
        events,
        generated_at=_BASE + timedelta(days=8),
    )
    row = build.rows[0]

    assert row.features["prior_positive_feedback_count"] == 1
    assert row.features["prior_application_action_count"] == 0
    assert row.features["baseline_overall"] == 100.0
    assert row.features["source_update_age_days"] == 2.0
    assert row.label == 1
    assert row.label_disposition is RankingLabelDisposition.POSITIVE
    assert row.feature_event_ids == ["prior-save"]
    assert row.label_event_ids == ["future-submit"]


def test_event_observed_after_cutoff_cannot_become_feature() -> None:
    imported_late = _event(
        "late-observed",
        FeedbackEventType.JOB_SAVED,
        job_id="older-job",
        occurred_at=_BASE - timedelta(days=1),
        observed_at=_BASE + timedelta(hours=1),
    )

    build = RankingDatasetBuilder().build(
        [_point()],
        [imported_late],
        generated_at=_BASE + timedelta(days=8),
    )
    row = build.rows[0]

    assert row.features["prior_positive_feedback_count"] == 0
    assert row.feature_event_ids == []
    assert row.label_disposition is RankingLabelDisposition.UNLABELED


def test_pre_cutoff_occurrence_observed_later_is_not_a_future_label() -> None:
    late_import = _event(
        "late-import",
        FeedbackEventType.JOB_SAVED,
        occurred_at=_BASE - timedelta(minutes=10),
        observed_at=_BASE + timedelta(hours=1),
    )

    row = RankingDatasetBuilder().build(
        [_point()],
        [late_import],
        generated_at=_BASE + timedelta(days=8),
    ).rows[0]

    assert row.label is None
    assert row.label_event_ids == []


def test_events_after_label_horizon_are_ignored() -> None:
    spec = RankingDatasetSpec(label_window_hours=24)
    too_late = _event(
        "too-late",
        FeedbackEventType.APPLICATION_SUBMITTED,
        occurred_at=_BASE + timedelta(hours=25),
    )

    row = RankingDatasetBuilder().build(
        [_point()],
        [too_late],
        spec=spec,
        generated_at=_BASE + timedelta(days=2),
    ).rows[0]

    assert row.label_disposition is RankingLabelDisposition.UNLABELED
    assert row.label_event_ids == []


def test_contradictory_future_labels_are_ambiguous() -> None:
    events = [
        _event(
            "save",
            FeedbackEventType.JOB_SAVED,
            occurred_at=_BASE + timedelta(hours=1),
        ),
        _event(
            "skip",
            FeedbackEventType.JOB_SKIPPED,
            occurred_at=_BASE + timedelta(hours=2),
        ),
    ]

    build = RankingDatasetBuilder().build(
        [_point()],
        events,
        generated_at=_BASE + timedelta(days=8),
    )
    row = build.rows[0]

    assert row.label is None
    assert row.label_disposition is RankingLabelDisposition.AMBIGUOUS
    assert row.split is DatasetSplit.UNASSIGNED
    assert build.diagnostics.ambiguous_rows == 1


def test_chronological_split_keeps_validation_after_training() -> None:
    points = [
        _point(job_id=f"job-{index}", cutoff=_BASE + timedelta(days=index))
        for index in range(5)
    ]
    events = [
        _event(
            f"label-{index}",
            FeedbackEventType.JOB_SAVED,
            job_id=f"job-{index}",
            occurred_at=_BASE + timedelta(days=index, hours=1),
        )
        for index in range(5)
    ]

    build = RankingDatasetBuilder().build(
        points,
        events,
        spec=RankingDatasetSpec(validation_fraction=0.4),
        generated_at=_BASE + timedelta(days=10),
    )

    train = [row for row in build.rows if row.split is DatasetSplit.TRAIN]
    validation = [row for row in build.rows if row.split is DatasetSplit.VALIDATION]
    assert len(train) == 3
    assert len(validation) == 2
    assert max(row.prediction_cutoff for row in train) < min(
        row.prediction_cutoff for row in validation
    )


def test_dataset_fingerprint_is_independent_of_generation_time_and_input_order() -> None:
    points = [
        _point(job_id="job-a", cutoff=_BASE),
        _point(job_id="job-b", cutoff=_BASE + timedelta(days=1)),
    ]
    events = [
        _event(
            "a",
            FeedbackEventType.JOB_SAVED,
            job_id="job-a",
            occurred_at=_BASE + timedelta(hours=1),
        ),
        _event(
            "b",
            FeedbackEventType.JOB_SKIPPED,
            job_id="job-b",
            occurred_at=_BASE + timedelta(days=1, hours=1),
        ),
    ]
    builder = RankingDatasetBuilder()

    first = builder.build(
        points,
        events,
        generated_at=_BASE + timedelta(days=10),
    )
    second = builder.build(
        list(reversed(points)),
        list(reversed(events)),
        generated_at=_BASE + timedelta(days=20),
    )

    assert first.manifest.dataset_sha256 == second.manifest.dataset_sha256
    assert [row.row_id for row in first.rows] == [row.row_id for row in second.rows]


def test_employer_outcome_is_history_feature_but_not_default_ranking_label() -> None:
    prior_response = _event(
        "prior-response",
        FeedbackEventType.RECRUITER_RESPONSE,
        job_id="older-job",
        occurred_at=_BASE - timedelta(days=1),
    )
    future_interview = _event(
        "future-interview",
        FeedbackEventType.INTERVIEW_SCHEDULED,
        occurred_at=_BASE + timedelta(hours=4),
    )

    row = RankingDatasetBuilder().build(
        [_point()],
        [prior_response, future_interview],
        generated_at=_BASE + timedelta(days=8),
    ).rows[0]

    assert row.features["prior_employer_outcome_count"] == 1
    assert row.label_disposition is RankingLabelDisposition.UNLABELED
    assert row.label_event_ids == []


def test_prediction_point_rejects_future_candidate_or_job_snapshot() -> None:
    with pytest.raises(ValidationError, match="candidate snapshot"):
        RankingPredictionPoint(
            candidate=_candidate(),
            job=_job(),
            prediction_cutoff=_BASE,
            candidate_snapshot_observed_at=_BASE + timedelta(seconds=1),
            job_snapshot_observed_at=_BASE,
        )

    with pytest.raises(ValidationError, match="job snapshot"):
        RankingPredictionPoint(
            candidate=_candidate(),
            job=_job(),
            prediction_cutoff=_BASE,
            candidate_snapshot_observed_at=_BASE,
            job_snapshot_observed_at=_BASE + timedelta(seconds=1),
        )
