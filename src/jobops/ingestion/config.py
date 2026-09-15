from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, Field

from jobops.ingestion.base import JobSourceAdapter
from jobops.ingestion.greenhouse import GreenhouseAdapter
from jobops.ingestion.lever import LeverAdapter


class GreenhouseSourceConfig(BaseModel):
    kind: Literal["greenhouse"]
    board_token: str = Field(min_length=1)
    company: str = Field(min_length=1)


class LeverSourceConfig(BaseModel):
    kind: Literal["lever"]
    site: str = Field(min_length=1)
    company: str = Field(min_length=1)


type SourceConfig = Annotated[
    GreenhouseSourceConfig | LeverSourceConfig,
    Field(discriminator="kind"),
]


class IngestionConfig(BaseModel):
    sources: list[SourceConfig] = Field(min_length=1)


def load_ingestion_config(path: str | Path) -> IngestionConfig:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("ingestion config must be a mapping")
    return IngestionConfig.model_validate(payload)


def build_adapter(config: SourceConfig) -> JobSourceAdapter:
    if isinstance(config, GreenhouseSourceConfig):
        return GreenhouseAdapter(config.board_token, config.company)
    return LeverAdapter(config.site, config.company)
