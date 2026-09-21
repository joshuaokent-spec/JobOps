import argparse
import asyncio
import json

from jobops.config import get_settings
from jobops.db import build_engine, build_session_factory
from jobops.discovery.factory import build_discovery_providers
from jobops.flagship.schedule import DailyFlagshipRunner, PrivateFlagshipRunInputStore
from jobops.models.flagship_schedule import ScheduledFlagshipBatchResult


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run all active JobOps Flagship search profiles once",
    )
    parser.add_argument(
        "--input-dir",
        default="data/private/flagship-runs",
        help=(
            "Gitignored directory containing <profile_id>.json/.yaml FlagshipRunRequest "
            "files"
        ),
    )
    return parser


async def _run(input_dir: str) -> int:
    settings = get_settings()
    engine = build_engine(settings.database_url)
    runner = DailyFlagshipRunner(
        build_session_factory(engine),
        build_discovery_providers(settings),
        PrivateFlagshipRunInputStore(input_dir),
        discovery_timeout_seconds=settings.discovery_timeout_seconds,
    )
    result = await runner.run()
    print(json.dumps(result.model_dump(mode="json"), sort_keys=True))

    return _exit_code(result)


def _exit_code(result: ScheduledFlagshipBatchResult) -> int:
    if result.profiles_failed:
        return 1
    if result.profiles_skipped:
        return 2
    return 0


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(_run(args.input_dir)))
