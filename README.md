# JobOps

**JobOps** is an evidence-grounded, human-in-the-loop job-search intelligence platform for discovering, ranking, preparing, and tracking job applications.

The project is intentionally designed as a portfolio-grade system spanning data engineering, data science, machine learning, agent orchestration, retrieval, API design, browser automation, and analytics.

## Core principles

- **Truth before fluency:** generated answers must be grounded in verified candidate facts.
- **Human approval before submission:** the system may prepare applications, but consequential submission stays behind an approval gate.
- **ML where prediction helps, LLMs where language helps:** ranking and outcome prediction are modeled separately from natural-language generation.
- **Reproducible data pipelines:** ingest, normalize, deduplicate, score, and track jobs as structured data.
- **Auditable decisions:** every score and generated answer should be explainable from stored evidence.

## Current milestone: M0 — Foundation

This initial scaffold includes:

- typed domain models for jobs, candidate profiles, facts, and applications;
- an evidence-backed `TruthStore`;
- a transparent baseline job scoring model;
- a small FastAPI service;
- example candidate configuration;
- unit tests and GitHub Actions CI;
- architecture documentation designed for later agent and ML expansion.

## Planned releases

### M1 — Job Intelligence

- job-source adapters;
- normalized job schema;
- deduplication;
- baseline ranking;
- persistent PostgreSQL storage;
- dashboard/API views.

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

## Example API usage

```bash
curl http://127.0.0.1:8000/health
```

Score a sample job:

```bash
curl -X POST http://127.0.0.1:8000/v1/score \
  -H "Content-Type: application/json" \
  -d @data/examples/score-request.example.json
```

## Repository layout

```text
src/jobops/
  agents/       orchestration interfaces and future specialized agents
  api/          FastAPI application
  knowledge/    evidence-backed candidate truth store
  matching/     scoring, feature generation, future learned rankers
  models/       typed domain models

data/examples/  sanitized runnable sample data
docs/           architecture and engineering decisions
tests/          unit and integration tests
```

## Safety and privacy

Do **not** commit production candidate data, credentials, API keys, browser cookies, recruiter correspondence, or legal-identification data. Use `.env`, private runtime configuration, and external databases/secrets managers for those values.

JobOps should never invent qualifications, certifications, work authorization, legal attestations, or other candidate facts. Unknown consequential questions must be escalated for human review.

## Portfolio goal

This repository is meant to demonstrate an end-to-end intelligent system rather than a thin LLM wrapper: custom data pipelines, explainable baseline scoring, learned models, retrieval, agent tooling, browser automation, testing, observability, and analytics all live behind one product boundary.
