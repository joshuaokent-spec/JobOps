from collections.abc import Sequence

from jobops.models.job import JobPosting
from jobops.normalization.semantic_evaluation import (
    LabeledDuplicatePair,
    evaluate_thresholds,
)


class PairProvider:
    model_name = "eval-fake"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        result = []
        for text in texts:
            if "positive-a" in text or "positive-b" in text:
                result.append([1.0, 0.0])
            elif "negative-a" in text:
                result.append([0.0, 1.0])
            else:
                result.append([1.0, 0.0])
        return result


def posting(job_id: str, title: str) -> JobPosting:
    return JobPosting(job_id=job_id, company="Acme", title=title)


def test_threshold_evaluation_reports_precision_recall_and_best_threshold() -> None:
    examples = [
        LabeledDuplicatePair(
            pair_id="positive",
            left=posting("1", "positive-a"),
            right=posting("2", "positive-b"),
            duplicate=True,
        ),
        LabeledDuplicatePair(
            pair_id="negative",
            left=posting("3", "negative-a"),
            right=posting("4", "negative-b"),
            duplicate=False,
        ),
    ]
    report = evaluate_thresholds(PairProvider(), examples, [0.5, 0.9])
    assert report.examples == 2
    assert report.best_threshold == 0.9
    assert report.thresholds[1].precision == 1.0
    assert report.thresholds[1].recall == 1.0
    assert report.thresholds[1].f1 == 1.0
