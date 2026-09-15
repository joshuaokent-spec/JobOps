# JobOps

**JobOps** is an evidence-grounded, human-in-the-loop job-search intelligence platform for discovering, ranking, preparing, and tracking job applications.

The project is intentionally designed as a portfolio-grade system spanning data engineering, data science, machine learning, agent orchestration, retrieval, local AI inference, API design, browser automation, and analytics.

## Core principles

- **Truth before fluency:** generated answers must be grounded in verified candidate facts.
- **Human approval before submission:** the system may prepare applications, but consequential submission stays behind an approval gate.
- **ML where prediction helps, LLMs where language helps:** ranking and outcome prediction are modeled separately from natural-language generation.
- **Local-first language inference:** candidate material and ambiguous UI classification can use an on-device Foundry Local model without coupling agents to a specific runtime.
- **Reproducible data pipelines:** ingest, normalize, deduplicate, score, and track jobs as structured data.
- **Auditable decisions:** every score, generated answer, verification finding, approval decision, browser mapping, ATS detection, and preparation step should be traceable.
- **Browser safety by construction:** browser inspection and preparation are separate from consequential submission.

## Current milestone: M3 — Browser Automation

M1 Job Intelligence and M2 Application Intelligence are complete. M3 now has a guarded Playwright browser abstraction, semantic form-field understanding, and two ATS-specific browser preparation adapters, with real-Chromium CI coverage across these boundaries.

JobOps can ingest supported ATS feeds, normalize and persist canonical postings, identify deterministic and semantic duplicate candidates, query/filter active jobs, and rank a filtered candidate pool with an explainable baseline scorer. It can select an evidence-grounded resume family, retrieve bounded verified candidate evidence, classify application questions by risk, draft Yellow-band narrative answers with a local or compatible LLM provider, audit generated claims against cited evidence, and persist explicit human approval decisions.

M3.1 can open employer/ATS pages in isolated Playwright contexts, inventory native form controls, and produce a typed dry-run structural plan. M3.2 maps those controls into application semantics such as contact data, resume/CV, professional links, salary, sponsorship, work authorization, narrative prompts, EEO/self-identification fields, and consent/attestation controls. Those mappings reuse the existing Green/Yellow/Red M2 policy and produce a second non-executing semantic preparation plan.

M3.3 adds a Greenhouse browser preparation adapter that can detect Greenhouse-hosted and embedded/iFrame application experiences, isolate the application form from unrelated careers-page controls, preserve Greenhouse job/source metadata when present, and route the selected form through the existing semantic mapper and review policy.

M3.4 adds the same vendor-specific preparation layer for Lever. It recognizes Lever posting/apply URL structure and verified Lever form actions, preserves account/site, posting UUID, `lever-source`, and `lever-origin` metadata, supports hosted and embedded forms, rejects generic `/apply` false positives, and preserves Red review for EEO, authorization, consent, and other consequential controls. Submit-capable controls remain blocked and no live form fill or application submission path exists yet.

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

### M2 capabilities implemented

- typed career evidence with provenance, verification state, metrics, role-family tags, skills, and retrieval-ready text;
- resume-family definitions over one master evidence base rather than duplicated factual resumes;
- verified-payload guardrails that block unknown, excluded, or unverified evidence;
- explainable resume-family selection with typed feature vectors, confidence/fallback behavior, and verified evidence pools;
- bounded evidence retrieval using lexical, skill, family, specificity, and optional semantic features;
- deterministic application-question classification with Green/Yellow/Red review routing;
- mandatory human review for legal/sensitive and unresolved application questions;
- provider-neutral typed LLM requests/responses and an `LLMProvider` protocol;
- OpenAI-compatible HTTP inference with Microsoft Foundry Local as the default development path;
- evidence-grounded narrative drafting that must cite supplied evidence IDs;
- rejection of unverified context, fabricated evidence IDs, malformed drafts, and invalid review routes;
- layered claim-level verification with deterministic vetoes for unsupported metrics, technologies, credentials, and other concrete evidence mismatches;
- optional semantic entailment review that may escalate to review but cannot override deterministic blockers;
- persistent PostgreSQL human approval queue with proposed, edited, and final answer separation;
- approval states for pending, approved, rejected, and revision-required content;
- idempotent identical review decisions and rejection of conflicting second decisions;
- explicit `approved_for_preparation` versus `submitted` separation;
- approval list/get/decision API endpoints with durable timestamps and audit metadata;
- mocked/fake model testing so CI remains model-download-free;
- sanitized public candidate evidence with no production PII.

### M3 capabilities implemented so far

