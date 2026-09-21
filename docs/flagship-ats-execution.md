# Flagship F5 — Supported ATS application execution

F5 connects the Flagship readiness layer to controlled live application preparation for supported applicant-tracking systems.

The execution boundary is intentionally split into two phases:

```text
latest Flagship run
    |
    v
F4 readiness / approvals
    |
    v
F5 live ATS preparation
    |
    +--> privacy-safe audit bundle
    +--> sealed PreparedSubmissionState
    |
    v
M3.7 one-shot human authorization
    |
    v
final submit executor
```

Preparation is not submission.

## Supported v1 ATS behavior

### Greenhouse and Lever

JobOps can prepare a live application page when the job is in the latest Flagship run and all earlier review requirements have been resolved.

F5:

- re-checks latest-run membership before touching the browser;
- verifies the candidate owns the latest Flagship run;
- refuses jobs whose F4 readiness remains `review_required`;
- refuses browser preparation while ApprovalQueue items remain pending;
- uses only verified CandidateProfile facts for Green-band autofill;
- uses only explicitly approved review answers for Yellow/Red fields;
- accepts approved ephemeral file paths for resume/cover-letter uploads;
- fails closed on required unknown, ambiguous, unsupported, or unresolved fields;
- identifies exactly one final submit control without clicking it;
- calculates a deterministic hash of the prepared payload without persisting raw answers;
- captures a privacy-safe post-preparation browser audit;
- seals the application, job, ATS vendor, payload, browser session, document URL, and submit control into `PreparedSubmissionState`;
- evaluates that exact state with the existing M3.7 submission-readiness rules.

### Workday

Workday remains review-only for Flagship v1.

External Workday applications are stateful multi-step workflows. Next/Continue actions can persist employer-side draft state, and tenants may require Candidate Home account access or other stateful transitions. F5 therefore returns a typed `workday_stateful_progression` blocker instead of pretending that generic single-page execution is safe.

## Latest-run boundary

F5 only operates on work selected by the latest durable Flagship run for a search profile.

A job is blocked before browser writes when:

- no durable Flagship run exists;
- the job is not present in the latest run;
- the candidate does not match the run owner;
- the job is still marked `review_required`;
- pending approvals remain.

This prevents an old recommendation or stale browser tab from silently becoming executable work.

## Live preparation rules

The live preparer supports text-like inputs, selects, explicit boolean checkboxes, and approved file uploads.

Values come from three sources only:

1. `verified_fact` — verified CandidateProfile data;
2. `approved_review` — a final answer explicitly approved in ApprovalQueue;
3. `approved_file` — an ephemeral local path supplied for the selected resume or cover letter.

Unknown candidate facts are never inferred.

Conflicting approved answers fail closed because no single approved answer can be resolved.

Radio-group execution remains blocked until option identity can be sealed deterministically.

## Privacy-safe post-preparation audit

The original M3 read-only screenshot redaction intentionally cleared candidate values before capture. That behavior is unsafe after live preparation because it would alter the browser state being authorized.

F5 adds a reversible live-page capture path:

- form controls are visually masked for the screenshot without changing their values;
- checked state, selected options, and uploaded files are not altered;
- visible PII text nodes are temporarily redacted;
- DOM text and styles are restored in a `finally` path after screenshot capture;
- the structural audit payload still omits candidate-answer values;
- raw passwords, cookies, session tokens, and browser authentication state are never persisted.

A real-Chromium regression test verifies that candidate values and the uploaded resume remain intact after audit capture.

## State sealing and final authorization

A successful preparation produces `PreparedSubmissionState` containing:

- `application_id`;
- `job_id`;
- ATS vendor;
- prepared-payload SHA-256;
- audit run ID and timestamp;
- browser session ID;
- document URL SHA-256;
- exact submit selector;
- submit-control SHA-256;
- blocker counters and ATS/browser-state assertions.

The existing `SubmissionGate` evaluates this state. A real fresh authorization can be issued only when the state has zero blockers and a complete recent audit context.

Authorization remains short-lived and one-shot. Changing the prepared state after authorization invalidates it.

F5 never performs the final submit click itself.

## Safety boundary

F5 does not:

- automate LinkedIn account actions;
- bypass CAPTCHA or MFA;
- create or sign into Candidate Home accounts automatically;
- infer missing candidate facts;
- autonomously answer legal/sensitive questions;
- persist raw candidate answers in audit artifacts;
- persist passwords, cookies, tokens, or authenticated browser state;
- expose a stateless endpoint capable of fabricating a browser session and submitting an application;
- retry an indeterminate submission automatically.

## Tests

F5 regression coverage includes:

- Greenhouse live preparation;
- Lever live preparation;
- missing required fact blocking;
- explicit Workday unsupported/stateful behavior;
- latest Flagship-run membership enforcement;
- pending-approval enforcement before browser writes;
- non-destructive privacy-safe live audit capture;
- deterministic prepared-state sealing;
- successful readiness evaluation;
- successful one-shot `SubmissionGate` authorization;
- proof that preparation and audit capture never invoke Submit.
