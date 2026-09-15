from collections.abc import Iterable

from pydantic import BaseModel, Field

from jobops.embeddings import EmbeddingProvider
from jobops.models.job import JobPosting
from jobops.normalization.semantic_deduplication import (
    EmbeddingNearDuplicateComparator,
    JobEmbeddingTextBuilder,
)


class LabeledDuplicatePair(BaseModel):
    pair_id: str
    left: JobPosting
    right: JobPosting
    duplicate: bool


class PairSimilarity(BaseModel):
    pair_id: str
    duplicate: bool
    similarity: float


class ThresholdMetrics(BaseModel):
    threshold: float
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    precision: float
    recall: float
    f1: float


class SemanticEvaluationReport(BaseModel):
    model_name: str
    examples: int
    pair_scores: list[PairSimilarity] = Field(default_factory=list)
    thresholds: list[ThresholdMetrics] = Field(default_factory=list)
    best_threshold: float | None = None


def _safe_ratio(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def _metrics(scores: list[PairSimilarity], threshold: float) -> ThresholdMetrics:
    tp = fp = tn = fn = 0
    for score in scores:
        predicted = score.similarity >= threshold
        if predicted and score.duplicate:
            tp += 1
        elif predicted:
            fp += 1
        elif score.duplicate:
            fn += 1
        else:
            tn += 1
    precision = _safe_ratio(tp, tp + fp)
    recall = _safe_ratio(tp, tp + fn)
    f1 = _safe_ratio(2 * precision * recall, precision + recall)
    return ThresholdMetrics(
        threshold=threshold,
        true_positive=tp,
        false_positive=fp,
        true_negative=tn,
        false_negative=fn,
        precision=round(precision, 6),
        recall=round(recall, 6),
        f1=round(f1, 6),
    )


def evaluate_thresholds(
    provider: EmbeddingProvider,
    examples: Iterable[LabeledDuplicatePair],
    thresholds: Iterable[float],
    *,
    text_builder: JobEmbeddingTextBuilder | None = None,
) -> SemanticEvaluationReport:
    example_list = list(examples)
    comparator = EmbeddingNearDuplicateComparator(
        provider=provider,
        text_builder=text_builder or JobEmbeddingTextBuilder(),
    )
    pair_scores = [
        PairSimilarity(
            pair_id=example.pair_id,
            duplicate=example.duplicate,
            similarity=round(comparator.similarity(example.left, example.right), 6),
        )
        for example in example_list
    ]
    threshold_metrics = [_metrics(pair_scores, threshold) for threshold in thresholds]
    best = max(
        threshold_metrics,
        key=lambda item: (item.f1, item.recall, item.precision, item.threshold),
        default=None,
    )
    return SemanticEvaluationReport(
        model_name=provider.model_name,
        examples=len(example_list),
        pair_scores=pair_scores,
        thresholds=threshold_metrics,
        best_threshold=None if best is None else best.threshold,
    )