- optional Playwright browser dependency rather than a mandatory base-runtime dependency;
- typed browser session, page, form, field, option, structural-plan, semantic-mapping, semantic-plan, and ATS-preparation contracts;
- isolated non-persistent browser contexts with service workers blocked by default;
- native form inventory for input, textarea, select, checkbox, radio, button, and file controls;
- label, accessible-name, required/disabled state, option, and stable-selector extraction;
- deterministic structural dry-run planning for fill/select/choose/upload/review/skip operations;
- submit-capable controls explicitly represented as `blocked_submit` rather than executable actions;
- dry-run blocking of `POST`, `PUT`, `PATCH`, and `DELETE` browser requests;
- post-load document-navigation blocking while the submission gate is closed;
- DOM guards for submit events, `form.submit()`, and `form.requestSubmit()`;
- guarded top-document plus child-frame form inspection for embedded ATS applications;
- deterministic semantic mapping for identity/contact fields, professional links, documents, preferences, legal/consequential fields, narrative prompts, demographics, consent/attestations, unknowns, and submit controls;
- explicit confidence, matched signals, and ambiguity handling rather than silent guesses;
- direct reuse of M2 `QuestionCategory`, `HandlingRoute`, and Green/Yellow/Red review policy inside browser automation;
- optional provider-neutral model-assisted classification only for unresolved controls;
- model-assisted mappings prevented from becoming Green autofill; ordinary assisted mappings stay Yellow and sensitive ones stay Red;
- semantic preparation planning that routes fields to verified fact resolution, draft-with-review, human review, escalation, or blocked submit without writing to the browser;
- Greenhouse context detection using URL, query, form, action, and field-name evidence with surfaced confidence and reasons;
- Greenhouse-hosted and embedded/iFrame application preparation support using controlled real-browser fixtures;
- isolation of Greenhouse application forms from unrelated careers-page search/decorative forms;
- preservation of `gh_jid`, `gh_src`, and board-token metadata when available;
- fail-closed rejection of generic non-Greenhouse forms by the Greenhouse adapter;
- Lever context detection using host, posting UUID, `/apply`, source/origin, verified form action, and recognizable candidate-control evidence;
- Lever-hosted and embedded/iFrame application preparation support using controlled real-browser fixtures;
- preservation of site/account token, posting UUID, `lever-source`, and `lever-origin` metadata when available;
- explicit rejection of generic external `/apply` forms and Lever posting pages without an application form;
- cross-ATS consent/attestation semantics routed Red to human review;
- LinkedIn browser navigation kept outside the ATS automation layer while LinkedIn profile URL remains a valid candidate data field;
- real headless Chromium tests against controlled application forms in GitHub Actions, including browser-snapshot-to-semantic-policy and ATS-specific integration.

See `docs/resume-evidence.md`, `docs/resume-family-selector.md`, `docs/evidence-retrieval.md`, `docs/question-classifier.md`, `docs/llm-providers.md`, `docs/narrative-drafting.md`, `docs/evidence-verifier.md`, `docs/approval-queue.md`, `docs/browser-dry-run.md`, `docs/semantic-form-mapping.md`, `docs/greenhouse-browser-adapter.md`, and `docs/lever-browser-adapter.md` for the current system contracts.

## Releases

### M1 — Job Intelligence — complete

- job-source adapters;
- normalized job schema;
- deterministic and semantic deduplication;
- baseline ranking;
- persistent PostgreSQL storage;
- query/ranking API views.

### M2 — Application Intelligence — complete

- candidate knowledge base;
- resume-family selection;
- evidence retrieval;
- question classification and routing;
- local/cloud-pluggable LLM provider boundary;
- evidence-grounded LLM drafts;
- claim-level answer verification;
- persistent human approval queue.

### M3 — Application Automation — in progress

- guarded Playwright abstraction — complete;
- semantic generic form-field detection and M2 policy mapping — complete;
- Greenhouse browser preparation adapter — complete;
- Lever browser preparation adapter — complete;
- Workday research/prototype — next;
- resume/document upload;
- application preparation;
- screenshot/audit artifacts;
- separate explicit final submit gate.

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
                                                     Narrative Draft Agent
                                                             |
                                                        LLMProvider
                                                   (Foundry Local default)
                                                             |
                                                             v
                                                    Claim-Level Verifier
                                                             |
                                                             v
                                                Persistent Approval Queue
                                                             |
                                                  APPROVED FOR PREPARATION
                                                             |
                                                             v
                                             Guarded Playwright Inspector
                                               /             \
                                       top document       child frames
                                               \             /
                                                             v
                                                Structural Form Snapshot
                                                             |
                                                             v
                                               Semantic Field Mapping
                                              /          |           \
                                    deterministic   model fallback   ambiguity
                                              \          |           /
                                                             v
                                                  M2 Review Policy
                                                             |
                                                             v
                                            Semantic Preparation Plan
                                                             |
                                                             v
                                      Greenhouse / Lever ATS Adapters
                                   (detect / isolate / preserve metadata)
                                                             |
                                                             X  no live fill/submit in M3.4
                                                             |
                                                             v
                                           Workday / Other Adapters
                                                             |
                                                   Explicit Submit Gate
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

