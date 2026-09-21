from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from jobops.models.candidate import CandidateProfile
from jobops.models.feedback import FeedbackEventType
from jobops.models.job import JobPosting


class DatasetLabelDisposition(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    AMBIGUOUS = "ambiguous"
    UNLABELED = "unlabeled"


class DatasetSplit(StrEnum):
    TRAIN = "train"
    VALIDATION = "validation"
    EXCLUDED = "excluded"


class RankingLabelPolicy(BaseModel):
    positive_events: list[FeedbackEventType] = Field(
        default_factory=lambda: [
            FeedbackEventType.JOB_SAVED,
            FeedbackEventType.INTEREST_MARKED,
            FeedbackEventType.STRONG_INTEREST_MARKED,
            FeedbackEventType.APPLICATION_STARTED,
            FeedbackEventType.APPLICATION_SUBMITTED,
        ]
    )
    negative_events: list[FeedbackEventType] = Field(
        default_factory=lambda: [
            FeedbackEventType.JOB_SKIPPED,
            FeedbackEventType.APPLICATION_ABANDONED,
        ]
    )

    @model_validator(mode="after")
    def _validate_disjoint_labels(self) -> "RankingLabelPolicy":
        overlap = set(self.positive_events) & set(self.negative_events)
        if overlap:
            names = ", ".join(sorted(item.value for item in overlap))
            raise ValueError(f"positive and negative label events overlap: {names}")
        return self


class TrainingDatasetSpec(BaseModel):
    name: str = Field(default="ranking-interest-v1", min_length=1, max_length=200)
    schema_version: int = Field(default=1, ge=1)
    builder_version: str = Field(default="m4.2-v1", min_length=1, max_length=100)
    label_window: timedelta = Field(default=timedelta(days=30))
    train_fraction: float = Field(default=0.8, gt=0.0, lt=1.0)
    label_policy: RankingLabelPolicy = Field(default_factory=RankingLabelPolicy)

    @model_validator(mode="after")
    def _validate_window(self) -> "TrainingDatasetSpec":
        if self.label_window <= timedelta(0):
            raise ValueError("label_window must be positive")
        if self.label_window > timedelta(days=365):
            raise ValueError("label_window cannot exceed 365 days")
        return self


class RankingDecisionPoint(BaseModel):
    point_id: str = Field(min_length=1, max_length=255)
    candidate: CandidateProfile
    job: JobPosting
    cutoff_at: datetime
    application_id: str | None = Field(default=None, max_length=255)
    resume_family_id: str | None = Field(default=None, max_length=100)


FeatureValue = str | int | float | bool | None


class RankingFeatureRow(BaseModel):
    point_id: str
    candidate_id: str
    job_id: str
    application_id: str | None = None
    cutoff_at: datetime
    features: dict[str, FeatureValue]
    label: int | None = Field(default=None, ge=0, le=1)
    label_disposition: DatasetLabelDisposition
    split: DatasetSplit
    feature_event_ids: list[str] = Field(default_factory=list)
    label_event_ids: list[str] = Field(default_factory=list)


class DatasetDiagnostics(BaseModel):
    input_points: int = Field(ge=0)
    output_rows: int = Field(ge=0)
    model_ready_rows: int = Field(ge=0)
    positive_rows: int = Field(ge=0)
    negative_rows: int = Field(ge=0)
    ambiguous_rows: int = Field(ge=0)
    unlabeled_rows: int = Field(ge=0)
    train_rows: int = Field(ge=0)
    validation_rows: int = Field(ge=0)
    ignored_after_horizon_events: int = Field(ge=0)
    ignored_post_cutoff_feature_events: int = Field(ge=0)


class DatasetManifest(BaseModel):
    dataset_name: str
    schema_version: int
    builder_version: str
    generated_at: datetime
    label_window_seconds: int = Field(gt=0)
    positive_event_types: list[str]
    negative_event_types: list[str]
    feature_names: list[str]
    row_count: int = Field(ge=0)
    model_ready_row_count: int = Field(ge=0)
    class_counts: dict[str, int]
    split_counts: dict[str, int]
    first_prediction_cutoff: datetime | None = None
    last_prediction_cutoff: datetime | None = None
    source_event_cutoff: datetime | None = None
    dataset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class TrainingDatasetBuildResult(BaseModel):
    rows: list[RankingFeatureRow]
    manifest: DatasetManifest
    diagnostics: DatasetDiagnostics
