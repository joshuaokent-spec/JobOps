import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)

from jobops.models.ranking_model import (
    LogisticRankingConfig,
    NumericPreprocessingStat,
    RankingModelEvaluation,
    RankingModelMetadata,
    RankingPrediction,
)
from jobops.models.training_dataset import (
    RANKING_FEATURE_NAMES,
    DatasetManifest,
    DatasetSplit,
    RankingFeatureRow,
)

CATEGORICAL_FEATURE_NAMES = (
    "source",
    "work_mode",
    "resume_family_id",
)
_NUMERIC_FEATURE_NAMES = tuple(
    name for name in RANKING_FEATURE_NAMES if name not in CATEGORICAL_FEATURE_NAMES
)
_UNKNOWN_CATEGORY = "__unknown__"
_MISSING_CATEGORY = "__missing__"


class RankingModelError(RuntimeError):
    """Raised when the ranking model contract or dataset lineage is invalid."""


@dataclass(slots=True)
class LogisticRankingModel:
    estimator: LogisticRegression
    metadata: RankingModelMetadata

    def predict_features(
        self,
        features: dict[str, str | int | float | bool | None],
    ) -> RankingPrediction:
        _validate_feature_keys(features)
        matrix = _encode_feature_dicts(
            [features],
            numeric_stats=self.metadata.numeric_preprocessing,
            categorical_vocabulary=self.metadata.categorical_vocabulary,
        )
        probability = float(self.estimator.predict_proba(matrix)[0, 1])
        threshold = float(self.metadata.evaluation.decision_threshold)
        return RankingPrediction(
            probability=probability,
            predicted_label=int(probability >= threshold),
            threshold=threshold,
        )


@dataclass(slots=True)
class LogisticTrainingResult:
    model: LogisticRankingModel
    train_probabilities: list[float]
    validation_probabilities: list[float]


class LogisticRankingTrainer:
    """Train the first explainable supervised ranking baseline."""

    def train(
        self,
        rows: list[RankingFeatureRow],
        manifest: DatasetManifest,
        config: LogisticRankingConfig | None = None,
        *,
        trained_at: datetime | None = None,
    ) -> LogisticTrainingResult:
        resolved = config or LogisticRankingConfig()
        _validate_dataset_contract(rows, manifest)

        train_rows = sorted(
            (row for row in rows if row.split is DatasetSplit.TRAIN),
            key=lambda row: (row.cutoff_at, row.point_id),
        )
        validation_rows = sorted(
            (row for row in rows if row.split is DatasetSplit.VALIDATION),
            key=lambda row: (row.cutoff_at, row.point_id),
        )
        if not train_rows:
            raise RankingModelError("training dataset contains no train rows")

        y_train = np.asarray([_require_label(row) for row in train_rows], dtype=int)
        if len(set(y_train.tolist())) < 2:
            raise RankingModelError("training split must contain both target classes")

        numeric_stats = _fit_numeric_stats(train_rows)
        categorical_vocabulary = _fit_categorical_vocabulary(train_rows)
        transformed_feature_names = _transformed_feature_names(categorical_vocabulary)

        x_train = _encode_rows(
            train_rows,
            numeric_stats=numeric_stats,
            categorical_vocabulary=categorical_vocabulary,
        )
        estimator = LogisticRegression(
            C=resolved.c,
            solver=resolved.solver,
            max_iter=resolved.max_iter,
            random_state=resolved.random_state,
        )
        estimator.fit(x_train, y_train)
        train_probabilities = estimator.predict_proba(x_train)[:, 1].astype(float).tolist()

        validation_probabilities: list[float] = []
        evaluation = _evaluate(
            estimator,
            validation_rows,
            numeric_stats=numeric_stats,
            categorical_vocabulary=categorical_vocabulary,
            threshold=resolved.decision_threshold,
        )
        if validation_rows:
            x_validation = _encode_rows(
                validation_rows,
                numeric_stats=numeric_stats,
                categorical_vocabulary=categorical_vocabulary,
            )
            validation_probabilities = (
                estimator.predict_proba(x_validation)[:, 1].astype(float).tolist()
            )

        coefficients = {
            name: float(value)
            for name, value in zip(
                transformed_feature_names,
                estimator.coef_[0],
                strict=True,
            )
        }
        metadata = RankingModelMetadata(
            model_version=resolved.model_version,
            trained_at=_as_utc(trained_at or datetime.now(UTC)),
            dataset_fingerprint=manifest.dataset_fingerprint,
            dataset_name=manifest.dataset_name,
            dataset_schema_version=manifest.schema_version,
            dataset_builder_version=manifest.builder_version,
            source_feature_names=list(RANKING_FEATURE_NAMES),
            numeric_feature_names=list(_NUMERIC_FEATURE_NAMES),
            categorical_feature_names=list(CATEGORICAL_FEATURE_NAMES),
            transformed_feature_names=transformed_feature_names,
            numeric_preprocessing=numeric_stats,
            categorical_vocabulary=categorical_vocabulary,
            hyperparameters={
                "solver": resolved.solver,
                "C": resolved.c,
                "max_iter": resolved.max_iter,
                "random_state": resolved.random_state,
                "decision_threshold": resolved.decision_threshold,
            },
            intercept=float(estimator.intercept_[0]),
            coefficients=coefficients,
            train_rows=len(train_rows),
            validation_rows=len(validation_rows),
            train_first_cutoff=train_rows[0].cutoff_at if train_rows else None,
            train_last_cutoff=train_rows[-1].cutoff_at if train_rows else None,
            validation_first_cutoff=(
                validation_rows[0].cutoff_at if validation_rows else None
            ),
            validation_last_cutoff=(
                validation_rows[-1].cutoff_at if validation_rows else None
            ),
            evaluation=evaluation,
        )
        return LogisticTrainingResult(
            model=LogisticRankingModel(estimator=estimator, metadata=metadata),
            train_probabilities=train_probabilities,
            validation_probabilities=validation_probabilities,
        )


