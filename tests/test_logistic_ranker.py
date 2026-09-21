from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from jobops.learning.logistic_ranker import (
    LogisticRankingTrainer,
    RankingModelError,
    load_logistic_ranking_model,
    save_logistic_ranking_model,
)
from jobops.models.ranking_model import LogisticRankingConfig
from jobops.models.training_dataset import (
    RANKING_FEATURE_NAMES,
    DatasetLabelDisposition,
    DatasetManifest,
    DatasetSplit,
    RankingFeatureRow,
)


def _features(
    score: float,
    *,
    source: str = "greenhouse",
    work_mode: str = "remote",
    family: str | None = "data-engineer",
) -> dict[str, str | int | float | bool | None]:
    return {
        "title_fit": score,
        "required_skill_fit": min(score + 5, 100),
        "preferred_skill_fit": max(score - 5, 0),
        "experience_fit": score,
        "compensation_fit": score,
        "work_mode_fit": 100.0 if work_mode == "remote" else 50.0,
        "baseline_overall_score": score,
        "posting_age_days": 10.0,
        "source": source,
        "work_mode": work_mode,
        "salary_min_available": True,
        "salary_max_available": True,
        "salary_any_available": True,
        "resume_family_id": family,
        "prior_positive_feedback_count": 2 if score >= 70 else 0,
        "prior_negative_feedback_count": 0 if score >= 70 else 2,
        "prior_application_count": 1,
        "prior_recruiter_response_count": 0,
        "prior_recruiter_screen_count": 0,
        "prior_interview_count": 0,
        "prior_rejection_count": 0,
        "prior_offer_count": 0,
    }


def _row(
    point_id: str,
    score: float,
    label: int,
    split: DatasetSplit,
    cutoff: datetime,
    *,
    source: str = "greenhouse",
    work_mode: str = "remote",
    family: str | None = "data-engineer",
) -> RankingFeatureRow:
    return RankingFeatureRow(
        point_id=point_id,
        candidate_id="candidate-1",
        job_id=f"job-{point_id}",
        cutoff_at=cutoff,
        features=_features(
            score,
            source=source,
            work_mode=work_mode,
            family=family,
        ),
        label=label,
        label_disposition=(
            DatasetLabelDisposition.POSITIVE if label == 1 else DatasetLabelDisposition.NEGATIVE
        ),
        split=split,
    )


def _rows(*, single_class_validation: bool = False) -> list[RankingFeatureRow]:
    base = datetime(2026, 7, 1, tzinfo=UTC)
    train = [
        _row("train-1", 25, 0, DatasetSplit.TRAIN, base),
        _row("train-2", 35, 0, DatasetSplit.TRAIN, base + timedelta(days=1)),
        _row("train-3", 75, 1, DatasetSplit.TRAIN, base + timedelta(days=2)),
        _row("train-4", 90, 1, DatasetSplit.TRAIN, base + timedelta(days=3)),
    ]
    if single_class_validation:
        validation = [
            _row("validation-1", 80, 1, DatasetSplit.VALIDATION, base + timedelta(days=4)),
            _row("validation-2", 85, 1, DatasetSplit.VALIDATION, base + timedelta(days=5)),
        ]
    else:
        validation = [
            _row("validation-1", 30, 0, DatasetSplit.VALIDATION, base + timedelta(days=4)),
            _row("validation-2", 85, 1, DatasetSplit.VALIDATION, base + timedelta(days=5)),
        ]
    return [*train, *validation]


def _manifest(rows: list[RankingFeatureRow]) -> DatasetManifest:
    train_count = sum(row.split is DatasetSplit.TRAIN for row in rows)
    validation_count = sum(row.split is DatasetSplit.VALIDATION for row in rows)
    return DatasetManifest(
        dataset_name="ranking-interest-v1",
        schema_version=1,
        builder_version="m4.2-v1",
        generated_at=datetime(2026, 9, 1, tzinfo=UTC),
        label_window_seconds=30 * 24 * 60 * 60,
        positive_event_types=["job_saved"],
        negative_event_types=["job_skipped"],
        feature_names=list(RANKING_FEATURE_NAMES),
        row_count=len(rows),
        model_ready_row_count=len(rows),
        class_counts={
            "positive": sum(row.label == 1 for row in rows),
            "negative": sum(row.label == 0 for row in rows),
            "ambiguous": 0,
            "unlabeled": 0,
        },
        split_counts={
            "train": train_count,
            "validation": validation_count,
            "excluded": 0,
        },
        first_prediction_cutoff=min(row.cutoff_at for row in rows),
        last_prediction_cutoff=max(row.cutoff_at for row in rows),
        source_event_cutoff=datetime(2026, 9, 1, tzinfo=UTC),
        dataset_fingerprint="a" * 64,
    )


