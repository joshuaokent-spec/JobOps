# JobOps

**JobOps** is an evidence-grounded, human-in-the-loop job-search intelligence platform for discovering, ranking, preparing, and tracking job applications.

The project is intentionally designed as a portfolio-grade system spanning data engineering, data science, machine learning, agent orchestration, retrieval, API design, browser automation, and analytics.

## Core principles

- **Truth before fluency:** generated answers must be grounded in verified candidate facts.
- **Human approval before submission:** the system may prepare applications, but consequential submission stays behind an approval gate.
- **ML where prediction helps, LLMs where language helps:** ranking and outcome prediction are modeled separately from natural-language generation.
- **Reproducible data pipelines:** ingest, normalize, deduplicate, score, and track jobs as structured data.
- **Auditable decisions:** every score and generated answer should be explainable from stored evidence.

## Current milestone: M2 — Application Intelligence

M1 Job Intelligence is complete. JobOps can ingest supported ATS feeds, normalize and persist canonical postings, identify deterministic and semantic duplicate candidates, query/filter active jobs, and rank a filtered candidate pool with the explainable baseline scorer.

M2 has started with the evidence-grounded candidate knowledge model. A master `ResumeEvidenceBase` stores factual career evidence once, with provenance, role-family tags, skills, metrics, verification state, and retrieval-ready text. Role-specific resume families select from that shared evidence rather than duplicating facts across static resume variants.

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

- typed career-evidence entities for experience, projects, education, certifications, skills, and achievements;
- explicit provenance sources and verification state;
- role-family, skill, tag, and recency-aware deterministic filtering;
- resume-family definitions over one master evidence base;
- retrieval-ready canonical evidence text;
- a verified-payload guard that blocks unknown, excluded, or unverified evidence;
- sanitized public example evidence with no production candidate PII.

See `docs/resume-evidence.md` for the boundary between atomic `TruthStore` facts, richer resume evidence, and future generated wording.

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
Candidate Profile -> TruthStore -----------+
                                             |
Resume Evidence -> ResumeEvidenceStore -----+--> Matching / Retrieval / Ranking
                                             |
                                             v
                                  Application Orchestrator
                                   /        |         \
                                  v         v          v
                            Resume Agent  Q&A Agent  Verifier
                                   \        |         /
                                    v       v        v
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

Initialize or upgrade the PostgreSQL schema with:

```bash
docker compose up -d postgres
alembic upgrade head
```

## Job ingestion

Copy the sanitized source example to a private runtime configuration and replace the placeholders with public ATS identifiers:

```bash
cp data/examples/sources.example.yaml data/private/sources.yaml
jobops-ingest --config data/private/sources.yaml
```

Each source refresh is transactional. A failed fetch does not deactivate previously stored jobs; stale postings are marked inactive only after a successful refresh of the same source scope.

## Semantic duplicate detection

Install the optional local ML dependency only when semantic embeddings are needed:

```bash
pip install -e ".[ml]"
```

Scan stored jobs:

```bash
jobops-semantic-dedup scan --threshold 0.84
```

Evaluate threshold behavior:

```bash
jobops-semantic-dedup evaluate \
  --dataset data/evaluation/semantic-duplicate-pairs.example.json
```

## Candidate evidence

A sanitized master-evidence example lives at:

```text
data/examples/resume-evidence.example.yaml
```

The evidence layer treats canonical claims and generated resume wording differently. Generated text may transform verified evidence later in M2, but it may not become a new candidate fact merely because a model wrote it.

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
  knowledge/      TruthStore plus resume evidence access
  matching/       scoring, feature generation, future learned rankers
  models/         typed domain/query/evidence models
  normalization/  canonicalization plus deterministic/semantic deduplication

data/examples/    sanitized runnable sample data
data/evaluation/  labeled evaluation fixtures
docs/             architecture and engineering decisions
tests/            unit and integration tests
```

## Safety and privacy

Do **not** commit production candidate data, credentials, API keys, browser cookies, recruiter correspondence, or legal-identification data. Use `.env`, private runtime configuration, and external databases/secrets managers for those values.

JobOps should never invent qualifications, certifications, work authorization, legal attestations, or other candidate facts. Unknown consequential questions must be escalated for human review.

## Portfolio goal

This repository is meant to demonstrate an end-to-end intelligent system rather than a thin LLM wrapper: custom data pipelines, explainable baseline scoring, semantic ML, learned models, retrieval, provenance-aware knowledge modeling, agent tooling, browser automation, testing, observability, and analytics all live behind one product boundary.