def load_training_dataset(
    rows_path: Path,
    manifest_path: Path,
) -> tuple[list[RankingFeatureRow], DatasetManifest]:
    manifest = DatasetManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    rows = [
        RankingFeatureRow.model_validate(json.loads(line))
        for line in rows_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    _validate_dataset_contract(rows, manifest)
    return rows, manifest


def save_logistic_ranking_model(
    model: LogisticRankingModel,
    output_dir: Path,
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    estimator_path = output_dir / "model.joblib"
    metadata_path = output_dir / "metadata.json"
    evaluation_path = output_dir / "evaluation.json"

    joblib.dump(model.estimator, estimator_path)
    metadata_path.write_text(
        json.dumps(
            model.metadata.model_dump(mode="json"),
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    evaluation_path.write_text(
        json.dumps(
            model.metadata.evaluation.model_dump(mode="json"),
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return estimator_path, metadata_path, evaluation_path


def load_logistic_ranking_model(output_dir: Path) -> LogisticRankingModel:
    metadata = RankingModelMetadata.model_validate_json(
        (output_dir / "metadata.json").read_text(encoding="utf-8")
    )
    estimator = joblib.load(output_dir / "model.joblib")
    if not isinstance(estimator, LogisticRegression):
        raise RankingModelError("persisted ranking estimator is not logistic regression")
    if len(metadata.transformed_feature_names) != len(estimator.coef_[0]):
        raise RankingModelError("persisted model coefficient count does not match metadata")
    return LogisticRankingModel(estimator=estimator, metadata=metadata)


def _validate_dataset_contract(
    rows: list[RankingFeatureRow],
    manifest: DatasetManifest,
) -> None:
    if manifest.schema_version != 1:
        raise RankingModelError(
            f"unsupported training dataset schema version: {manifest.schema_version}"
        )
    if manifest.builder_version != "m4.2-v1":
        raise RankingModelError(
            f"unsupported training dataset builder version: {manifest.builder_version}"
        )
    if manifest.feature_names != list(RANKING_FEATURE_NAMES):
        raise RankingModelError("training dataset feature schema does not match M4.2")
    if len(manifest.dataset_fingerprint) != 64:
        raise RankingModelError("training dataset fingerprint is invalid")

    model_ready = [
        row for row in rows if row.split in (DatasetSplit.TRAIN, DatasetSplit.VALIDATION)
    ]
    if len(rows) != len(model_ready):
        raise RankingModelError("rows.jsonl may contain only train/validation rows")
    if manifest.model_ready_row_count != len(rows):
        raise RankingModelError(
            "manifest model-ready row count does not match rows.jsonl"
        )
    train_count = sum(row.split is DatasetSplit.TRAIN for row in rows)
    validation_count = sum(row.split is DatasetSplit.VALIDATION for row in rows)
    if manifest.split_counts.get("train") != train_count:
        raise RankingModelError("manifest train row count does not match rows.jsonl")
    if manifest.split_counts.get("validation") != validation_count:
        raise RankingModelError(
            "manifest validation row count does not match rows.jsonl"
        )
    for row in rows:
        _require_label(row)
        _validate_feature_keys(row.features)


def _fit_numeric_stats(
    rows: list[RankingFeatureRow],
) -> dict[str, NumericPreprocessingStat]:
    stats: dict[str, NumericPreprocessingStat] = {}
    for name in _NUMERIC_FEATURE_NAMES:
        values = [
            _numeric_value(row.features[name])
            for row in rows
            if row.features[name] is not None
        ]
        mean = float(sum(values) / len(values)) if values else 0.0
        variance = (
            float(sum((value - mean) ** 2 for value in values) / len(values))
            if values
            else 0.0
        )
        std = math.sqrt(variance)
        if std <= 1e-12:
            std = 1.0
        stats[name] = NumericPreprocessingStat(mean=mean, std=std)
    return stats


def _fit_categorical_vocabulary(
    rows: list[RankingFeatureRow],
) -> dict[str, list[str]]:
    vocabulary: dict[str, list[str]] = {}
    for name in CATEGORICAL_FEATURE_NAMES:
        seen = {_category_value(row.features[name]) for row in rows}
        seen.update({_MISSING_CATEGORY, _UNKNOWN_CATEGORY})
        vocabulary[name] = sorted(seen)
    return vocabulary


def _transformed_feature_names(
    categorical_vocabulary: dict[str, list[str]],
) -> list[str]:
    names = [f"numeric__{name}" for name in _NUMERIC_FEATURE_NAMES]
    for name in CATEGORICAL_FEATURE_NAMES:
        names.extend(
            f"categorical__{name}={value}"
            for value in categorical_vocabulary[name]
        )
    return names


def _encode_rows(
    rows: Iterable[RankingFeatureRow],
    *,
    numeric_stats: dict[str, NumericPreprocessingStat],
    categorical_vocabulary: dict[str, list[str]],
) -> np.ndarray:
    return _encode_feature_dicts(
        [row.features for row in rows],
        numeric_stats=numeric_stats,
        categorical_vocabulary=categorical_vocabulary,
    )


def _encode_feature_dicts(
    feature_dicts: list[dict[str, str | int | float | bool | None]],
    *,
    numeric_stats: dict[str, NumericPreprocessingStat],
    categorical_vocabulary: dict[str, list[str]],
) -> np.ndarray:
    matrix: list[list[float]] = []
    vocab_index = {
        name: {value: index for index, value in enumerate(values)}
        for name, values in categorical_vocabulary.items()
    }

    for features in feature_dicts:
        _validate_feature_keys(features)
        encoded: list[float] = []
        for name in _NUMERIC_FEATURE_NAMES:
            stat = numeric_stats[name]
            raw = features[name]
            value = stat.mean if raw is None else _numeric_value(raw)
            encoded.append((value - stat.mean) / stat.std)

        for name in CATEGORICAL_FEATURE_NAMES:
            values = categorical_vocabulary[name]
            category = _category_value(features[name])
            if category not in vocab_index[name]:
                category = _UNKNOWN_CATEGORY
            one_hot = [0.0] * len(values)
            one_hot[vocab_index[name][category]] = 1.0
            encoded.extend(one_hot)
        matrix.append(encoded)

    return np.asarray(matrix, dtype=float)


def _evaluate(
    estimator: LogisticRegression,
    rows: list[RankingFeatureRow],
    *,
    numeric_stats: dict[str, NumericPreprocessingStat],
    categorical_vocabulary: dict[str, list[str]],
    threshold: float,
) -> RankingModelEvaluation:
    if not rows:
        return RankingModelEvaluation(
            validation_rows=0,
            validation_positive=0,
            validation_negative=0,
            decision_threshold=threshold,
            diagnostics=["No validation rows are available."],
        )

    x_validation = _encode_rows(
        rows,
        numeric_stats=numeric_stats,
        categorical_vocabulary=categorical_vocabulary,
    )
    y_true = np.asarray([_require_label(row) for row in rows], dtype=int)
    probabilities = estimator.predict_proba(x_validation)[:, 1]
    predicted = (probabilities >= threshold).astype(int)
    positive = int(y_true.sum())
    negative = int(len(y_true) - positive)
    diagnostics: list[str] = []

    roc_auc: float | None = None
    average_precision: float | None = None
    if len(set(y_true.tolist())) == 2:
        roc_auc = float(roc_auc_score(y_true, probabilities))
        average_precision = float(average_precision_score(y_true, probabilities))
    else:
        diagnostics.append(
            "Validation contains one target class; ROC AUC and average precision are unavailable."
        )

    matrix = confusion_matrix(y_true, predicted, labels=[0, 1])
    true_negative, false_positive, false_negative, true_positive = (
        int(matrix[0, 0]),
        int(matrix[0, 1]),
        int(matrix[1, 0]),
        int(matrix[1, 1]),
    )

    baseline_probabilities = np.asarray(
        [
            float(row.features["baseline_overall_score"] or 0.0) / 100.0
            for row in rows
        ],
        dtype=float,
    )
    baseline_roc_auc: float | None = None
    baseline_average_precision: float | None = None
    if len(set(y_true.tolist())) == 2:
        baseline_roc_auc = float(roc_auc_score(y_true, baseline_probabilities))
        baseline_average_precision = float(
            average_precision_score(y_true, baseline_probabilities)
        )

    return RankingModelEvaluation(
        validation_rows=len(rows),
        validation_positive=positive,
        validation_negative=negative,
        decision_threshold=threshold,
        roc_auc=roc_auc,
        average_precision=average_precision,
        log_loss=float(log_loss(y_true, probabilities, labels=[0, 1])),
        brier_score=float(brier_score_loss(y_true, probabilities)),
        accuracy=float(accuracy_score(y_true, predicted)),
        precision=float(precision_score(y_true, predicted, zero_division=0)),
        recall=float(recall_score(y_true, predicted, zero_division=0)),
        f1=float(f1_score(y_true, predicted, zero_division=0)),
        true_negative=true_negative,
        false_positive=false_positive,
        false_negative=false_negative,
        true_positive=true_positive,
        baseline_roc_auc=baseline_roc_auc,
        baseline_average_precision=baseline_average_precision,
        diagnostics=diagnostics,
    )


def _validate_feature_keys(
    features: dict[str, str | int | float | bool | None],
) -> None:
    if set(features) != set(RANKING_FEATURE_NAMES):
        raise RankingModelError("prediction feature schema does not match M4.2")


def _require_label(row: RankingFeatureRow) -> int:
    if row.label not in (0, 1):
        raise RankingModelError(
            f"model-ready row {row.point_id!r} does not contain a binary label"
        )
    return int(row.label)


def _numeric_value(value: str | int | float | bool | None) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    raise RankingModelError(f"expected numeric feature value, got {type(value).__name__}")


def _category_value(value: str | int | float | bool | None) -> str:
    if value is None:
        return _MISSING_CATEGORY
    if isinstance(value, str):
        return value.strip() or _MISSING_CATEGORY
    raise RankingModelError(
        f"expected categorical feature value, got {type(value).__name__}"
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
