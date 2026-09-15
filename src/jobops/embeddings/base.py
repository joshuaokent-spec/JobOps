from collections.abc import Sequence
from typing import Protocol


class EmbeddingProvider(Protocol):
    model_name: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...
