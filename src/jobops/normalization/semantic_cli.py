import argparse
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from jobops.config import get_settings
from jobops.db import SqlAlchemyJobRepository, build_engine, build_session_factory
from jobops.embeddings.local import SentenceTransformerEmbeddingProvider
from jobops.models.query import JobSearchFilters
from jobops.normalization.semantic_deduplication import HybridDuplicateDetector
from jobops.normalization.semantic_evaluation import (
    LabeledDuplicatePair,
    evaluate_thresholds,
)

_DEFAULT_THRESHOLDS = [0.70, 0.75, 0.80, 0.84, 0.87, 0.90, 0.93, 0.95]


def _provider(model_name: str) -> SentenceTransformerEmbeddingProvider:
    return SentenceTransformerEmbeddingProvider(model_name=model_name)


def _scan(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = build_engine(settings.database_url)
    factory = build_session_factory(engine)
    provider = _provider(args.model)

    with factory() as session:
        repository = SqlAlchemyJobRepository(session)
        filters = JobSearchFilters(active=None if args.include_inactive else True)
        jobs = list(repository.search(filters, limit=args.limit, offset=0))

    detector = HybridDuplicateDetector(
        provider=provider,
        threshold=args.threshold,
        cross_source_only=not args.include_same_source,
    )
    result = detector.scan(jobs)
    print(result.model_dump_json(indent=2))
    return 0


def _load_examples(path: Path) -> list[LabeledDuplicatePair]:
    adapter = TypeAdapter(list[LabeledDuplicatePair])
    return adapter.validate_json(path.read_text(encoding="utf-8"))


def _parse_thresholds(value: str | None) -> list[float]:
    if value is None:
        return list(_DEFAULT_THRESHOLDS)
    values = [float(item.strip()) for item in value.split(",") if item.strip()]
    if not values:
        raise ValueError("at least one threshold is required")
    for threshold in values:
        if not -1.0 <= threshold <= 1.0:
            raise ValueError("thresholds must be between -1 and 1")
    return values


def _evaluate(args: argparse.Namespace) -> int:
    examples = _load_examples(Path(args.dataset))
    report = evaluate_thresholds(
        provider=_provider(args.model),
        examples=examples,
        thresholds=_parse_thresholds(args.thresholds),
    )
    print(report.model_dump_json(indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jobops-semantic-dedup",
        description=(
            "Scan JobOps postings for semantic duplicate candidates or evaluate thresholds."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Scan stored jobs for duplicate candidates.")
    scan.add_argument(
        "--model",
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="Sentence Transformers model name.",
    )
    scan.add_argument("--threshold", type=float, default=0.84)
    scan.add_argument("--limit", type=int, default=5000)
    scan.add_argument("--include-inactive", action="store_true")
    scan.add_argument("--include-same-source", action="store_true")
    scan.set_defaults(handler=_scan)

    evaluate = subparsers.add_parser(
        "evaluate",
        help="Evaluate similarity thresholds against a labeled JSON dataset.",
    )
    evaluate.add_argument("--dataset", required=True)
    evaluate.add_argument(
        "--model",
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="Sentence Transformers model name.",
    )
    evaluate.add_argument(
        "--thresholds",
        default=None,
        help="Comma-separated thresholds. Uses the built-in evaluation grid when omitted.",
    )
    evaluate.set_defaults(handler=_evaluate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        handler: Any = args.handler
        return int(handler(args))
    except (RuntimeError, ValueError, OSError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
