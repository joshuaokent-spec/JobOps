import argparse
import json
from pathlib import Path

from pydantic import TypeAdapter

from jobops.learning.dataset_builder import (
    RankingTrainingDatasetBuilder,
    write_training_dataset,
)
from jobops.models.feedback import FeedbackEvent
from jobops.models.training_dataset import RankingDecisionPoint, TrainingDatasetSpec

_POINTS = TypeAdapter(list[RankingDecisionPoint])
_EVENTS = TypeAdapter(list[FeedbackEvent])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jobops-build-dataset",
        description="Build a leakage-resistant ranking dataset from explicit snapshots and events.",
    )
    parser.add_argument("--points", required=True, type=Path)
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--spec", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    points = _POINTS.validate_json(args.points.read_text(encoding="utf-8"))
    events = _EVENTS.validate_json(args.events.read_text(encoding="utf-8"))

    spec = TrainingDatasetSpec()
    if args.spec is not None:
        spec = TrainingDatasetSpec.model_validate_json(
            args.spec.read_text(encoding="utf-8")
        )

    result = RankingTrainingDatasetBuilder().build(points, events, spec)
    rows_path, manifest_path = write_training_dataset(result, args.output)

    print(
        json.dumps(
            {
                "rows_path": str(rows_path),
                "manifest_path": str(manifest_path),
                "dataset_fingerprint": result.manifest.dataset_fingerprint,
                "model_ready_rows": result.manifest.model_ready_row_count,
                "class_counts": result.manifest.class_counts,
                "split_counts": result.manifest.split_counts,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
