# JobOps

**JobOps** is an evidence-grounded, human-in-the-loop job-search intelligence platform for discovering, ranking, preparing, auditing, and tracking job applications.

The project is intentionally designed as a portfolio-grade system spanning data engineering, data science, machine learning, agent orchestration, retrieval, local AI inference, API design, browser automation, privacy engineering, and analytics.

## Core principles

- **Truth before fluency:** generated answers must be grounded in verified candidate facts.
- **Human approval before submission:** preparation and consequential submission are separate capabilities.
- **ML where prediction helps, LLMs where language helps:** ranking and outcome prediction are modeled separately from natural-language generation.
- **Local-first language inference:** candidate material and ambiguous UI classification can use an on-device Foundry Local model without coupling agents to one runtime.
- **Reproducible data pipelines:** ingest, normalize, deduplicate, score, and track jobs as structured data.
- **Auditable decisions:** scores, drafts, verification findings, approvals, browser mappings, ATS detection, workflow state, blocked actions, and audit artifacts are traceable.
- **Browser safety by construction:** browser inspection, preparation, audit capture, and final submission remain distinct trust boundaries.
- **Privacy by minimization:** browser audit artifacts preserve the evidence needed to explain a decision without becoming a candidate-answer or credential archive.

## Current milestone: Flagship v1 — Working Job Search + Application Product

M1 Job Intelligence, M2 Application Intelligence, and M3 Browser Automation are complete. The project is now refocused on the Flagship product: a user supplies a verified candidate/resume evidence base plus explicit search criteria, and JobOps discovers matching jobs, enforces hard constraints, ranks the survivors, prepares applications, surfaces only review-required exceptions, submits through supported ATS paths behind the existing one-shot authorization gate, and tracks outcomes.

M3 already provides the guarded Playwright/browser foundation, semantic field understanding, Greenhouse and Lever adapters, stateful Workday modeling, privacy-safe audit bundles, and explicit final-submit authorization needed by the Flagship.

JobOps can ingest supported ATS feeds, normalize and persist canonical postings, identify deterministic and semantic duplicate candidates, query/filter active jobs, and rank a filtered candidate pool with an explainable baseline scorer. It can select an evidence-grounded resume family, retrieve bounded verified candidate evidence, classify application questions by risk, draft Yellow-band narrative answers with a local or compatible LLM provider, audit generated claims against cited evidence, and persist explicit human approval decisions.

M3 is deliberately incremental:

- **M3.1 — Guarded browser inspection:** isolated Playwright contexts, structural form inventory, blocked mutation requests, and non-executing dry-run plans.
- **M3.2 — Semantic field understanding:** deterministic-first mapping into application semantics with Green/Yellow/Red policy reuse and optional model assistance only for unresolved controls.
- **M3.3 — Greenhouse:** hosted/embedded application detection, application-form isolation, metadata preservation, and semantic preparation.
- **M3.4 — Lever:** hosted/embedded application detection, posting/source metadata preservation, false-positive resistance, and semantic preparation.
- **M3.5 — Workday:** stateful wizard modeling for resume, contact, experience, questions, disclosures, terms, Candidate Home/account access, and final review. `Next`, `Save for Later`, account actions, Apply with LinkedIn, and Submit remain typed blocked operations because Workday progression can itself be consequential.
- **M3.6 — Browser audit artifacts:** privacy-redacted screenshots, sanitized structural/semantic/ATS JSON, correlated manifests, SHA-256 integrity records, and a storage abstraction that keeps production artifacts out of the repository.
- **M3.7 — Explicit final-submit gate:** deterministic readiness checks, short-lived one-shot human authorization, state/session/document/control fingerprint binding, durable pre-click authorization consumption, an application-wide execution lock for concurrency/crash safety, a narrowly scoped Playwright final-submit executor, success-probe confirmation, safe receipts, and indeterminate timeout handling.

