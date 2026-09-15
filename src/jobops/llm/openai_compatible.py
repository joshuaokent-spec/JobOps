from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from jobops.models.llm import (
    ChatRequest,
    ChatResponse,
    LLMProviderStatus,
    TokenUsage,
)


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider request fails or returns an invalid payload."""


class OpenAICompatibleLLMProvider:
    """Chat-completion provider for OpenAI-compatible HTTP endpoints.

    Foundry Local uses this provider with Foundry-specific diagnostic paths while
    generation remains on the standard ``/v1/chat/completions`` endpoint.
    """

    def __init__(
        self,
        *,
        provider_name: str,
        base_url: str,
        model_name: str,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
        status_path: str | None = None,
        models_path: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not provider_name.strip():
            raise ValueError("provider_name cannot be blank")
        if not model_name.strip():
            raise ValueError("model_name cannot be blank")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self.provider_name = provider_name.strip()
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name.strip()
        self.api_key = api_key or None
        self.timeout_seconds = timeout_seconds
        self.status_path = status_path
        self.models_path = models_path
        self.transport = transport
        self._validate_base_url()

    def complete(self, request: ChatRequest) -> ChatResponse:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [message.model_dump(mode="json") for message in request.messages],
            "temperature": request.temperature,
        }
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        response = self._request("POST", f"{self.base_url}/chat/completions", json=payload)
        data = self._json_object(response)
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMProviderError("LLM response did not contain any choices")

        first = choices[0]
        if not isinstance(first, Mapping):
            raise LLMProviderError("LLM response choice had an unexpected shape")
        message = first.get("message")
        if not isinstance(message, Mapping):
            raise LLMProviderError("LLM response did not contain an assistant message")
        content = message.get("content")
        if not isinstance(content, str):
            raise LLMProviderError("LLM response assistant content was not text")

        model = data.get("model")
        response_model = model if isinstance(model, str) and model else self.model_name
        finish_reason = first.get("finish_reason")
        usage = self._usage(data.get("usage"))
        return ChatResponse(
            content=content,
            provider=self.provider_name,
            model=response_model,
            finish_reason=finish_reason if isinstance(finish_reason, str) else None,
            usage=usage,
            request_id=response.headers.get("x-request-id"),
        )

    def probe(self) -> LLMProviderStatus:
        if self.status_path is None:
            return LLMProviderStatus(
                provider=self.provider_name,
                model=self.model_name,
                available=False,
                detail="No provider status endpoint is configured.",
            )

        try:
            response = self._request("GET", self._service_url(self.status_path))
        except LLMProviderError as exc:
            return LLMProviderStatus(
                provider=self.provider_name,
                model=self.model_name,
                available=False,
                detail=str(exc),
            )
        return LLMProviderStatus(
            provider=self.provider_name,
            model=self.model_name,
            available=True,
            detail=f"Provider status endpoint returned HTTP {response.status_code}.",
        )

    def list_models(self) -> list[str]:
        if self.models_path is None:
            return []
        response = self._request("GET", self._service_url(self.models_path))
        payload = self._json_value(response)

        if isinstance(payload, list):
            return sorted(str(item) for item in payload if isinstance(item, str))
        if isinstance(payload, Mapping):
            data = payload.get("data")
            if isinstance(data, list):
                model_ids = [
                    item.get("id")
                    for item in data
                    if isinstance(item, Mapping) and isinstance(item.get("id"), str)
                ]
                return sorted(model_ids)
        raise LLMProviderError("Model-list endpoint returned an unexpected payload")

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                transport=self.transport,
                headers=headers,
            ) as client:
                response = client.request(method, url, **kwargs)
                response.raise_for_status()
                return response
        except httpx.HTTPStatusError as exc:
            raise LLMProviderError(
                f"{self.provider_name} returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(
                f"{self.provider_name} request failed: {type(exc).__name__}"
            ) from exc

    def _service_url(self, path: str) -> str:
        split = urlsplit(self.base_url)
        base_path = split.path.rstrip("/")
        if base_path.endswith("/v1"):
            base_path = base_path[:-3]
        full_path = f"{base_path}/{path.lstrip('/')}"
        return urlunsplit((split.scheme, split.netloc, full_path, "", ""))

    def _validate_base_url(self) -> None:
        split = urlsplit(self.base_url)
        if split.scheme not in {"http", "https"} or not split.netloc:
            raise ValueError("base_url must be an absolute HTTP(S) URL")

    @staticmethod
    def _json_value(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise LLMProviderError("LLM provider returned invalid JSON") from exc

    @classmethod
    def _json_object(cls, response: httpx.Response) -> Mapping[str, Any]:
        payload = cls._json_value(response)
        if not isinstance(payload, Mapping):
            raise LLMProviderError("LLM provider returned an unexpected JSON payload")
        return payload

    @staticmethod
    def _usage(value: Any) -> TokenUsage | None:
        if not isinstance(value, Mapping):
            return None
        return TokenUsage(
            prompt_tokens=_nonnegative_int(value.get("prompt_tokens")),
            completion_tokens=_nonnegative_int(value.get("completion_tokens")),
            total_tokens=_nonnegative_int(value.get("total_tokens")),
        )


def _nonnegative_int(value: Any) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None
