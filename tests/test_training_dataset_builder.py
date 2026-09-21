import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from jobops.learning.dataset_builder import (
    RankingTrainingDatasetBuilder,
    write_training_dataset,
)
from jobops.models.candidate import CandidateProfile
from jobops.models.feedback import FeedbackEvent, FeedbackEventSource, FeedbackEventType
from jobops.models.job import JobPosting, WorkMode
from jobops.models.training_dataset import (
    RANKING_FEATURE_NAMES,
    DatasetLabelDisposition,
    DatasetSplit,
    RankingDecisionPoint,
    RankingFeatureRow,
    TrainingDatasetSpec,
)


def _candidate(candidate_id: str = "candidate-1") -> CandidateProfile:
    return CandidateProfile(
        candidate_id=candidate_id,
        target_roles=["Data Engineer"],
        skills=["Python", "SQL", "PostgreSQL"],
        years_experience=3,
        preferred_work_modes=["remote", "hybrid"],
        minimum_salary=80_000,
    )


def _job(job_id: str, *, updated_at: datetime | None = None) -> JobPosting:
    return JobPosting(
        job_id=job_id,
        company="Synthetic Co",
        title="Data Engineer",
        description="Synthetic fixture description that must not appear in feature rows.",
        work_mode=WorkMode.REMOTE,
        salary_min=90_000,
        salary_max=120_000,
        salary_currency="USD",
        salary_interval="year",
        required_skills=["Python", "SQL"],
        preferred_skills=["PostgreSQL"],
        minimum_years_experience=2,
        source="greenhouse",
        source_updated_at=updated_at,
    )


def _event(
    event_id: str,
    event_type: FeedbackEventType,
    *,
    job_id: str,
    candidate_id: str = "candidate-1",
    occurred_at: datetime,
    observed_at: datetime,
    application_id: str | None = None,
) -> FeedbackEvent:
    return FeedbackEvent(
        event_id=event_id,
        event_type=event_type,
        job_id=job_id,
        application_id=application_id,
        candidate_id=candidate_id,
        occurred_at=occurred_at,
        observed_at=observed_at,
        source=FeedbackEventSource.USER,
        actor="synthetic-test",
        idempotency_key=f"idem-{event_id}",
        schema_version=1,
        metadata={},
    )


def _point(
    point_id: str,
    job_id: str,
    cutoff: datetime,
    *,
    candidate_id: str = "candidate-1",
) -> RankingDecisionPoint:
    return RankingDecisionPoint(
        point_id=point_id,
        candidate=_candidate(candidate_id),
        job=_job(job_id, updated_at=cutoff - timedelta(days=5)),
        cutoff_at=cutoff,
        application_id=f"application-{point_id}",
        resume_family_id="data-engineer",
    )


def test_post_cutoff_label_does_not_leak_into_features() -> None:
    cutoff = datetime(2026, 9, 1, 12, tzinfo=UTC)
    events = [
        _event(
            "past-save",
            FeedbackEventType.JOB_SAVED,
            job_id="older-job",
            occurred_at=cutoff - timedelta(days=3),
            observed_at=cutoff - timedelta(days=3),
        ),
        _event(
            "future-apply",
            FeedbackEventType.APPLICATION_STARTED,
            job_id="job-1",
            application_id="application-point-1",
            occurred_at=cutoff + timedelta(days=1),
            observed_at=cutoff + timedelta(days=1),
        ),
    ]

    result = RankingTrainingDatasetBuilder().build(
        [_point("point-1", "job-1", cutoff)],
        events,
        generated_at=cutoff + timedelta(days=40),
    )

    row = result.rows[0]
    assert row.label == 1
    assert row.label_disposition is DatasetLabelDisposition.POSITIVE
    assert row.features["prior_positive_feedback_count"] == 1
    assert row.features["prior_application_count"] == 0
    assert row.feature_event_ids == ["past-save"]
    assert row.label_event_ids == ["future-apply"]


def test_late_observed_pre_cutoff_occurrence_is_not_future_label() -> None:
    cutoff = datetime(2026, 9, 1, 12, tzinfo=UTC)
    event = _event(
        "late-import",
        FeedbackEventType.JOB_SAVED,
        job_id="job-1",
        occurred_at=cutoff - timedelta(days=1),
        observed_at=cutoff + timedelta(days=1),
    )

    result = RankingTrainingDatasetBuilder().build(
        [_point("point-1", "job-1", cutoff)],
        [event],
    )

    row = result.rows[0]
    assert row.label is None
    assert row.label_disposition is DatasetLabelDisposition.UNLABELED
    assert row.split is DatasetSplit.EXCLUDED


def test_event_after_label_horizon_is_ignored() -> None:
    cutoff = datetime(2026, 9, 1, 12, tzinfo=UTC)
    event = _event(
        "too-late",
        FeedbackEventType.JOB_SAVED,
        job_id="job-1",
        occurred_at=cutoff + timedelta(days=31),
        observed_at=cutoff + timedelta(days=31),
    )

    result = RankingTrainingDatasetBuilder().build(
        [_point("point-1", "job-1", cutoff)],
        [event],
        TrainingDatasetSpec(label_window=timedelta(days=30)),
    )

    assert result.rows[0].label_disposition is DatasetLabelDisposition.UNLABELED
    assert result.diagnostics.ignored_after_horizon_events == 1


