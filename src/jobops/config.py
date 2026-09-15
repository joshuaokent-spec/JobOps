from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "development"
    database_url: str = "postgresql+psycopg://jobops:jobops@localhost:5432/jobops"
    candidate_profile: str = "data/private/candidate.yaml"

    llm_provider: str = "foundry_local"
    llm_base_url: str = "http://127.0.0.1:39839/v1"
    llm_model: str = "qwen2.5-0.5b"
    llm_api_key: str | None = None
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    llm_max_tokens: int | None = Field(default=768, gt=0)
    llm_timeout_seconds: float = Field(default=60.0, gt=0.0)

    model_config = SettingsConfigDict(
        env_prefix="JOBOPS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
