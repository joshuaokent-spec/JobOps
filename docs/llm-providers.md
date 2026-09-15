# LLM providers and Foundry Local

JobOps keeps language-model inference behind a provider-neutral `LLMProvider` boundary. Deterministic policy, `TruthStore` resolution, question-risk routing, evidence selection, and submission approval remain outside the model.

## Why Foundry Local is the default development provider

A local model is a strong fit for application material because resume evidence and draft answers can remain on the candidate's machine. JobOps talks to Foundry Local through its OpenAI-compatible REST surface rather than importing the hardware runtime into the application process.

This keeps the core application:

- portable across local and hosted OpenAI-compatible endpoints;
- independent of a particular NPU/GPU runtime SDK;
- model-download-free in CI;
- easy to mock in unit tests;
- able to keep candidate text local during inference.

## Recommended local setup

Install and verify Foundry Local using Microsoft's current CLI instructions. For predictable JobOps configuration, run the local server on a fixed port:

```powershell
foundry server start --port 39839 --idle-timeout 0
foundry server status
```

If the server was already running on another port:

```powershell
foundry server restart --port 39839 --idle-timeout 0
```

Use a model alias when selecting/loading a model so Foundry can choose the best available hardware variant:

```powershell
foundry model list --filter task=chat-completion
foundry model info qwen2.5-0.5b
foundry model load qwen2.5-0.5b
```

An alias is useful at the CLI layer because Foundry resolves it to a hardware-specific model variant. The REST chat-completions API identifies the specific model used for the request. If the alias is not accepted by the running service, set `JOBOPS_LLM_MODEL` to the loaded model ID shown by Foundry rather than forcing a CPU/GPU/NPU suffix in JobOps code.

## JobOps configuration

Copy `.env.example` to `.env` and keep the local provider configuration similar to:

```env
JOBOPS_LLM_PROVIDER=foundry_local
JOBOPS_LLM_BASE_URL=http://127.0.0.1:39839/v1
JOBOPS_LLM_MODEL=qwen2.5-0.5b
JOBOPS_LLM_API_KEY=
JOBOPS_LLM_TEMPERATURE=0.2
JOBOPS_LLM_MAX_TOKENS=768
JOBOPS_LLM_TIMEOUT_SECONDS=60
```

Foundry Local does not require an API key for local use, so JobOps omits the Authorization header when `JOBOPS_LLM_API_KEY` is empty.

## Provider contract

Downstream agents depend only on:

```python
class LLMProvider(Protocol):
    provider_name: str
    model_name: str

    def complete(self, request: ChatRequest) -> ChatResponse: ...
    def probe(self) -> LLMProviderStatus: ...
    def list_models(self) -> list[str]: ...
```

`OpenAICompatibleLLMProvider` sends generation requests to:

```text
POST <base_url>/chat/completions
```

For the default Foundry URL, that becomes:

```text
POST http://127.0.0.1:39839/v1/chat/completions
```

The Foundry configuration also uses its service diagnostics:

```text
GET /openai/status
GET /openai/models
```

Those paths remain provider configuration; drafting agents never contain Foundry-specific branches.

## What the local model should and should not control

Good uses for the model include:

- drafting Yellow-band narrative answers from retrieved verified evidence;
- rewriting evidence-grounded resume bullets without adding qualifications;
- extracting structured information from job/application text;
- summarizing employer or role research;
- proposing wording for human review;
- later, assisting an evidence verifier as one signal among deterministic checks.

The model must not decide whether a legal/sensitive answer may be submitted, change `TruthStore` facts, bypass a Red review route, invent qualifications, or trigger final submission by itself.

## Model sizing strategy

A very small model is useful for plumbing tests, extraction, short classification tasks, and validating the local NPU path. Narrative application answers and resume rewriting generally benefit from a stronger local model. Because JobOps selects the provider/model through configuration, moving from a small smoke-test model to a larger NPU-capable model does not require changes to the drafting agent.

## Offline and privacy behavior

Once the model and required runtime components are cached, local inference can continue without a cloud inference dependency. JobOps should treat provider unavailability as an explicit runtime condition and never silently send candidate content to a cloud fallback. A future cloud fallback must be separately configured and intentionally enabled.

## CI strategy

GitHub Actions does not run a Foundry model. Provider tests use `httpx.MockTransport` to validate:

- request and response schemas;
- optional Authorization behavior;
- Foundry diagnostic URL construction;
- model-list parsing;
- token metadata;
- malformed responses;
- sanitized provider failures.

This keeps CI deterministic while the same production adapter talks to the actual local NPU service on the user's machine.
