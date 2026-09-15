from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "development"
    database_url: str = "postgresql+psycopg://jobops:jobops@localhost:5432/jobops"
    candidate_profile: str = "data/private/candidate.yaml"

    model_config = SettingsConfigDict(
        env_prefix="JOBOPS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