## Browser dry-run development

Install the optional browser stack and Chromium only when working on M3 automation:

```bash
pip install -e ".[dev,browser]"
python -m playwright install chromium
```

M3.1 exposes guarded structural inspection. M3.2 adds deterministic-first semantic field understanding plus an optional local-model fallback for unresolved controls. M3.3 adds Greenhouse-specific detection, application-form isolation, metadata preservation, and embedded-frame support. M3.4 adds the parallel Lever preparation adapter plus a generic Red consent/attestation semantic. All of these layers reuse the generic browser and semantic-policy boundaries and produce non-executing plans: they do not fill or submit live applications. See `docs/browser-dry-run.md`, `docs/semantic-form-mapping.md`, `docs/greenhouse-browser-adapter.md`, and `docs/lever-browser-adapter.md` for the browser-policy contracts.

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

Canonical claims and generated resume wording are intentionally different concepts. Generated text may transform verified evidence, but it may not become a new candidate fact merely because a model wrote it.

## Approval workflow

Prepared answers enter the persistent approval queue before M3 may use them. The API exposes:

```text
POST /v1/approvals
GET  /v1/approvals
GET  /v1/approvals/{approval_id}
POST /v1/approvals/{approval_id}/decision
```

An approved item is **approved for preparation only**. The approval API intentionally has no application-submission endpoint, and approval responses keep `submitted=false`.

## Example API usage

```bash
curl http://127.0.0.1:8000/health
curl "http://127.0.0.1:8000/v1/jobs?work_mode=remote&min_salary=90000"
curl "http://127.0.0.1:8000/v1/approvals?status=pending"
```

`POST /v1/jobs/rank` accepts a candidate profile plus job filters, evaluates a bounded filtered candidate pool with the transparent baseline scorer, and returns jobs ordered by score.

## Repository layout

```text
src/jobops/
  agents/         narrative drafting, verification, orchestration interfaces
  api/            FastAPI health, jobs, scoring, ranking, and approval endpoints
  approvals/      human-review state machine
  browser/        guarded Playwright inspection, semantic mapping, ATS adapters, dry-run planning
  db/             PostgreSQL models, sessions, repositories, approval persistence
  embeddings/     pluggable semantic embedding providers
  ingestion/      ATS feed adapters, source config, refresh runner, and CLI
  knowledge/      TruthStore, resume evidence, retrieval, question policy
  llm/            provider-neutral language-model interfaces and HTTP adapters
  matching/       job scoring, resume-family selection, future learned rankers
  models/         typed domain/query/evidence/retrieval/LLM/browser/mapping/ATS/approval models
  normalization/  canonicalization plus deterministic/semantic deduplication

data/examples/    sanitized runnable sample data
data/evaluation/  labeled evaluation fixtures
docs/             architecture and engineering decisions
tests/            unit, integration, and controlled browser tests
```

## Safety and privacy

Do **not** commit production candidate data, credentials, API keys, browser cookies, recruiter correspondence, or legal-identification data. Use `.env`, private runtime configuration, and external databases/secrets managers for those values.

JobOps should never invent qualifications, certifications, work authorization, legal attestations, or other candidate facts. Unknown consequential questions must be escalated for human review. Language-model output cannot override deterministic review policy, blocked verification cannot be approved through the queue, approval cannot trigger final submission on its own, model-assisted browser mappings cannot become Green autofill decisions, ATS-specific detection cannot lower review requirements, consent/attestation controls cannot be answered automatically, and the current M3 browser layers cannot execute live application submission.

## Portfolio goal

This repository is meant to demonstrate an end-to-end intelligent system rather than a thin LLM wrapper: custom data pipelines, explainable baseline scoring, semantic ML, provenance-aware RAG, local/private inference, layered hallucination controls, human-in-the-loop state management, durable auditability, guarded browser automation, semantic UI understanding, reusable ATS-specific adaptation, iframe handling, source-attribution preservation, real-browser CI testing, observability, and analytics all live behind one product boundary.