def test_training_is_deterministic_for_same_dataset() -> None:
    rows = _rows()
    manifest = _manifest(rows)
    config = LogisticRankingConfig(random_state=17)
    trained_at = datetime(2026, 9, 21, tzinfo=UTC)

    first = LogisticRankingTrainer().train(
        rows,
        manifest,
        config,
        trained_at=trained_at,
    )
    second = LogisticRankingTrainer().train(
        list(reversed(rows)),
        manifest,
        config,
        trained_at=trained_at,
    )

    assert first.model.metadata.model_dump() == second.model.metadata.model_dump()
    assert np.allclose(
        first.model.estimator.coef_,
        second.model.estimator.coef_,
    )
    assert np.allclose(
        first.validation_probabilities,
        second.validation_probabilities,
    )


def test_training_metadata_preserves_dataset_lineage_and_feature_order() -> None:
    rows = _rows()
    manifest = _manifest(rows)
    result = LogisticRankingTrainer().train(rows, manifest)

    metadata = result.model.metadata
    assert metadata.dataset_fingerprint == "a" * 64
    assert metadata.dataset_schema_version == 1
    assert metadata.dataset_builder_version == "m4.2-v1"
    assert metadata.source_feature_names == list(RANKING_FEATURE_NAMES)
    assert metadata.train_rows == 4
    assert metadata.validation_rows == 2
    assert len(metadata.coefficients) == len(metadata.transformed_feature_names)
    assert set(metadata.numeric_preprocessing) == set(metadata.numeric_feature_names)


def test_validation_uses_temporal_validation_rows_only() -> None:
    rows = _rows()
    result = LogisticRankingTrainer().train(rows, _manifest(rows))

    evaluation = result.model.metadata.evaluation
    assert evaluation.validation_rows == 2
    assert evaluation.validation_positive == 1
    assert evaluation.validation_negative == 1
    assert len(result.validation_probabilities) == 2
    assert len(result.train_probabilities) == 4
    assert evaluation.roc_auc is not None
    assert evaluation.average_precision is not None
    assert evaluation.log_loss is not None
    assert evaluation.brier_score is not None


def test_single_class_validation_reports_unavailable_auc_metrics() -> None:
    rows = _rows(single_class_validation=True)
    result = LogisticRankingTrainer().train(rows, _manifest(rows))

    evaluation = result.model.metadata.evaluation
    assert evaluation.roc_auc is None
    assert evaluation.average_precision is None
    assert evaluation.baseline_roc_auc is None
    assert evaluation.baseline_average_precision is None
    assert evaluation.log_loss is not None
    assert evaluation.brier_score is not None
    assert any("one target class" in message for message in evaluation.diagnostics)


def test_unknown_categories_use_defined_unknown_bucket() -> None:
    rows = _rows()
    model = LogisticRankingTrainer().train(rows, _manifest(rows)).model
    unseen = _features(
        72,
        source="unknown-ats",
        work_mode="hybrid",
        family="ml-engineer",
    )

    prediction = model.predict_features(unseen)

    assert 0.0 <= prediction.probability <= 1.0
    assert prediction.predicted_label in (0, 1)
    assert "__unknown__" in model.metadata.categorical_vocabulary["source"]


def test_save_and_reload_preserve_predictions_and_metadata(tmp_path) -> None:
    rows = _rows()
    trained = LogisticRankingTrainer().train(
        rows,
        _manifest(rows),
        trained_at=datetime(2026, 9, 21, tzinfo=UTC),
    )
    before = trained.model.predict_features(_features(82))

    estimator_path, metadata_path, evaluation_path = save_logistic_ranking_model(
        trained.model,
        tmp_path,
    )
    loaded = load_logistic_ranking_model(tmp_path)
    after = loaded.predict_features(_features(82))

    assert estimator_path.exists()
    assert metadata_path.exists()
    assert evaluation_path.exists()
    assert loaded.metadata == trained.model.metadata
    assert after == before
    assert "Synthetic" not in metadata_path.read_text()
    assert "candidate-1" not in metadata_path.read_text()


def test_rejects_unsupported_dataset_schema_or_builder() -> None:
    rows = _rows()
    manifest = _manifest(rows).model_copy(update={"schema_version": 2})
    with pytest.raises(RankingModelError, match="schema version"):
        LogisticRankingTrainer().train(rows, manifest)

    manifest = _manifest(rows).model_copy(update={"builder_version": "future-builder"})
    with pytest.raises(RankingModelError, match="builder version"):
        LogisticRankingTrainer().train(rows, manifest)


def test_rejects_feature_manifest_drift() -> None:
    rows = _rows()
    manifest = _manifest(rows).model_copy(
        update={"feature_names": [*RANKING_FEATURE_NAMES[:-1], "new_feature"]}
    )
    with pytest.raises(RankingModelError, match="feature schema"):
        LogisticRankingTrainer().train(rows, manifest)


def test_rejects_single_class_training_split() -> None:
    rows = _rows()
    for row in rows:
        if row.split is DatasetSplit.TRAIN:
            row.label = 1
            row.label_disposition = DatasetLabelDisposition.POSITIVE
    manifest = _manifest(rows)

    with pytest.raises(RankingModelError, match="both target classes"):
        LogisticRankingTrainer().train(rows, manifest)
