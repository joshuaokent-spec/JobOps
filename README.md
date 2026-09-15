# JobOps

**JobOps** is an evidence-grounded, human-in-the-loop job-search intelligence platform for discovering, ranking, preparing, and tracking job applications.

The project is intentionally designed as a portfolio-grade system spanning data engineering, data science, machine learning, agent orchestration, retrieval, local AI inference, API design, browser automation, and analytics.

## Core principles

- **Truth before fluency:** generated answers must be grounded in verified candidate facts.
- **Human approval before submission:** the system may prepare applications, but consequential submission stays behind an approval gate.
- **ML where prediction helps, LLMs where language helps:** ranking and outcome prediction are modeled separately from natural-language generation.
- **Local-first language inference:** candidate material can be drafted through an on-device Foundry Local model without coupling agents to a specific model runtime.
- **Reproducible data pipelines:** ingest, normalize, deduplicate, score, and track jobs as structured data.
- **Auditable decisions:** every score and generated answer should be explainable from stored evidence.

## Current milestone: M2 — Application Intelligence

M1 Job Intelligence is complete. JobOps can ingest supported ATS feeds, normalize and persist canonical postings, identify deterministic and semantic duplicate candidates, query/filter active jobs, and rank a filtered candidate pool with the explainable baseline scorer.

M2 now has five foundations in place: a provenance-aware master resume evidence model, an explainable resume-family selector, bounded job-specific evidence retrieval, risk-aware application-question routing, and a provider-neutral LLM boundary with Microsoft Foundry Local support. The system can determine which verified evidence may enter a language-model prompt without giving the model authority over candidate facts or review policy.

### M1 capabilities implemented

- Greenhouse and Lever public-feed adapters;
- canonical normalization with stable source identities and audit metadata;
- deterministic cross-source duplicate fingerprints;
- embedding-assisted semantic near-duplicate detection with a pluggable provider interface;
- labeled threshold evaluation with precision, recall, F1, and confusion counts;
- PostgreSQL persistence with Alembic migrations;
- paginated job search/filter API;
- baseline candidate-specific job ranking;
- idempotent source refresh with stale-posting deactivation;
- JSON ingestion metrics and scheduler-friendly CLI execution.

### M2 capabilities implemented so far

- typed career evidence with provenance, verification state, metrics, role-family tags, skills, and retrieval-ready text;
- resume-family definitions over one master evidence base rather than duplicated factual resumes;
- verified-payload guardrails that block unknown, excluded, or unverified evidence;
- explainable resume-family selection with typed feature vectors, confidence/fallback behavior, and verified evidence pools;
- bounded evidence retrieval using lexical, skill, family, and specificity features;
- optional semantic retrieval through the same pluggable embedding interface used by M1;
- evidence-kind diversity and stable ranking;
- preservation of original evidence IDs and source references through retrieval;
- deterministic application-question classification with Green/Yellow/Red review routing;
- mandatory human review for legal/sensitive and unresolved application questions;
- provider-neutral typed LLM requests/responses and an `LLMProvider` protocol;
- OpenAI-compatible HTTP inference with no mandatory vendor SDK;
- local-first Microsoft Foundry Local configuration, status/model probing, and optional API-key handling;
- mocked provider integration tests that keep CI model-download-free;
- sanitized public candidate evidence with no production PII.

See `docs/resume-evidence.md`, `docs/resume-family-selector.md`, `docs/evidence-retrieval.md`, `docs/question-classifier.md`, and `docs/llm-providers.md` for the candidate-knowledge, policy, retrieval, and inference contracts.

## Planned releases

### M1 — Job Intelligence — complete

- job-source adapters;
- normalized job schema;
- deterministic and semantic deduplication;
- baseline ranking;
- persistent PostgreSQL storage;
- query/ranking API views.

### M2 — Application Intelligence

- candidate knowledge base;
- resume-family selection;
- evidence retrieval;
- question classification and routing;
- local/cloud-pluggable LLM provider boundary;
- LLM-generated drafts;
- answer verification;
- approval queue.

### M3 — Application Automation

- Playwright ATS adapters;
- form-field classification;
- resume upload;
- application preparation;
- mandatory review before submit.

### M4 — Learning System

- user-feedback labels;
- learned ranking model;
- resume-selection model;
- application-outcome analytics;
- interview/callback prediction;
- model evaluation and experiment tracking.

## Architecture

