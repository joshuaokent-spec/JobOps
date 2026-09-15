import json

import httpx
import pytest

from jobops.config import Settings
from jobops.llm import LLMProviderError, OpenAICompatibleLLMProvider, build_llm_provider
from jobops.models.llm import ChatMessage, ChatRequest, ChatRole


def _chat_response(model: str = "local-model") -> dict[str, object]:
    return {
        "model": model,
        "choices": [
            {
                "message": {"role": "assistant", "content": "Grounded draft."},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 4,
            "total_tokens": 16,
        },
    }


def test_local_completion_uses_openai_contract_without_auth_header() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json=_chat_response("qwen-npu"),
            headers={"x-request-id": "req-local-1"},
        )

    provider = OpenAICompatibleLLMProvider(
        provider_name="foundry_local",
        base_url="http://127.0.0.1:39839/v1",
        model_name="qwen-npu",
        transport=httpx.MockTransport(handler),
    )
    response = provider.complete(
        ChatRequest(
            messages=[ChatMessage(role=ChatRole.USER, content="Draft a concise answer.")],
            temperature=0.1,
            max_tokens=120,
        )
    )

    assert captured["url"] == "http://127.0.0.1:39839/v1/chat/completions"
    assert captured["authorization"] is None
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "qwen-npu"
    assert body["temperature"] == 0.1
    assert body["max_tokens"] == 120
    assert response.content == "Grounded draft."
    assert response.provider == "foundry_local"
    assert response.model == "qwen-npu"
    assert response.finish_reason == "stop"
    assert response.request_id == "req-local-1"
    assert response.usage is not None
    assert response.usage.total_tokens == 16


def test_api_key_is_sent_only_when_configured() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret-test-key"
        return httpx.Response(200, json=_chat_response())

    provider = OpenAICompatibleLLMProvider(
        provider_name="openai_compatible",
        base_url="https://example.invalid/v1",
        model_name="example-model",
        api_key="secret-test-key",
        transport=httpx.MockTransport(handler),
    )
    provider.complete(
        ChatRequest(messages=[ChatMessage(role=ChatRole.USER, content="Hello")])
    )


def test_foundry_probe_uses_service_root_status_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://127.0.0.1:39839/openai/status"
        return httpx.Response(200, json={"Endpoints": ["http://127.0.0.1:39839"]})

    provider = OpenAICompatibleLLMProvider(
        provider_name="foundry_local",
        base_url="http://127.0.0.1:39839/v1",
        model_name="qwen-local",
        status_path="/openai/status",
        transport=httpx.MockTransport(handler),
    )

    status = provider.probe()
    assert status.available is True
    assert status.provider == "foundry_local"


def test_foundry_model_listing_supports_string_array() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://127.0.0.1:39839/openai/models"
        return httpx.Response(200, json=["qwen-npu", "phi-local"])

    provider = OpenAICompatibleLLMProvider(
        provider_name="foundry_local",
        base_url="http://127.0.0.1:39839/v1",
        model_name="qwen-npu",
        models_path="/openai/models",
        transport=httpx.MockTransport(handler),
    )

    assert provider.list_models() == ["phi-local", "qwen-npu"]


def test_standard_model_listing_supports_openai_data_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"id": "model-b"}, {"id": "model-a"}]},
        )

    provider = OpenAICompatibleLLMProvider(
        provider_name="openai_compatible",
        base_url="https://example.invalid/v1",
        model_name="model-a",
        models_path="/v1/models",
        transport=httpx.MockTransport(handler),
    )

    assert provider.list_models() == ["model-a", "model-b"]


def test_provider_failure_does_not_echo_response_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            text="private candidate application content must not be surfaced",
        )

    provider = OpenAICompatibleLLMProvider(
        provider_name="foundry_local",
        base_url="http://127.0.0.1:39839/v1",
        model_name="qwen-local",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LLMProviderError) as exc_info:
        provider.complete(
            ChatRequest(messages=[ChatMessage(role=ChatRole.USER, content="Private prompt")])
        )
    message = str(exc_info.value)
    assert "HTTP 500" in message
    assert "private candidate" not in message


def test_malformed_completion_response_is_rejected() -> None:
    provider = OpenAICompatibleLLMProvider(
        provider_name="foundry_local",
        base_url="http://127.0.0.1:39839/v1",
        model_name="qwen-local",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"choices": []})
        ),
    )

    with pytest.raises(LLMProviderError, match="did not contain any choices"):
        provider.complete(
            ChatRequest(messages=[ChatMessage(role=ChatRole.USER, content="Hello")])
        )


def test_factory_builds_foundry_local_with_diagnostic_paths() -> None:
    settings = Settings(
        llm_provider="foundry_local",
        llm_base_url="http://127.0.0.1:39839/v1",
        llm_model="qwen2.5-0.5b",
        llm_api_key=None,
    )
    provider = build_llm_provider(settings)

    assert isinstance(provider, OpenAICompatibleLLMProvider)
    assert provider.provider_name == "foundry_local"
    assert provider.model_name == "qwen2.5-0.5b"
    assert provider.status_path == "/openai/status"
    assert provider.models_path == "/openai/models"


def test_factory_rejects_unknown_provider() -> None:
    settings = Settings(llm_provider="mystery-provider")
    with pytest.raises(ValueError, match="unsupported LLM provider"):
        build_llm_provider(settings)
