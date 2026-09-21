import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from jobops.matching import BaselineJobScorer
from jobops.models.feedback import FeedbackEvent, FeedbackEventType
from jobops.models.training_dataset import (
    RANKING_FEATURE_NAMES,
    DatasetDiagnostics,
    DatasetLabelDisposition,
    DatasetManifest,
    DatasetSplit,
    RankingDecisionPoint,
    RankingFeatureRow,
    TrainingDatasetBuildResult,
    TrainingDatasetSpec,
)

_POSITIVE_HISTORY_EVENTS = {
    FeedbackEventType.JOB_SAVED,
    FeedbackEventType.INTEREST_MARKED,
    FeedbackEventType.STRONG_INTEREST_MARKED,
    FeedbackEventType.RANKING_FEEDBACK_POSITIVE,
}
_NEGATIVE_HISTORY_EVENTS = {
    FeedbackEventType.JOB_SKIPPED,
    FeedbackEventType.RANKING_FEEDBACK_NEGATIVE,
}
_APPLICATION_HISTORY_EVENTS = {
    FeedbackEventType.APPLICATION_STARTED,
    FeedbackEventType.APPLICATION_PREPARED,
    FeedbackEventType.APPLICATION_SUBMITTED,
    FeedbackEventType.APPLICATION_ABANDONED,
    FeedbackEventType.APPLICATION_WITHDRAWN,
}
_INTERVIEW_HISTORY_EVENTS = {
    FeedbackEventType.INTERVIEW_SCHEDULED,
    FeedbackEventType.INTERVIEW_COMPLETED,
}
_OFFER_HISTORY_EVENTS = {
    FeedbackEventType.OFFER_RECEIVED,
    FeedbackEventType.OFFER_ACCEPTED,
    FeedbackEventType.OFFER_DECLINED,
}


class RankingTrainingDatasetBuilder:
    """Build temporally correct candidate-job ranking examples from immutable events."""

    def __init__(self, scorer: BaselineJobScorer | None = None) -> None:
        self.scorer = scorer or BaselineJobScorer()

    def build(
        self,
        points: list[RankingDecisionPoint],
        events: list[FeedbackEvent],
        spec: TrainingDatasetSpec | None = None,
        *,
        generated_at: datetime | None = None,
    ) -> TrainingDatasetBuildResult:
        dataset_spec = spec or TrainingDatasetSpec()
        ordered_points = sorted(
            points,
            key=lambda point: (_as_utc(point.cutoff_at), point.point_id),
        )
        ordered_events = sorted(
            events,
            key=lambda event: (
                _as_utc(event.observed_at),
                _as_utc(event.occurred_at),
                event.event_id,
            ),
        )

        rows: list[RankingFeatureRow] = []
        ignored_after_horizon = 0
        ignored_post_cutoff_features = 0

        for point in ordered_points:
            cutoff = _as_utc(point.cutoff_at)
            horizon = cutoff + dataset_spec.label_window
            candidate_events = [
                event
                for event in ordered_events
                if event.candidate_id == point.candidate.candidate_id
            ]
            feature_events = [
                event for event in candidate_events if _as_utc(event.observed_at) <= cutoff
            ]
            ignored_post_cutoff_features += sum(
                1 for event in candidate_events if _as_utc(event.observed_at) > cutoff
            )

            future_job_events = [
                event
                for event in candidate_events
                if event.job_id == point.job.job_id
                and _label_event_matches_application(point, event)
                and _as_utc(event.occurred_at) > cutoff
                and _as_utc(event.observed_at) > cutoff
            ]
            window_events = [
                event
                for event in future_job_events
                if _as_utc(event.observed_at) <= horizon
            ]
            ignored_after_horizon += sum(
                1 for event in future_job_events if _as_utc(event.observed_at) > horizon
            )

            label, disposition, label_event_ids = _derive_label(
                window_events,
                positive=set(dataset_spec.label_policy.positive_events),
                negative=set(dataset_spec.label_policy.negative_events),
            )
            features = self._features(point, feature_events, cutoff=cutoff)
            rows.append(
                RankingFeatureRow(
                    point_id=point.point_id,
                    candidate_id=point.candidate.candidate_id,
                    job_id=point.job.job_id,
                    application_id=point.application_id,
                    cutoff_at=cutoff,
                    features=features,
                    label=label,
                    label_disposition=disposition,
                    split=DatasetSplit.EXCLUDED,
                    feature_event_ids=[event.event_id for event in feature_events],
                    label_event_ids=label_event_ids,
                )
            )

        rows = _assign_time_splits(rows, train_fraction=dataset_spec.train_fraction)
        diagnostics = _diagnostics(
            rows,
            input_points=len(points),
            ignored_after_horizon_events=ignored_after_horizon,
            ignored_post_cutoff_feature_events=ignored_post_cutoff_features,
        )
        manifest = _manifest(
            rows,
            ordered_events,
            dataset_spec,
            diagnostics,
            generated_at=_as_utc(generated_at or datetime.now(UTC)),
        )
        return TrainingDatasetBuildResult(
            rows=rows,
            manifest=manifest,
            diagnostics=diagnostics,
        )

    def _features(
        self,
        point: RankingDecisionPoint,
        feature_events: list[FeedbackEvent],
        *,
        cutoff: datetime,
    ) -> dict[str, str | int | float | bool | None]:
        score = self.scorer.score(point.candidate, point.job)
        counts = Counter(event.event_type for event in feature_events)

        posting_age_days: float | None = None
        if point.job.source_updated_at is not None:
            source_time = _as_utc(point.job.source_updated_at)
            if source_time <= cutoff:
                posting_age_days = round(
                    max((cutoff - source_time).total_seconds(), 0.0) / 86_400,
                    4,
                )

        return {
            "title_fit": score.title_fit,
            "required_skill_fit": score.required_skill_fit,
            "preferred_skill_fit": score.preferred_skill_fit,
            "experience_fit": score.experience_fit,
            "compensation_fit": score.compensation_fit,
            "work_mode_fit": score.work_mode_fit,
            "baseline_overall_score": score.overall,
            "posting_age_days": posting_age_days,
            "source": point.job.source,
            "work_mode": point.job.work_mode.value,
            "salary_min_available": point.job.salary_min is not None,
            "salary_max_available": point.job.salary_max is not None,
            "salary_any_available": (
                point.job.salary_min is not None or point.job.salary_max is not None
            ),
            "resume_family_id": point.resume_family_id,
            "prior_positive_feedback_count": sum(
                counts[event_type] for event_type in _POSITIVE_HISTORY_EVENTS
            ),
            "prior_negative_feedback_count": sum(
                counts[event_type] for event_type in _NEGATIVE_HISTORY_EVENTS
            ),
            "prior_application_count": sum(
                counts[event_type] for event_type in _APPLICATION_HISTORY_EVENTS
            ),
            "prior_recruiter_response_count": counts[FeedbackEventType.RECRUITER_RESPONSE],
            "prior_recruiter_screen_count": counts[FeedbackEventType.RECRUITER_SCREEN],
            "prior_interview_count": sum(
                counts[event_type] for event_type in _INTERVIEW_HISTORY_EVENTS
            ),
            "prior_rejection_count": counts[FeedbackEventType.REJECTED],
            "prior_offer_count": sum(counts[event_type] for event_type in _OFFER_HISTORY_EVENTS),
        }


