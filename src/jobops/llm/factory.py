from jobops.config import Settings, get_settings
from jobops.llm.base import LLMProvider
from jobops.llm.openai_compatible import OpenAICompatibleLLMProvider


def build_llm_provider(settings: Settings | None = None) -> LLMProvider:
    resolved = settings or get_settings()
    provider = resolved.llm_provider.strip().casefold()

    if provider == "foundry_local":
        return OpenAICompatibleLLMProvider(
            provider_name="foundry_local",
            base_url=resolved.llm_base_url,
            model_name=resolved.llm_model,
            api_key=resolved.llm_api_key,
            timeout_seconds=resolved.llm_timeout_seconds,
            status_path="/openai/status",
            models_path="/openai/models",
        )

    if provider == "openai_compatible":
        return OpenAICompatibleLLMProvider(
            provider_name="openai_compatible",
            base_url=resolved.llm_base_url,
            model_name=resolved.llm_model,
            api_key=resolved.llm_api_key,
            timeout_seconds=resolved.llm_timeout_seconds,
            models_path="/v1/models" if not resolved.llm_base_url.rstrip("/").endswith("/v1") else "/models",
        )

    raise ValueError(f"unsupported LLM provider: {resolved.llm_provider}")