M3 is complete as an engineering milestone. Final-submit execution is deliberately not exposed as a stateless HTTP click endpoint: the executor requires the live browser page/session that was bound into the reviewed state. CI submits only controlled synthetic fixtures, never real employer applications.

## Flagship v1 capabilities

### F1 — Persistent search profiles and hard constraints

JobOps now stores reusable candidate-owned search profiles and applies them as deterministic eligibility rules **before** fit ranking.

A profile can express requested role titles, required/excluded keywords, allowed work modes, locations, employment types, salary floor/currency policy, excluded companies, allowed sources, and an optional minimum fit score.

The default salary behavior is strict: a request such as "remote Data Engineer roles paying at least $65k/year" rejects hybrid/onsite/unknown work modes, rejects salary ranges whose verified lower bound is below $65k, and rejects unknown compensation unless the profile explicitly allows unknown salary.

Search-profile preview returns ranked eligible jobs plus stable rejection-code summaries so the user can see why jobs were excluded.

See `docs/flagship-search-profiles.md` for the hard-constraint contract. F2 adds resilient multi-provider discovery through Jobicy plus optional Adzuna, normalizes all returned jobs through the canonical pipeline, reapplies the saved hard constraints authoritatively, and persists only eligible deduplicated jobs with provider/rejection diagnostics. See `docs/flagship-discovery.md` for the discovery contract.

F3 adds `POST /v1/search-profiles/{profile_id}/run`, which composes discovery, store-wide hard constraints, deterministic ranking, explainable resume-family selection, verified evidence retrieval, and readiness packaging in one call. See `docs/flagship-run.md` for the orchestration contract.

F4 persists a privacy-minimized snapshot after each successful Flagship run and adds `GET /v1/search-profiles/{profile_id}/readiness` plus `GET /v1/search-profiles/{profile_id}/exceptions`, so ready work stays quiet and only review-required jobs/pending approvals surface for candidate attention. See `docs/flagship-readiness.md`.

### Flagship roadmap

- F1 persistent search profile + hard constraints — complete;
- F2 multi-provider internet job discovery — complete;
- F3 end-to-end discover/filter/rank/prepare orchestration — complete;
- F4 exception/review inbox and readiness summary — complete;
- F5 supported ATS application execution orchestration — next;
- F6 command-center API/dashboard;
- F7 scheduled/daily runs and tracking summaries;
- F8 real candidate/resume onboarding and v1 demo/release.

Advanced M4 learning work is now treated as **Labs/Expansion**. M4.1 feedback events and M4.2 leakage-resistant datasets remain complete and useful; later learned models can improve the Flagship without blocking a working v1.

## M4 capabilities implemented so far

### M4.1 — Feedback and outcome events

JobOps now records learning signals as an **append-only event stream** rather than overwriting one application-status field. This preserves both when an event happened (`occurred_at`) and when JobOps first learned about it (`observed_at`), giving later dataset builders an explicit temporal boundary for preventing hindsight leakage.

The first event schema covers job views/saves/skips and interest feedback; application start, preparation, submission, abandonment, and withdrawal; recruiter responses/screens; interview scheduling/completion; rejection and offer outcomes; ranking feedback; and resume-selection acceptance/override.

M4.1 adds:

- PostgreSQL event persistence with an Alembic migration and deterministic chronological ordering;
- server-controlled observation timestamps distinct from real-world occurrence time;
- semantic idempotency, so retries with the same key and event content return the original event even when a client regenerated its UUID;
- conflict detection when an idempotency key is reused for different event semantics;
- bounded privacy-minimized metadata that rejects answer/message, PII, authentication/session, legal-identification, EEO/demographic, and work-authorization fields;
- optional model name/version and experiment ID context for later attribution and experiment analysis;
- cutoff-aware querying through `observed_to`, allowing a training builder to request only facts actually known by a prediction cutoff;
- indexed job/application/event-type/time queries;
- `POST /v1/feedback/events`, `GET /v1/feedback/events`, and `GET /v1/feedback/events/{event_id}`;
- unit, persistence, API, migration, temporal-order, privacy, and idempotency regression coverage using synthetic data only.