def write_training_dataset(
    result: TrainingDatasetBuildResult,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Write deterministic model rows and a manifest; private datasets stay caller-controlled."""
    output_dir.mkdir(parents=True, exist_ok=True)
    rows_path = output_dir / "rows.jsonl"
    manifest_path = output_dir / "manifest.json"

    model_rows = [row for row in result.rows if row.split is not DatasetSplit.EXCLUDED]
    rows_text = "".join(
        json.dumps(row.model_dump(mode="json"), sort_keys=True, separators=(",", ":")) + "\n"
        for row in model_rows
    )
    manifest_text = json.dumps(
        result.manifest.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        indent=2,
    ) + "\n"
    rows_path.write_text(rows_text, encoding="utf-8")
    manifest_path.write_text(manifest_text, encoding="utf-8")
    return rows_path, manifest_path


def _label_event_matches_application(
    point: RankingDecisionPoint,
    event: FeedbackEvent,
) -> bool:
    if point.application_id is None:
        return True
    return event.application_id in (None, point.application_id)


def _derive_label(
    events: list[FeedbackEvent],
    *,
    positive: set[FeedbackEventType],
    negative: set[FeedbackEventType],
) -> tuple[int | None, DatasetLabelDisposition, list[str]]:
    positive_events = [event for event in events if event.event_type in positive]
    negative_events = [event for event in events if event.event_type in negative]
    contributing = sorted(
        [*positive_events, *negative_events],
        key=lambda event: (_as_utc(event.observed_at), event.event_id),
    )
    event_ids = [event.event_id for event in contributing]

    if positive_events and negative_events:
        return None, DatasetLabelDisposition.AMBIGUOUS, event_ids
    if positive_events:
        return 1, DatasetLabelDisposition.POSITIVE, event_ids
    if negative_events:
        return 0, DatasetLabelDisposition.NEGATIVE, event_ids
    return None, DatasetLabelDisposition.UNLABELED, []


def _assign_time_splits(
    rows: list[RankingFeatureRow],
    *,
    train_fraction: float,
) -> list[RankingFeatureRow]:
    eligible = [
        row
        for row in rows
        if row.label_disposition
        in (DatasetLabelDisposition.POSITIVE, DatasetLabelDisposition.NEGATIVE)
    ]
    eligible = sorted(eligible, key=lambda row: (_as_utc(row.cutoff_at), row.point_id))

    if len(eligible) <= 1:
        train_ids = {row.point_id for row in eligible}
        validation_ids: set[str] = set()
    else:
        train_count = int(len(eligible) * train_fraction)
        train_count = min(max(train_count, 1), len(eligible) - 1)
        train_ids = {row.point_id for row in eligible[:train_count]}
        validation_ids = {row.point_id for row in eligible[train_count:]}

    return [
        row.model_copy(
            update={
                "split": (
                    DatasetSplit.TRAIN
                    if row.point_id in train_ids
                    else DatasetSplit.VALIDATION
                    if row.point_id in validation_ids
                    else DatasetSplit.EXCLUDED
                )
            }
        )
        for row in rows
    ]


def _diagnostics(
    rows: list[RankingFeatureRow],
    *,
    input_points: int,
    ignored_after_horizon_events: int,
    ignored_post_cutoff_feature_events: int,
) -> DatasetDiagnostics:
    disposition_counts = Counter(row.label_disposition for row in rows)
    split_counts = Counter(row.split for row in rows)
    return DatasetDiagnostics(
        input_points=input_points,
        output_rows=len(rows),
        model_ready_rows=split_counts[DatasetSplit.TRAIN]
        + split_counts[DatasetSplit.VALIDATION],
        positive_rows=disposition_counts[DatasetLabelDisposition.POSITIVE],
        negative_rows=disposition_counts[DatasetLabelDisposition.NEGATIVE],
        ambiguous_rows=disposition_counts[DatasetLabelDisposition.AMBIGUOUS],
        unlabeled_rows=disposition_counts[DatasetLabelDisposition.UNLABELED],
        train_rows=split_counts[DatasetSplit.TRAIN],
        validation_rows=split_counts[DatasetSplit.VALIDATION],
        ignored_after_horizon_events=ignored_after_horizon_events,
        ignored_post_cutoff_feature_events=ignored_post_cutoff_feature_events,
    )


def _manifest(
    rows: list[RankingFeatureRow],
    events: list[FeedbackEvent],
    spec: TrainingDatasetSpec,
    diagnostics: DatasetDiagnostics,
    *,
    generated_at: datetime,
) -> DatasetManifest:
    cutoffs = [_as_utc(row.cutoff_at) for row in rows]
    latest_horizon = max(cutoffs, default=None)
    if latest_horizon is not None:
        latest_horizon += spec.label_window
    considered_events = [
        event
        for event in events
        if latest_horizon is None or _as_utc(event.observed_at) <= latest_horizon
    ]
    source_event_cutoff = max(
        (_as_utc(event.observed_at) for event in considered_events),
        default=None,
    )

    fingerprint_payload = {
        "spec": {
            "name": spec.name,
            "schema_version": spec.schema_version,
            "builder_version": spec.builder_version,
            "label_window_seconds": int(spec.label_window.total_seconds()),
            "train_fraction": spec.train_fraction,
            "positive_events": sorted(item.value for item in spec.label_policy.positive_events),
            "negative_events": sorted(item.value for item in spec.label_policy.negative_events),
        },
        "feature_names": RANKING_FEATURE_NAMES,
        "rows": [row.model_dump(mode="json") for row in rows],
    }
    encoded = json.dumps(
        fingerprint_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    fingerprint = hashlib.sha256(encoded).hexdigest()

    return DatasetManifest(
        dataset_name=spec.name,
        schema_version=spec.schema_version,
        builder_version=spec.builder_version,
        generated_at=generated_at,
        label_window_seconds=int(spec.label_window.total_seconds()),
        positive_event_types=sorted(
            event_type.value for event_type in spec.label_policy.positive_events
        ),
        negative_event_types=sorted(
            event_type.value for event_type in spec.label_policy.negative_events
        ),
        feature_names=list(RANKING_FEATURE_NAMES),
        row_count=len(rows),
        model_ready_row_count=diagnostics.model_ready_rows,
        class_counts={
            "positive": diagnostics.positive_rows,
            "negative": diagnostics.negative_rows,
            "ambiguous": diagnostics.ambiguous_rows,
            "unlabeled": diagnostics.unlabeled_rows,
        },
        split_counts={
            "train": diagnostics.train_rows,
            "validation": diagnostics.validation_rows,
            "excluded": len(rows) - diagnostics.model_ready_rows,
        },
        first_prediction_cutoff=min(cutoffs, default=None),
        last_prediction_cutoff=max(cutoffs, default=None),
        source_event_cutoff=source_event_cutoff,
        dataset_fingerprint=fingerprint,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
