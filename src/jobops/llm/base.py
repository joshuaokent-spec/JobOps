from typing import Protocol

from jobops.models.llm import ChatRequest, ChatResponse, LLMProviderStatus


class LLMProvider(Protocol):
    provider_name: str
    model_name: str

    def complete(self, request: ChatRequest) -> ChatResponse: ...

    def probe(self) -> LLMProviderStatus: ...

    def list_models(self) -> list[str]: ...
