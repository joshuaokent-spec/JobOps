import argparse
import json
from pathlib import Path

import yaml
from pydantic import ValidationError

from jobops.config import get_settings
from jobops.db import build_engine, build_session_factory
from jobops.db.onboarding_repository import SqlAlchemyCandidateOnboardingRepository
from jobops.models.onboarding import CandidateOnboardingPayload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import private candidate/resume onboarding into JobOps",
    )
    parser.add_argument(
        "--config",
        required=True,
        help="JSON or YAML CandidateOnboardingPayload file",
    )
    return parser


def load_payload(path: str | Path) -> CandidateOnboardingPayload:
    resolved = Path(path)
    raw = resolved.read_text(encoding="utf-8")
    if resolved.suffix.casefold() == ".json":
        payload = json.loads(raw)
    else:
        payload = yaml.safe_load(raw)
    if not isinstance(payload, dict):
        raise ValueError("onboarding config must be an object")
    return CandidateOnboardingPayload.model_validate(payload)


def _run(config_path: str) -> int:
    try:
        payload = load_payload(config_path)
    except (OSError, json.JSONDecodeError, yaml.YAMLError, ValidationError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "invalid",
                    "error": f"{type(exc).__name__}: onboarding config is invalid",
                },
                sort_keys=True,
            )
        )
        return 1

    settings = get_settings()
    engine = build_engine(settings.database_url)
    session = build_session_factory(engine)()
    try:
        repo = SqlAlchemyCandidateOnboardingRepository(session)
        saved = repo.save(payload)
        session.commit()
        status = repo.status(saved.candidate.candidate_id)
        print(json.dumps(status.model_dump(mode="json"), sort_keys=True))
        return 0 if status.ready_to_run else 2
    except Exception as exc:
        session.rollback()
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": f"{type(exc).__name__}: onboarding import failed",
                },
                sort_keys=True,
            )
        )
        return 1
    finally:
        session.close()


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(_run(args.config))
