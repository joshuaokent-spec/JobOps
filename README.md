# JobOps

**JobOps** is an evidence-grounded, human-in-the-loop job-search intelligence platform for discovering, ranking, preparing, and tracking job applications.

The project is intentionally designed as a portfolio-grade system spanning data engineering, data science, machine learning, agent orchestration, retrieval, API design, browser automation, and analytics.

## Core principles

- **Truth before fluency:** generated answers must be grounded in verified candidate facts.
- **Human approval before submission:** the system may prepare applications, but consequential submission stays behind an approval gate.
- **ML where prediction helps, LLMs where language helps:** ranking and outcome prediction are modeled separately from natural-language generation.
- **Reproducible data pipelines:** ingest, normalize, deduplicate, score, and track jobs as structured data.
- **Auditable decisions:** every score and generated answer should be explainable from stored evidence.

## Current milestone: M1 — Job Intelligence

The M0 foundation is complete. M1 now provides a persistent job-intelligence pipeline that can ingest supported ATS feeds, normalize and persist canonical postings, identify deterministic duplicate candidates, query/filter active jobs, and rank a filtered candidate pool with the explainable baseline scorer.

### M0 foundation includes

- typed domain models for jobs, candidate profiles, facts, and applications;
- an evidence-backed `TruthStore`;
- a transparent baseline job scoring model;
- a FastAPI service;
- example candidate configuration;
- unit/integration tests and GitHub Actions CI;
- architecture documentation designed for later agent and ML expansion.

### M1 capabilities implemented

- Greenhouse and Lever public-feed adapters;
- canonical normalization with stable source identities and audit metadata;
- deterministic cross-source duplicate fingerprints;
- PostgreSQL persistence with Alembic migrations;
- paginated job search/filter API;
- baseline candidate-specific job ranking;
- idempotent source refresh with stale-posting deactivation;
- JSON ingestion metrics and scheduler-friendly CLI execution.

The remaining M1 intelligence item is embedding-assisted near-duplicate detection.

## Planned releases

### M1 — Job Intelligence

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
Ingestion -> Normalization -> Deduplication -> Job Store
                                         |
                                         v
Candidate Profile -> Truth Store -> Matching / Ranking
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

The ingestion command is scheduler-friendly: run it from cron, a container scheduler, or another workflow runner. Each source refresh is transactional. A failed fetch does not deactivate previously stored jobs; stale postings are marked inactive only after a successful refresh of the same source scope.

## Example API usage

Health check:

```bash
curl http://127.0.0.1:8000/health
```

List active remote jobs with known compensation that can reach at least $90,000:

```bash
curl "http://127.0.0.1:8000/v1/jobs?work_mode=remote&min_salary=90000"
```

The `/v1/jobs` endpoint supports pagination plus title, company, location, work mode, minimum salary, source, and active-status filters.

Score one sample job:

```bash
curl -X POST http://127.0.0.1:8000/v1/score \
  -H "Content-Type: application/json" \
  -d @data/examples/score-request.example.json
```

`POST /v1/jobs/rank` accepts a candidate profile plus job filters, evaluates a bounded filtered candidate pool with the transparent baseline scorer, and returns jobs ordered by score.

## Repository layout

```text
src/jobops/
  agents/         orchestration interfaces and future specialized agents
  api/            FastAPI health, scoring, job-query, and ranking endpoints
  db/             persistence models, sessions, and repository interfaces
  ingestion/      ATS adapters, source config, refresh runner, and CLI
  knowledge/      evidence-backed candidate truth store
  matching/       scoring, feature generation, future learned rankers
  models/         typed domain/query models
  normalization/  canonicalization and duplicate detection

data/examples/    sanitized runnable sample data
docs/             architecture and engineering decisions
tests/            unit and integration tests
```

## Safety and privacy

Do **not** commit production candidate data, credentials, API keys, browser cookies, recruiter correspondence, or legal-identification data. Use `.env`, private runtime configuration, and external databases/secrets managers for those values.

JobOps should never invent qualifications, certifications, work authorization, legal attestations, or other candidate facts. Unknown consequential questions must be escalated for human review.

## Portfolio goal

This repository is meant to demonstrate an end-to-end intelligent system rather than a thin LLM wrapper: custom data pipelines, explainable baseline scoring, learned models, retrieval, agent tooling, browser automation, testing, observability, and analytics all live behind one product boundary.
