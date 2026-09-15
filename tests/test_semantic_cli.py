from pathlib import Path

import pytest

from jobops.normalization.semantic_cli import _load_examples, _parse_thresholds, build_parser


def test_example_evaluation_dataset_loads() -> None:
    path = Path("data/evaluation/semantic-duplicate-pairs.example.json")
    examples = _load_examples(path)

    assert len(examples) == 6
    assert sum(example.duplicate for example in examples) == 3
    assert {example.left.source for example in examples} == {"greenhouse"}
    assert {example.right.source for example in examples} == {"lever"}


def test_threshold_parser_uses_default_grid() -> None:
    thresholds = _parse_thresholds(None)
    assert 0.84 in thresholds
    assert thresholds == sorted(thresholds)


def test_threshold_parser_rejects_out_of_range_value() -> None:
    with pytest.raises(ValueError, match="between -1 and 1"):
        _parse_thresholds("0.8,1.1")


def test_scan_parser_defaults_to_safe_cross_source_mode() -> None:
    args = build_parser().parse_args(["scan"])
    assert args.threshold == 0.84
    assert args.include_same_source is False
    assert args.include_inactive is False