def test_contradictory_labels_are_ambiguous_and_excluded() -> None:
    cutoff = datetime(2026, 9, 1, 12, tzinfo=UTC)
    events = [
        _event(
            "positive",
            FeedbackEventType.JOB_SAVED,
            job_id="job-1",
            occurred_at=cutoff + timedelta(hours=1),
            observed_at=cutoff + timedelta(hours=1),
        ),
        _event(
            "negative",
            FeedbackEventType.JOB_SKIPPED,
            job_id="job-1",
            occurred_at=cutoff + timedelta(hours=2),
            observed_at=cutoff + timedelta(hours=2),
        ),
    ]

    result = RankingTrainingDatasetBuilder().build(
        [_point("point-1", "job-1", cutoff)],
        events,
    )

    row = result.rows[0]
    assert row.label is None
    assert row.label_disposition is DatasetLabelDisposition.AMBIGUOUS
    assert row.split is DatasetSplit.EXCLUDED
    assert result.diagnostics.ambiguous_rows == 1


def test_default_label_policy_does_not_silently_use_employer_outcomes() -> None:
    cutoff = datetime(2026, 9, 1, 12, tzinfo=UTC)
    event = _event(
        "recruiter-response",
        FeedbackEventType.RECRUITER_RESPONSE,
        job_id="job-1",
        occurred_at=cutoff + timedelta(days=2),
        observed_at=cutoff + timedelta(days=2),
    )

    result = RankingTrainingDatasetBuilder().build(
        [_point("point-1", "job-1", cutoff)],
        [event],
    )

    assert result.rows[0].label_disposition is DatasetLabelDisposition.UNLABELED


def test_build_is_deterministic_and_chronological_split_preserves_order() -> None:
    base = datetime(2026, 8, 1, 12, tzinfo=UTC)
    points = [
        _point(f"point-{index}", f"job-{index}", base + timedelta(days=index))
        for index in range(5)
    ]
    events = [
        _event(
            f"label-{index}",
            FeedbackEventType.JOB_SAVED if index % 2 == 0 else FeedbackEventType.JOB_SKIPPED,
            job_id=f"job-{index}",
            occurred_at=base + timedelta(days=index, hours=1),
            observed_at=base + timedelta(days=index, hours=1),
        )
        for index in range(5)
    ]
    spec = TrainingDatasetSpec(train_fraction=0.6)
    builder = RankingTrainingDatasetBuilder()

    first = builder.build(
        points,
        events,
        spec,
        generated_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    second = builder.build(
        list(reversed(points)),
        list(reversed(events)),
        spec,
        generated_at=datetime(2026, 10, 2, tzinfo=UTC),
    )

    assert first.manifest.dataset_fingerprint == second.manifest.dataset_fingerprint
    assert first.manifest.feature_names == list(RANKING_FEATURE_NAMES)
    assert [row.split for row in first.rows] == [
        DatasetSplit.TRAIN,
        DatasetSplit.TRAIN,
        DatasetSplit.TRAIN,
        DatasetSplit.VALIDATION,
        DatasetSplit.VALIDATION,
    ]
    train_cutoffs = [row.cutoff_at for row in first.rows if row.split is DatasetSplit.TRAIN]
    validation_cutoffs = [
        row.cutoff_at for row in first.rows if row.split is DatasetSplit.VALIDATION
    ]
    assert max(train_cutoffs) < min(validation_cutoffs)
    assert first.manifest.class_counts == {
        "positive": 3,
        "negative": 2,
        "ambiguous": 0,
        "unlabeled": 0,
    }


def test_feature_schema_rejects_raw_or_unrecognized_payload_fields() -> None:
    cutoff = datetime(2026, 9, 1, 12, tzinfo=UTC)
    features = {name: None for name in RANKING_FEATURE_NAMES}
    features["candidate_answer"] = "raw private narrative"

    with pytest.raises(ValidationError, match="unsupported ranking feature keys"):
        RankingFeatureRow(
            point_id="point-1",
            candidate_id="candidate-1",
            job_id="job-1",
            cutoff_at=cutoff,
            features=features,
            label=1,
            label_disposition=DatasetLabelDisposition.POSITIVE,
            split=DatasetSplit.TRAIN,
        )


def test_writer_outputs_only_model_ready_rows_without_raw_job_text(tmp_path) -> None:
    base = datetime(2026, 9, 1, 12, tzinfo=UTC)
    points = [
        _point("positive", "job-positive", base),
        _point("ambiguous", "job-ambiguous", base + timedelta(days=1)),
    ]
    events = [
        _event(
            "positive-label",
            FeedbackEventType.JOB_SAVED,
            job_id="job-positive",
            occurred_at=base + timedelta(hours=1),
            observed_at=base + timedelta(hours=1),
        ),
        _event(
            "amb-pos",
            FeedbackEventType.JOB_SAVED,
            job_id="job-ambiguous",
            occurred_at=base + timedelta(days=1, hours=1),
            observed_at=base + timedelta(days=1, hours=1),
        ),
        _event(
            "amb-neg",
            FeedbackEventType.JOB_SKIPPED,
            job_id="job-ambiguous",
            occurred_at=base + timedelta(days=1, hours=2),
            observed_at=base + timedelta(days=1, hours=2),
        ),
    ]

    result = RankingTrainingDatasetBuilder().build(points, events)
    rows_path, manifest_path = write_training_dataset(result, tmp_path)

    lines = rows_path.read_text().splitlines()
    assert len(lines) == 1
    row_payload = json.loads(lines[0])
    assert row_payload["point_id"] == "positive"
    assert "description" not in lines[0]
    assert "Synthetic fixture description" not in lines[0]

    manifest = json.loads(manifest_path.read_text())
    assert manifest["row_count"] == 2
    assert manifest["model_ready_row_count"] == 1
