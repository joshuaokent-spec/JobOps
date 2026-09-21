import hashlib
import json
from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from jobops.models.candidate import CandidateProfile
from jobops.models.feedback import FeedbackEventType
from jobops.models.job import JobPosting


class RankingLabelDisposition(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    AMBIGUOUS = "ambiguous"
    UNLABELED = "unlabeled"


class DatasetSplit(StrEnum):
    TRAIN = "train"
    VALIDATION = "validation"
    UNASSIGNED = "unassigned"


class RankingLabelPolicy(BaseModel):
    positive_events: set[FeedbackEventType] = Field(
        default_factory=lambda: {
            FeedbackEventType.JOB_SAVED,
            FeedbackEventType.INTEREST_MARKED,
            FeedbackEventType.STRONG_INTEREST_MARKED,
            FeedbackEventType.APPLICATION_STARTED,
            FeedbackEventType.APPLICATION_SUBMITTED,
            FeedbackEventType.RANKING_FEEDBACK_POSITIVE,
        }
    )
    negative_events: set[FeedbackEventType] = Field(
        default_factory=lambda: {
            FeedbackEventType.JOB_SKIPPED,
            FeedbackEventType.APPLICATION_ABANDONED,
            FeedbackEventType.RANKING_FEEDBACK_NEGATIVE,
        }
    )

    @model_validator(mode="after")
    def _disjoint_labels(self) -> "RankingLabelPolicy":
        overlap = self.positive_events & self.negative_events
        if overlap:
            values = ", ".join(sorted(item.value for item in overlap))
            raise ValueError(f"positive and negative event sets overlap: {values}")
        return self


class RankingDatasetSpec(BaseModel):
    schema_version: int = Field(default=1, ge=1)
    builder_version: str = "m4.2-v1"
    label_window_hours: int = Field(default=168, ge=1, le=24 * 365)
    validation_fraction: float = Field(default=0.2, gt=0, lt=1)
    label_policy: RankingLabelPolicy = Field(default_factory=RankingLabelPolicy)


class RankingPredictionPoint(BaseModel):
    candidate: CandidateProfile
    job: JobPosting
    prediction_cutoff: datetime
    candidate_snapshot_observed_at: datetime
    job_snapshot_observed_at: datetime
    resume_family_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def _snapshots_must_precede_cutoff(self) -> "RankingPredictionPoint":
        cutoff = _as_utc(self.prediction_cutoff)
        if _as_utc(self.candidate_snapshot_observed_at) > cutoff:
            raise ValueError("candidate snapshot cannot be observed after prediction cutoff")
        if _as_utc(self.job_snapshot_observed_at) > cutoff:
            raise ValueError("job snapshot cannot be observed after prediction cutoff")
        return self


FeatureValue = float | int | str | bool | None


class RankingDatasetRow(BaseModel):
    row_id: str
    candidate_id: str
    job_id: str
    prediction_cutoff: datetime
    candidate_snapshot_observed_at: datetime
    job_snapshot_observed_at: datetime
    resume_family_id: str | None = None
    features: dict[str, FeatureValue]
    label: int | None = Field(default=None, ge=0, le=1)
    label_disposition: RankingLabelDisposition
    split: DatasetSplit = DatasetSplit.UNASSIGNED
    feature_event_ids: list[str] = Field(default_factory=list)
    label_event_ids: list[str] = Field(default_factory=list)


class RankingDatasetDiagnostics(BaseModel):
    total_rows: int = Field(ge=0)
    labeled_rows: int = Field(ge=0)
    positive_rows: int = Field(ge=0)
    negative_rows: int = Field(ge=0)
    ambiguous_rows: int = Field(ge=0)
    unlabeled_rows: int = Field(ge=0)
    train_rows: int = Field(ge=0)
    validation_rows: int = Field(ge=0)


class RankingDatasetManifest(BaseModel):
    schema_version: int
    builder_version: str
    generated_at: datetime
    label_window_hours: int
    positive_events: list[str]
    negative_events: list[str]
    feature_names: list[str]
    row_count: int
    labeled_row_count: int
    positive_count: int
    negative_count: int
    ambiguous_count: int
    unlabeled_count: int
    train_count: int
    validation_count: int
    earliest_prediction_cutoff: datetime | None = None
    latest_prediction_cutoff: datetime | None = None
    maximum_observation_time_used: datetime | None = None
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RankingDatasetBuild(BaseModel):
    spec: RankingDatasetSpec
    rows: list[RankingDatasetRow]
    diagnostics: RankingDatasetDiagnostics
    manifest: RankingDatasetManifest


def stable_row_id(candidate_id: str, job_id: str, cutoff: datetime) -> str:
    payload = f"{candidate_id}\n{job_id}\n{cutoff.isoformat()}".encode()
    return hashlib.sha256(payload).hexdigest()


def stable_dataset_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def label_horizon(cutoff: datetime, spec: RankingDatasetSpec) -> datetime:
    return cutoff + timedelta(hours=spec.label_window_hours)


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, set):
        return sorted(item.value if isinstance(item, StrEnum) else item for item in value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")
