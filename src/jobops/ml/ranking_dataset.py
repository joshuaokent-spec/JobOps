import math
from datetime import UTC, datetime
from typing import Iterable

from jobops.matching import BaselineJobScorer
from jobops.models.feedback import FeedbackEvent, FeedbackEventType
from jobops.models.training_dataset import (
    DatasetSplit,
    RankingDatasetBuild,
    RankingDatasetDiagnostics,
    RankingDatasetManifest,
    RankingDatasetRow,
    RankingDatasetSpec,
    RankingLabelDisposition,
    RankingPredictionPoint,
    label_horizon,
    stable_dataset_hash,
    stable_row_id,
)

_FEATURE_NAMES = [
    "title_fit",
    "required_skill_fit",
    "preferred_skill_fit",
    "experience_fit",
    "compensation_fit",
    "work_mode_fit",
    "baseline_overall",
    "source_update_age_days",
    "salary_min_available",
    "salary_max_available",
    "salary_currency_usd_or_unspecified",
    "resume_family_present",
    "prior_positive_feedback_count",
    "prior_negative_feedback_count",
    "prior_application_action_count",
    "prior_employer_outcome_count",
    "same_job_prior_event_count",
    "job_source",
    "work_mode",
]

_POSITIVE_HISTORY = {
    FeedbackEventType.JOB_SAVED,
    FeedbackEventType.INTEREST_MARKED,
    FeedbackEventType.STRONG_INTEREST_MARKED,
    FeedbackEventType.RANKING_FEEDBACK_POSITIVE,
}
_NEGATIVE_HISTORY = {
    FeedbackEventType.JOB_SKIPPED,
    FeedbackEventType.RANKING_FEEDBACK_NEGATIVE,
}
_APPLICATION_HISTORY = {
    FeedbackEventType.APPLICATION_STARTED,
    FeedbackEventType.APPLICATION_ABANDONED,
    FeedbackEventType.APPLICATION_PREPARED,
    FeedbackEventType.APPLICATION_SUBMITTED,
    FeedbackEventType.APPLICATION_WITHDRAWN,
}
_EMPLOYER_HISTORY = {
    FeedbackEventType.RECRUITER_RESPONSE,
    FeedbackEventType.RECRUITER_SCREEN,
    FeedbackEventType.INTERVIEW_SCHEDULED,
    FeedbackEventType.INTERVIEW_COMPLETED,
    FeedbackEventType.REJECTED,
    FeedbackEventType.OFFER_RECEIVED,
    FeedbackEventType.OFFER_ACCEPTED,
    FeedbackEventType.OFFER_DECLINED,
}


