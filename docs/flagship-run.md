# Flagship run orchestration

Flagship F3 turns the existing JobOps subsystems into one product-facing workflow.

## Endpoint

```text
POST /v1/search-profiles/{profile_id}/run
```

For F3, the request includes a CandidateProfile and ResumeEvidenceBase directly. Persistent
real-candidate onboarding remains F8.

## Pipeline

```text
saved SearchProfile
    |
    v
F2 multi-provider discovery
    |
    v
active canonical Job Store
    |
    v
authoritative SearchProfile hard constraints
    |
    v
baseline fit scoring + optional fit threshold
    |
    v
ranked jobs
    |
    v
explainable resume-family selection
    |
    v
bounded verified evidence retrieval
    |
    v
ready / review-required preparation packages
```

The Job Store pass is intentional. F3 evaluates both jobs found during the current discovery run
and active jobs already present from employer ATS ingestion or earlier runs.

## Ownership

The saved profile, candidate profile, and resume evidence base must share the same candidate ID.
Mismatched ownership fails closed before preparation.

## Readiness

A ranked job is marked `review_required` when:

- resume-family selection falls below the configured confidence threshold and no explicit fallback
  family was supplied; or
- the chosen family has no verified evidence available for retrieval.

Otherwise the package is marked `ready`.

This status means ready for later application-preparation/execution stages. It does not authorize
browser writes or submission.

## Result

The run returns:

- F2 discovery diagnostics;
- active jobs examined;
- hard-constraint eligible/rejected counts;
- stable hard-constraint and fit-threshold rejection summaries;
- total jobs surviving fit ranking;
- bounded prepared jobs in deterministic score order;
- explainable resume-family selection for each prepared job;
- verified evidence hits for each prepared job;
- ready versus review-required counts.

## Safety boundary

F3 does not fill live employer forms, click progression controls, answer sensitive questions,
authorize submission, or submit applications.

F4 consumes review-required states as the exception inbox. F5 owns supported ATS execution and the
existing one-shot final-submit authorization boundary.
