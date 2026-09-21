# Flagship readiness snapshots and exception inbox

Flagship F4 turns the F3 run result into a durable "what needs me?" surface for the current job hunt.

## Persistence boundary

A successful Flagship run stores:

- run/profile/candidate IDs and timestamps;
- aggregate examined, eligibility, ranking, and readiness counts;
- stable rejection-code totals;
- one lightweight row per prepared job containing rank, fit score, selected resume family,
  resume-selection score/confidence state, readiness reasons, and evidence IDs.

The F4 snapshot deliberately does **not** duplicate:

- resume evidence claim text;
- generated application answers;
- browser screenshots;
- credentials or provider secrets;
- discovery-provider raw payloads.

Historical runs are retained. Readiness and exception endpoints resolve the most recently completed run for the requested SearchProfile.

## API

```text
GET /v1/search-profiles/{profile_id}/readiness
GET /v1/search-profiles/{profile_id}/exceptions
```

`readiness` returns the latest run summary and lightweight prepared-job rows.

`exceptions` returns only candidate-attention work from the latest run:

- prepared jobs whose F3 readiness is `review_required`;
- pending ApprovalQueue items associated with jobs prepared in that run.

Jobs that are ready and have no pending review work remain out of the exception inbox.

Both endpoints return 404 when the SearchProfile does not exist or when it has not yet produced a successful Flagship snapshot.

## Run integration

`POST /v1/search-profiles/{profile_id}/run` writes the F4 snapshot only after F3 completes successfully. A failed ownership/readiness run therefore cannot replace the latest successful snapshot.

The run result returned to the caller remains the full F3 result; the durable F4 record is intentionally smaller and privacy-minimized.

## Why this matters for the Flagship

The product loop is now:

```text
saved SearchProfile
  -> discover
  -> normalize / deduplicate
  -> hard-filter
  -> rank
  -> select resume family / verified evidence
  -> package readiness
  -> persist lightweight run snapshot
  -> show only review-required exceptions
```

F5 can consume the same latest-run readiness records when it begins orchestrating supported ATS application execution.