class RankingDatasetBuilder:
    """Build deterministic ranking rows without using information unavailable at cutoff."""

    def __init__(self, scorer: BaselineJobScorer | None = None) -> None:
        self.scorer = scorer or BaselineJobScorer()

    def build(
        self,
        points: Iterable[RankingPredictionPoint],
        events: Iterable[FeedbackEvent],
        *,
        spec: RankingDatasetSpec | None = None,
        generated_at: datetime | None = None,
    ) -> RankingDatasetBuild:
        dataset_spec = spec or RankingDatasetSpec()
        built_at = _as_utc(generated_at or datetime.now(UTC))
        all_events = sorted(
            events,
            key=lambda event: (
                _as_utc(event.observed_at),
                _as_utc(event.occurred_at),
                event.event_id,
            ),
        )
        rows = [
            self._build_row(point, all_events, dataset_spec)
            for point in sorted(
                points,
                key=lambda item: (
                    _as_utc(item.prediction_cutoff),
                    item.candidate.candidate_id,
                    item.job.job_id,
                ),
            )
        ]
        self._assign_splits(rows, dataset_spec.validation_fraction)

        diagnostics = self._diagnostics(rows)
        maximum_observation = self._maximum_observation_used(rows, all_events)
        hash_payload = {
            "spec": {
                "schema_version": dataset_spec.schema_version,
                "builder_version": dataset_spec.builder_version,
                "label_window_hours": dataset_spec.label_window_hours,
                "validation_fraction": dataset_spec.validation_fraction,
                "positive_events": sorted(
                    event.value for event in dataset_spec.label_policy.positive_events
                ),
                "negative_events": sorted(
                    event.value for event in dataset_spec.label_policy.negative_events
                ),
            },
            "rows": [row.model_dump(mode="json") for row in rows],
        }
        dataset_hash = stable_dataset_hash(hash_payload)

        cutoffs = [_as_utc(row.prediction_cutoff) for row in rows]
        manifest = RankingDatasetManifest(
            schema_version=dataset_spec.schema_version,
            builder_version=dataset_spec.builder_version,
            generated_at=built_at,
            label_window_hours=dataset_spec.label_window_hours,
            positive_events=sorted(
                event.value for event in dataset_spec.label_policy.positive_events
            ),
            negative_events=sorted(
                event.value for event in dataset_spec.label_policy.negative_events
            ),
            feature_names=list(_FEATURE_NAMES),
            row_count=diagnostics.total_rows,
            labeled_row_count=diagnostics.labeled_rows,
            positive_count=diagnostics.positive_rows,
            negative_count=diagnostics.negative_rows,
            ambiguous_count=diagnostics.ambiguous_rows,
            unlabeled_count=diagnostics.unlabeled_rows,
            train_count=diagnostics.train_rows,
            validation_count=diagnostics.validation_rows,
            earliest_prediction_cutoff=min(cutoffs) if cutoffs else None,
            latest_prediction_cutoff=max(cutoffs) if cutoffs else None,
            maximum_observation_time_used=maximum_observation,
            dataset_sha256=dataset_hash,
        )
        return RankingDatasetBuild(
            spec=dataset_spec,
            rows=rows,
            diagnostics=diagnostics,
            manifest=manifest,
        )

    def _build_row(
        self,
        point: RankingPredictionPoint,
        events: list[FeedbackEvent],
        spec: RankingDatasetSpec,
    ) -> RankingDatasetRow:
        cutoff = _as_utc(point.prediction_cutoff)
        horizon = label_horizon(cutoff, spec)
        candidate_id = point.candidate.candidate_id

        feature_events = [
            event
            for event in events
            if event.candidate_id == candidate_id
            and _as_utc(event.observed_at) <= cutoff
        ]
        label_events = [
            event
            for event in events
            if event.candidate_id == candidate_id
            and event.job_id == point.job.job_id
            and cutoff < _as_utc(event.occurred_at) <= horizon
            and cutoff < _as_utc(event.observed_at) <= horizon
            and (
                event.event_type in spec.label_policy.positive_events
                or event.event_type in spec.label_policy.negative_events
            )
        ]

        positive = [
            event for event in label_events
            if event.event_type in spec.label_policy.positive_events
        ]
        negative = [
            event for event in label_events
            if event.event_type in spec.label_policy.negative_events
        ]

        if positive and negative:
            label = None
            disposition = RankingLabelDisposition.AMBIGUOUS
        elif positive:
            label = 1
            disposition = RankingLabelDisposition.POSITIVE
        elif negative:
            label = 0
            disposition = RankingLabelDisposition.NEGATIVE
        else:
            label = None
            disposition = RankingLabelDisposition.UNLABELED

        score = self.scorer.score(point.candidate, point.job)
        source_age = None
        if point.job.source_updated_at is not None:
            age = cutoff - _as_utc(point.job.source_updated_at)
            if age.total_seconds() >= 0:
                source_age = round(age.total_seconds() / 86400, 4)

        features = {
            "title_fit": score.title_fit,
            "required_skill_fit": score.required_skill_fit,
            "preferred_skill_fit": score.preferred_skill_fit,
            "experience_fit": score.experience_fit,
            "compensation_fit": score.compensation_fit,
            "work_mode_fit": score.work_mode_fit,
            "baseline_overall": score.overall,
            "source_update_age_days": source_age,
            "salary_min_available": point.job.salary_min is not None,
            "salary_max_available": point.job.salary_max is not None,
            "salary_currency_usd_or_unspecified": point.job.salary_currency in (None, "USD"),
            "resume_family_present": point.resume_family_id is not None,
            "prior_positive_feedback_count": self._count(feature_events, _POSITIVE_HISTORY),
            "prior_negative_feedback_count": self._count(feature_events, _NEGATIVE_HISTORY),
            "prior_application_action_count": self._count(feature_events, _APPLICATION_HISTORY),
            "prior_employer_outcome_count": self._count(feature_events, _EMPLOYER_HISTORY),
            "same_job_prior_event_count": sum(
                event.job_id == point.job.job_id for event in feature_events
            ),
            "job_source": point.job.source or "unknown",
            "work_mode": point.job.work_mode.value,
        }

        return RankingDatasetRow(
            row_id=stable_row_id(candidate_id, point.job.job_id, cutoff),
            candidate_id=candidate_id,
            job_id=point.job.job_id,
            prediction_cutoff=cutoff,
            candidate_snapshot_observed_at=_as_utc(point.candidate_snapshot_observed_at),
            job_snapshot_observed_at=_as_utc(point.job_snapshot_observed_at),
            resume_family_id=point.resume_family_id,
            features=features,
            label=label,
            label_disposition=disposition,
            feature_event_ids=[event.event_id for event in feature_events],
            label_event_ids=[event.event_id for event in label_events],
        )

    @staticmethod
    def _count(events: list[FeedbackEvent], kinds: set[FeedbackEventType]) -> int:
        return sum(event.event_type in kinds for event in events)

    @staticmethod
    def _assign_splits(rows: list[RankingDatasetRow], validation_fraction: float) -> None:
        labeled = [
            row
            for row in rows
            if row.label_disposition
            in (RankingLabelDisposition.POSITIVE, RankingLabelDisposition.NEGATIVE)
        ]
        labeled.sort(key=lambda row: (_as_utc(row.prediction_cutoff), row.row_id))
        if not labeled:
            return
        if len(labeled) == 1:
            labeled[0].split = DatasetSplit.TRAIN
            return

        validation_count = max(1, math.ceil(len(labeled) * validation_fraction))
        validation_count = min(validation_count, len(labeled) - 1)
        split_index = len(labeled) - validation_count
        for row in labeled[:split_index]:
            row.split = DatasetSplit.TRAIN
        for row in labeled[split_index:]:
            row.split = DatasetSplit.VALIDATION

    @staticmethod
    def _diagnostics(rows: list[RankingDatasetRow]) -> RankingDatasetDiagnostics:
        positive = sum(
            row.label_disposition is RankingLabelDisposition.POSITIVE for row in rows
        )
        negative = sum(
            row.label_disposition is RankingLabelDisposition.NEGATIVE for row in rows
        )
        ambiguous = sum(
            row.label_disposition is RankingLabelDisposition.AMBIGUOUS for row in rows
        )
        unlabeled = sum(
            row.label_disposition is RankingLabelDisposition.UNLABELED for row in rows
        )
        return RankingDatasetDiagnostics(
            total_rows=len(rows),
            labeled_rows=positive + negative,
            positive_rows=positive,
            negative_rows=negative,
            ambiguous_rows=ambiguous,
            unlabeled_rows=unlabeled,
            train_rows=sum(row.split is DatasetSplit.TRAIN for row in rows),
            validation_rows=sum(row.split is DatasetSplit.VALIDATION for row in rows),
        )

    @staticmethod
    def _maximum_observation_used(
        rows: list[RankingDatasetRow],
        events: list[FeedbackEvent],
    ) -> datetime | None:
        used_ids = {
            event_id
            for row in rows
            for event_id in (*row.feature_event_ids, *row.label_event_ids)
        }
        used_times = [
            _as_utc(event.observed_at)
            for event in events
            if event.event_id in used_ids
        ]
        return max(used_times) if used_times else None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
