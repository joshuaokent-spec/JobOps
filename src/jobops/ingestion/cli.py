import argparse
import asyncio
import json
import logging

from jobops.config import get_settings
from jobops.db import build_engine, build_session_factory
from jobops.ingestion.config import build_adapter, load_ingestion_config
from jobops.ingestion.runner import IngestionRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refresh configured JobOps job sources",
    )
    parser.add_argument(
        "--config",
        required=True,
        help="YAML source configuration",
    )
    return parser


async def _run(config_path: str) -> int:
    config = load_ingestion_config(config_path)
    adapters = [build_adapter(source) for source in config.sources]
    engine = build_engine(get_settings().database_url)
    runner = IngestionRunner(build_session_factory(engine))
    metrics = await runner.run(adapters)
    print(json.dumps(metrics.model_dump(mode="json"), sort_keys=True))
    return 1 if metrics.sources_failed else 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(_run(args.config)))
