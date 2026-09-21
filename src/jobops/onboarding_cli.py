import argparse
import json
from pathlib import Path

import yaml
from pydantic import ValidationError

from jobops.config import get_settings
from jobops.db import build_engine, build_session_factory
from jobops.db.onboarding_repository import SqlAlchemyCandidateOnboardingRepository
from jobops.db.search_profile_repository import SqlAlchemySearchProfileRepository
from jobops.models.onboarding import CandidateOnboardingPayload
from jobops.models.search_profile import SearchProfile


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


def _read_mapping(path: str | Path) -> dict[str, object]:
    resolved = Path(path)
    raw = resolved.read_text(encoding="utf-8")
    if resolved.suffix.casefold() == ".json":
        payload = json.loads(raw)
    else:
        payload = yaml.safe_load(raw)
    if not isinstance(payload, dict):
        raise ValueError("onboarding config must be an object")
    return payload


def load_payload(path: str | Path) -> CandidateOnboardingPayload:
    payload = _read_mapping(path)
    if "onboarding" in payload:
        nested = payload["onboarding"]
        if not isinstance(nested, dict):
            raise ValueError("onboarding field must be an object")
        payload = nested
    return CandidateOnboardingPayload.model_validate(payload)


def load_search_profiles(path: str | Path) -> list[SearchProfile]:
    payload = _read_mapping(path)
    raw_profiles = payload.get("search_profiles", [])
    if raw_profiles is None:
        return []
    if not isinstance(raw_profiles, list):
        raise ValueError("search_profiles must be a list")
    onboarding = load_payload(path)
    profiles = [SearchProfile.model_validate(item) for item in raw_profiles]
    wrong_owner = [
        profile.profile_id
        for profile in profiles
        if profile.candidate_id != onboarding.candidate.candidate_id
    ]
    if wrong_owner:
        raise ValueError(
            f"search profiles do not match onboarding owner: {sorted(wrong_owner)}"
        )
    return profiles


def _run(config_path: str) -> int:
    try:
        payload = load_payload(config_path)
        search_profiles = load_search_profiles(config_path)
    except (
        OSError,
        json.JSONDecodeError,
        yaml.YAMLError,
        ValidationError,
        ValueError,
    ) as exc:
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
        profile_repo = SqlAlchemySearchProfileRepository(session)
        for profile in search_profiles:
            profile_repo.save(profile)
        session.commit()
        status = repo.status(saved.candidate.candidate_id)
        output = status.model_dump(mode="json")
        output["search_profile_ids"] = [
            profile.profile_id for profile in search_profiles
        ]
        print(json.dumps(output, sort_keys=True))
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
