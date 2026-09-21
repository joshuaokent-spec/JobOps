# Roadmap

## M0 — Foundation — complete

- [x] Package structure
- [x] Typed candidate/job models
- [x] Evidence-backed truth store
- [x] Transparent rule scorer
- [x] Orchestration shell
- [x] FastAPI health/score endpoints
- [x] CI and tests
- [x] PostgreSQL persistence

## M1 — Job Intelligence — complete

- [x] Greenhouse ingestion adapter
- [x] Lever ingestion adapter
- [x] Canonical normalization pipeline
- [x] Deterministic duplicate detection
- [x] Embedding-assisted near-duplicate detection
- [x] PostgreSQL repositories and migrations
- [x] Job search/filter API
- [x] Scheduled ingestion pipeline

## M2 — Application Intelligence — complete

- [x] Resume evidence schema
- [x] Resume-family selector
- [x] Retrieval layer
- [x] Question classifier
- [x] LLM provider abstraction
- [x] Narrative-answer drafting agent
- [x] Evidence verifier
- [x] Approval queue

## M3 — Browser Automation — complete

- [x] Playwright abstraction
- [x] Generic semantic form-field detector
- [x] Greenhouse browser adapter
- [x] Lever browser adapter
- [x] Workday research/stateful prototype
- [x] Screenshot/audit artifacts
- [x] Explicit submit gate

## Flagship v1 — complete

The flagship product is the priority: give JobOps a candidate/resume evidence base and explicit search criteria, let it discover matching jobs broadly, prepare applications, surface only exceptions, submit through supported ATS paths with explicit authorization, and track results.

- [x] F1 — Persistent search profiles + hard-constraint engine
- [x] F2 — Multi-provider internet job discovery
- [x] F3 — End-to-end flagship run orchestrator
- [x] F4 — Exception/review inbox + readiness summary
- [x] F5 — Supported ATS application execution orchestration
- [x] F6 — Command-center API/dashboard
- [x] F7 — Scheduled/daily flagship runs + tracking summary
- [x] F8 — Real candidate/resume onboarding + v1 demo/release

## Labs / Expansion — M4 Learning System

These features improve or extend the flagship but do not block Flagship v1.

- [x] Feedback event schema
- [x] Leakage-resistant training dataset builder
- [ ] Explainable logistic ranking baseline — parked/in progress on Labs branch
- [ ] Gradient-boosted ranking model
- [ ] Learned resume-selection model
- [ ] Callback/interview prediction
- [ ] Experiment tracking
- [ ] Calibration and drift checks
