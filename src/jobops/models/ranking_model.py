from datetime import datetime

from pydantic import BaseModel, Field


class LogisticRankingConfig(BaseModel):
    model_version: str = Field(default="logistic-ranking-v1", min_length=1, max_length=100)
    solver: str = Field(default="liblinear", pattern=r"^liblinear$")
    c: float = Field(default=1.0, gt=0.0)
    max_iter: int = Field(default=1000, ge=10)
    random_state: int = 0
    decision_threshold: float = Field(default=0.5, gt=0.0, lt=1.0)


class NumericPreprocessingStat(BaseModel):
    mean: float
    std: float = Field(gt=0.0)


class RankingModelEvaluation(BaseModel):
    validation_rows: int = Field(ge=0)
    validation_positive: int = Field(ge=0)
    validation_negative: int = Field(ge=0)
    decision_threshold: float
    roc_auc: float | None = None
    average_precision: float | None = None
    log_loss: float | None = None
    brier_score: float | None = None
    accuracy: float | None = None
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    true_negative: int | None = None
    false_positive: int | None = None
    false_negative: int | None = None
    true_positive: int | None = None
    baseline_roc_auc: float | None = None
    baseline_average_precision: float | None = None
    diagnostics: list[str] = Field(default_factory=list)


class RankingModelMetadata(BaseModel):
    model_version: str
    trained_at: datetime
    dataset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    dataset_name: str
    dataset_schema_version: int
    dataset_builder_version: str
    source_feature_names: list[str]
    numeric_feature_names: list[str]
    categorical_feature_names: list[str]
    transformed_feature_names: list[str]
    numeric_preprocessing: dict[str, NumericPreprocessingStat]
    categorical_vocabulary: dict[str, list[str]]
    hyperparameters: dict[str, str | int | float | bool | None]
    intercept: float
    coefficients: dict[str, float]
    train_rows: int = Field(ge=0)
    validation_rows: int = Field(ge=0)
    train_first_cutoff: datetime | None = None
    train_last_cutoff: datetime | None = None
    validation_first_cutoff: datetime | None = None
    validation_last_cutoff: datetime | None = None
    evaluation: RankingModelEvaluation


class RankingPrediction(BaseModel):
    probability: float = Field(ge=0.0, le=1.0)
    predicted_label: int = Field(ge=0, le=1)
    threshold: float
