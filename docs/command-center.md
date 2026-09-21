# Flagship command center

F6 gives JobOps one practical operator surface over the Flagship pipeline.

## Surfaces

```text
GET /v1/command-center/{profile_id}
GET /command-center
```

The API endpoint returns one deterministic, profile-centric read model. The browser dashboard consumes that same endpoint with vanilla JavaScript, so there is no separate frontend state model or build pipeline.

## Command-center contents

For a configured search profile, the read model includes:

- the persisted SearchProfile;
- whether a durable Flagship run exists;
- latest-run counts and rejection diagnostics;
- ready jobs with canonical title/company/location/compensation/source/apply links;
- review-required jobs and their deterministic readiness reasons;
- pending approval references needed for navigation;
- missing canonical job IDs, if a readiness snapshot points to a job no longer present;
- links to the existing profile/run/readiness/exceptions/approvals API surfaces.

The no-run-yet state is valid and returns HTTP 200 with an empty command center rather than pretending that a run exists.

## Privacy boundary

The command center is intentionally a minimized projection. Pending approval entries expose the approval ID, job ID, question, review band, reason, and creation time. They do not expose proposed answers, edited answers, final answers, verification payloads, browser cookies, tokens, authentication state, or private browser-audit artifacts.

## Submission boundary

F6 does not add a final-submit button or create submit authorization. F5/M3.7 remain the capability boundary for live ATS preparation and exact-state, one-shot final submission.

## Product relationship

F6 is the manual operator experience for Flagship v1. F7 adds scheduled/daily runs and tracking summaries. F8 adds real candidate/resume onboarding and the release/demo pass needed to use the system against the current job hunt without hand-building request payloads.