See `docs/feedback-events.md` for the event semantics, temporal ML contract, idempotency rules, and privacy boundary.

### M4.2 — Leakage-resistant training dataset builder

JobOps can now turn explicit historical decision snapshots plus the immutable event stream into deterministic supervised-ranking rows without leaking future knowledge into features.

M4.2 adds:

- typed dataset specification, label policy, decision-point, feature-row, diagnostics, split, manifest, and build-result contracts;
- explicit prediction cutoffs and configurable future label windows;
- feature-event eligibility based on `observed_at <= cutoff`;
- label eligibility that requires both occurrence and observation after the decision point and observation within the declared horizon;
- a fixed inspectable ranking feature schema built from the existing baseline scorer plus pre-cutoff historical aggregates;
- configurable positive/negative event definitions, with employer outcomes excluded from ranking labels by default;
- explicit ambiguous/unlabeled dispositions instead of silently resolving contradictory feedback;
- deterministic chronological train/validation splitting with no default random shuffle;
- a deterministic dataset fingerprint that excludes generation time but includes specification, schema, and canonical rows;
- JSONL + JSON manifest output and a `jobops-build-dataset` CLI;
- strict feature-key validation and ignored private training-output paths to keep raw narrative/PII fields out of the public ML dataset surface;
- synthetic temporal/privacy/reproducibility regression tests.

See `docs/training-datasets.md` for the cutoff rules, label semantics, feature schema, split contract, privacy boundary, and reproducibility design.

## M1 capabilities

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

## M2 capabilities

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
- layered claim-level verification with deterministic vetoes for unsupported metrics, technologies, credentials, and other concrete mismatches;
- persistent PostgreSQL human approval queue with proposed, edited, and final answer separation;
- explicit `approved_for_preparation` versus `submitted` separation;
- mocked/fake model testing so CI remains model-download-free;
- sanitized public candidate evidence with no production PII.

## M3 capabilities implemented

### Guarded browser foundation

- optional Playwright dependency rather than a mandatory base-runtime dependency;
- typed browser session, page, form, field, option, structural-plan, semantic-plan, ATS-preparation, Workday-state, blocked-action, capture, and audit-manifest contracts;
- isolated non-persistent browser contexts with service workers blocked by default;
- inventory for native inputs, textareas, selects, checkboxes, radios, buttons, file controls, headings, and page-level actions;
- stable selectors plus label/accessibility/required/disabled metadata;
- blocked `POST`, `PUT`, `PATCH`, and `DELETE` requests while the write gate is closed;
- blocked post-load document navigation while the write gate is closed;
- DOM guards for submit events, `form.submit()`, and `form.requestSubmit()`;
- guarded top-document plus meaningful child-frame inspection;
- submit-capable controls represented as blocked operations instead of executable actions.

### Semantic policy

- deterministic semantic mapping for identity/contact data, professional links, documents, preferences, legal/consequential questions, narratives, demographics, consent/attestation, unknowns, and submit controls;
- surfaced confidence, matched signals, and ambiguity rather than silent guesses;
- direct reuse of M2 `QuestionCategory`, `HandlingRoute`, and Green/Yellow/Red review policy;
- optional provider-neutral model assistance only for unresolved controls;
- model-assisted mappings prevented from becoming Green autofill;
- sensitive and consequential controls remain Red even when a model can classify them;
- semantic preparation plans route fields to verified facts, draft-with-review, human review, escalation, or blocked submit without writing to the browser.

### ATS/workflow adaptation