```text
Job Sources
    |
    v
Ingestion -> Normalization -> Deterministic + Semantic Deduplication -> Job Store
                                                                  |
                                                                  v
Candidate Profile -> TruthStore ---------------------------+
                                                             |
Resume Evidence -> ResumeEvidenceStore -> Family Selector --+--> Evidence Retrieval
                                                             |          |
Application Question -> Risk/Review Classifier --------------+          |
                                                             |          v
                                                             |   bounded verified context
                                                             |          |
                                                             v          v
                                                     Application Orchestrator
                                                      /        |         \
                                                     v         v          v
                                               Resume Agent  Q&A Agent  Verifier
                                                      \        |         /
                                                       \       v        /
                                                        LLMProvider
                                                   (Foundry Local by default)
                                                             |
                                                             v
                                                       Approval Queue
                                                             |
                                                             v
                                                       Browser Adapter
                                                             |
                                                             v
                                                  Application Tracking
                                                             |
                                                             v
                                                  Analytics / ML Feedback
```

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e ".[dev]"
pytest
uvicorn jobops.api.main:app --reload
```

Then open `http://127.0.0.1:8000/docs`.

Initialize or upgrade PostgreSQL with:

```bash
docker compose up -d postgres
alembic upgrade head
```

## Local LLM inference

JobOps defaults to a Foundry Local-compatible endpoint in `.env.example`:

```env
JOBOPS_LLM_PROVIDER=foundry_local
JOBOPS_LLM_BASE_URL=http://127.0.0.1:39839/v1
JOBOPS_LLM_MODEL=qwen2.5-0.5b
JOBOPS_LLM_API_KEY=
```

For a predictable local endpoint during development:

```powershell
foundry server start --port 39839 --idle-timeout 0
foundry model load qwen2.5-0.5b
foundry server status
```

Use the model alias at the Foundry CLI layer to select the best local hardware variant. If the REST service requires the concrete loaded model ID, set `JOBOPS_LLM_MODEL` to that value in your private `.env`.

See `docs/llm-providers.md` for provider configuration and the local-inference safety boundary.

## Job ingestion

```bash
cp data/examples/sources.example.yaml data/private/sources.yaml
jobops-ingest --config data/private/sources.yaml
```

Each source refresh is transactional. A failed fetch does not deactivate previously stored jobs; stale postings are marked inactive only after a successful refresh of the same source scope.

## Semantic duplicate detection

Install optional local ML dependencies only when semantic embeddings are needed:

```bash
pip install -e ".[ml]"
```

```bash
jobops-semantic-dedup scan --threshold 0.84
jobops-semantic-dedup evaluate \
  --dataset data/evaluation/semantic-duplicate-pairs.example.json
```

## Candidate evidence

A sanitized master-evidence example lives at:

```text
data/examples/resume-evidence.example.yaml
```

Canonical claims and generated resume wording are intentionally different concepts. Generated text may later transform verified evidence, but it may not become a new candidate fact merely because a model wrote it.

## Example API usage

```bash
curl http://127.0.0.1:8000/health
curl "http://127.0.0.1:8000/v1/jobs?work_mode=remote&min_salary=90000"
```

`POST /v1/jobs/rank` accepts a candidate profile plus job filters, evaluates a bounded filtered candidate pool with the transparent baseline scorer, and returns jobs ordered by score.

## Repository layout

```text
src/jobops/
  agents/         orchestration interfaces and future specialized agents
  api/            FastAPI health, scoring, job-query, and ranking endpoints
  db/             persistence models, sessions, and repository interfaces
  embeddings/     pluggable semantic embedding providers
  ingestion/      ATS adapters, source config, refresh runner, and CLI
  knowledge/      TruthStore, resume evidence, retrieval, question policy
  llm/            provider-neutral language-model interfaces and HTTP adapters
  matching/       job scoring, resume-family selection, future learned rankers
  models/         typed domain/query/evidence/retrieval/LLM models
  normalization/  canonicalization plus deterministic/semantic deduplication

data/examples/    sanitized runnable sample data
data/evaluation/  labeled evaluation fixtures
docs/             architecture and engineering decisions
tests/            unit and integration tests
```

## Safety and privacy

Do **not** commit production candidate data, credentials, API keys, browser cookies, recruiter correspondence, or legal-identification data. Use `.env`, private runtime configuration, and external databases/secrets managers for those values.

JobOps should never invent qualifications, certifications, work authorization, legal attestations, or other candidate facts. Unknown consequential questions must be escalated for human review. Language-model output cannot override deterministic review policy or trigger final submission on its own.

## Portfolio goal

This repository is meant to demonstrate an end-to-end intelligent system rather than a thin LLM wrapper: custom data pipelines, explainable baseline scoring, semantic ML, learned models, provenance-aware RAG, local/private inference, agent tooling, browser automation, testing, observability, and analytics all live behind one product boundary.