- Greenhouse hosted and embedded/iFrame preparation with `gh_jid`, `gh_src`, and board metadata preservation when available;
- Greenhouse application-form isolation from unrelated careers-page controls;
- Lever hosted and embedded/iFrame preparation with account/site, posting UUID, `lever-source`, and `lever-origin` preservation when available;
- Lever rejection of generic external `/apply` pages and posting pages without application-form evidence;
- Workday state modeling without collapsing the wizard into a single form;
- Workday classification for account access, resume, contact information, experience, application questions, voluntary disclosures, terms/consent, final review, and unknown states;
- available Workday tenant/site/locale/requisition/source metadata preserved as context;
- Workday `Next/Continue`, Save for Later, Sign In, Create Account, Apply with LinkedIn, Submit, and other progression remain blocked;
- Workday job-detail pages are not mistaken for application-wizard state merely because they expose Apply/Sign In;
- embedded Workday child-frame states inherit verified parent Workday context while no-form final review remains inspectable;
- LinkedIn account/browser automation remains outside the ATS automation layer while a LinkedIn profile URL can still be candidate data.

### Privacy-safe audit artifacts

M3.6 can emit one correlated audit bundle per browser inspection/preparation run:

```text
artifacts/browser-audit/<run-id>/
  screenshot.png
  browser-snapshot.json
  semantic-plan.json
  ats-context.json
  manifest.json
```

The audit layer provides:

- full-page screenshot capture inside the same guarded Playwright context used by inspection;
- DOM redaction before screenshot pixels are captured;
- clearing/masking of entered input, textarea, select, checkbox/radio, and contenteditable state;
- masking of visible email, phone, SSN-shaped, and labelled sensitive values;
- URL sanitization that removes fragments and masks credential/session/PII query values while preserving safe job/source attribution where possible;
- structural-text sanitization for titles, headings, labels, placeholders, options, and page actions that echo PII;
- defensive omission of candidate answer/value fields and credential/token/session fields from semantic/ATS JSON payloads;
- deterministic JSON serialization for reproducibility;
- SHA-256 and byte-length integrity records for persisted audit payloads;
- manifest metadata for run ID, UTC timestamp, sanitized source URL, vendor, browser engine, redaction count, and explicit non-write/non-submit state;
- a `BrowserAuditArtifactStore` protocol plus a private local development implementation;
- path-traversal protection for local artifact run IDs/file names;
- `artifacts/` gitignored so private production audit material cannot be accidentally committed through normal workflows;
- synthetic real-Chromium CI coverage proving screenshot capture does not weaken mutation blocking.

See `docs/browser-audit-artifacts.md` for the privacy, retention, storage, and integrity contract.

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

### M3 — Application Automation — complete

- guarded Playwright abstraction — complete;
- semantic generic field detection and M2 policy mapping — complete;
- Greenhouse browser preparation adapter — complete;
- Lever browser preparation adapter — complete;
- Workday research/stateful prototype — complete;
- privacy-safe screenshot/audit artifacts — complete;
- explicit one-shot executable/final submit gate — complete.

### M4 — Learning System — in progress

- immutable feedback/outcome event stream — complete;
- leakage-resistant training dataset builder — complete;
- learned ranking baseline — next;
- gradient-boosted ranking model;
- resume-selection model;
- application-outcome analytics;
- interview/callback prediction;
- experiment tracking;
- calibration and drift checks.

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
                                       Structural + UI State Snapshot
                                          /                  \
                                  native forms        headings/actions
                                          \                  /
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
                                                /                  \
                                               v                    v
                                Greenhouse / Lever Adapters    Workday Prototype
                               detect/isolate/metadata       detect/classify state
                                               \                    /
                                                \       blocked actions
                                                 \                  /
                                                             v
                                                Audit Bundle Writer
                                                /       |        \
                                         redaction    hashes    manifest
                                                             |
                                                             |
                                                             v
                                               Readiness Evaluator
                                                             |
                                                    HUMAN AUTHORIZE
                                                             |
                                                             v
                                            One-Shot Submit Authorization
                                                             |
                                                             v
                                         Bound Final-Submit Executor
                                      session + document + control hashes
                                                             |
                                                             v
                                              Submission Receipt
                                      success / failed / indeterminate
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

Then open `http://127.0.0.1:8000/command-center` for the Flagship dashboard or `http://127.0.0.1:8000/docs` for the API.\n\nFor unattended daily searches, configure `jobops-flagship-daily --input-dir data/private/flagship-runs` with Windows Task Scheduler or cron. See `docs/flagship-daily.md`.

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

## Browser development

Install the optional browser stack and Chromium only when working on M3:

```bash
pip install -e ".[dev,browser]"
python -m playwright install chromium
```

M3.1–M3.7 share the same browser and semantic-policy safety boundaries. Audit capture does not create a second, less-guarded browser path: screenshot capture runs inside the existing isolated context after a privacy-redaction pass, while mutation/network/submission guards remain active. M3.7 adds a separate capability boundary for final submission: readiness must pass, a human must authorize the exact prepared state, the authorization is consumed once, and the bound executor rechecks the live session/document/control before clicking.

Current browser contracts:

- `docs/browser-dry-run.md`
- `docs/semantic-form-mapping.md`
- `docs/greenhouse-browser-adapter.md`
- `docs/lever-browser-adapter.md`
- `docs/workday-browser-prototype.md`
- `docs/browser-audit-artifacts.md`
- `docs/explicit-submit-gate.md`

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
  api/            FastAPI health, jobs, scoring, ranking, approval, submission, and feedback endpoints
  approvals/      human-review state machine
  browser/        guarded inspection, semantic mapping, ATS/workflow adapters, audit artifacts
  db/             PostgreSQL models, sessions, repositories, approvals, submissions, and feedback events
  embeddings/     pluggable semantic embedding providers
  ingestion/      ATS feed adapters, source config, refresh runner, and CLI
  knowledge/      TruthStore, resume evidence, retrieval, question policy
  llm/            provider-neutral language-model interfaces and HTTP adapters
  matching/       job scoring, resume-family selection, future learned rankers
  feedback.py     append-only learning feedback/outcome ingestion service
  models/         typed domain/evidence/LLM/browser/ATS/workflow/audit/approval contracts
  normalization/  canonicalization plus deterministic/semantic deduplication

data/examples/    sanitized runnable sample data
data/evaluation/  labeled evaluation fixtures
docs/             architecture and engineering decisions
tests/            unit, integration, and controlled browser tests
```

## Safety and privacy

Do **not** commit production candidate data, credentials, API keys, browser cookies, recruiter correspondence, legal-identification data, or production browser audit artifacts. Use `.env`, private runtime configuration, external databases/secrets managers, and private artifact storage for those values.

JobOps should never invent qualifications, certifications, work authorization, legal attestations, or other candidate facts. Unknown consequential questions must be escalated for human review. Language-model output cannot override deterministic review policy, blocked verification cannot be approved through the queue, approval cannot trigger final submission on its own, model-assisted browser mappings cannot become Green autofill decisions, ATS-specific detection cannot lower review requirements, and consent/attestation controls cannot be answered automatically.

Browser auditability does not weaken those controls. Audit screenshots are redacted before capture; structural/semantic/ATS JSON is sanitized before persistence; raw candidate-answer/value and credential/session fields are omitted defensively; persisted audit payloads receive integrity hashes; and private artifact roots are gitignored. Audit generation cannot open the write gate or submit an application.

Workday wizard progression, employer-side draft persistence, Candidate Home authentication/account creation, Apply with LinkedIn, and final application submission remain non-executable.

## Portfolio goal

This repository is meant to demonstrate an end-to-end intelligent decision system rather than a thin LLM wrapper: custom data pipelines, explainable scoring, semantic ML, provenance-aware RAG, local/private inference, layered hallucination controls, human-in-the-loop state management, guarded browser automation, semantic UI understanding, reusable ATS-specific adaptation, stateful workflow modeling, iframe handling, source-attribution preservation, consequential-action analysis, privacy-aware observability, artifact integrity, real-browser CI testing, and analytics all live behind one product boundary.
