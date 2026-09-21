# Explicit Final-Submit Gate

M3.7 adds the first executable final-submit capability to JobOps without turning
application preparation into autonomous submission authority.

The central rule is:

> Approval for preparation is not authorization to submit.

A final submission requires a fresh, short-lived, one-use authorization bound to
the exact prepared application state and the exact live browser/document context
that was reviewed.

## Trust boundaries

JobOps keeps these capabilities separate:

1. **Application preparation** — choose evidence, draft/review answers, map fields,
   and prepare a browser state.
2. **Readiness evaluation** — deterministically prove the prepared state has no
   unresolved blockers.
3. **Human submit authorization** — explicitly authorize one exact state.
4. **Final-submit execution** — consume that authorization and invoke only the
   sealed submit control.
5. **Receipt / reconciliation** — record a safe outcome without storing raw
   candidate answers, credentials, cookies, or browser auth state.

No LLM, scorer, approval item, ATS adapter, audit bundle, or browser dry-run plan
can create submit authority on its own.

## Prepared-state binding

`PreparedSubmissionState` contains only the metadata needed to prove that the
reviewed state has not drifted:

- application ID and job ID;
- ATS/vendor;
- SHA-256 of the prepared application payload;
- audit run ID and audit timestamp;
- opaque browser session ID;
- SHA-256 of the current document URL;
- the exact submit selector;
- SHA-256 fingerprint of the submit control;
- counts for unresolved required fields, ambiguous mappings, blocked
  verification, pending review, unanswered Red-band controls, and unconfirmed
  consent;
- submit-control count and enabled state;
- ATS-context and browser-state match flags.

The full state is deterministically serialized and SHA-256 hashed again into a
`state_fingerprint`. Any material change produces a different authorization
binding.

Raw answers and candidate secrets are not part of the submit authorization
record.

## Readiness evaluation

`SubmissionReadinessEvaluator` fails closed when any required invariant is not
satisfied.

Blockers include:

- missing audit/browser context;
- unresolved required fields;
- ambiguous semantic mappings;
- blocked evidence verification;
- pending human review;
- unanswered Red-band fields;
- unconfirmed consent/attestation;
- zero or multiple final submit controls;
- disabled final submit control;
- ATS context mismatch;
- browser state mismatch;
- stale audit state.

The default maximum audit age is 15 minutes.

Readiness evaluation is pure. The HTTP readiness endpoint does not need a
repository with write authority.

## One-shot authorization

`SubmitAuthorization` is created only after readiness passes and an explicit
human authorization request is received.

An authorization is bound to:

- application and job identity;
- ATS/vendor;
- prepared-state fingerprint;
- prepared-payload hash;
- audit run;
- browser session ID;
- document URL hash;
- exact submit selector;
- submit-control hash;
- authorizing human and decision note;
- creation and expiration timestamps.

TTL is constrained to 30–900 seconds and defaults to 300 seconds.

The authorization state machine is:

```text
ACTIVE -> CONSUMED
   |
   +----> REVOKED

ACTIVE --time--> EXPIRED
```

Consumed, revoked, or expired authorizations cannot be replayed.

## Transactional consumption and execution locking

The PostgreSQL repository claims an authorization with a row lock before browser
execution begins. It also acquires a unique application-level execution lock so
two different valid authorizations for the same application cannot race to two
browser clicks.

That ordering is deliberate:

1. validate readiness and exact-state binding;
2. verify no blocking attempt already exists for the application;
3. atomically claim the authorization;
4. create an `EXECUTING` attempt and acquire the application execution lock;
5. **commit the consumed authorization and executing attempt durably**;
6. only then enter the final-submit executor;
7. persist the final receipt/outcome in a second commit.

The pre-click commit matters. If the process crashes after the employer may have
received the click, the database still contains a consumed authorization and an
`EXECUTING` attempt. Restarting the process cannot resurrect the one-shot
authorization and cannot silently retry the application.

The database enforces:

- at most one submission attempt per authorization;
- at most one active/uncertain execution lock per application;
- at most one successful-submission key per application.

A definite pre-click `FAILED` outcome with `submit_invoked=false` releases the
application execution lock so the user may review and issue a fresh
authorization. `EXECUTING`, `SUCCEEDED`, and `INDETERMINATE` outcomes retain
the lock because a second click could duplicate a real employer-side
submission.

The service performs the same checks before the database constraints are needed,
but persistence remains the concurrency and crash-safety backstop.

## Browser executor

`PlaywrightFinalSubmitExecutor` is intentionally not a general click API.

It receives a live Playwright `Page` and an opaque browser-session ID when it is
constructed. Its `execute()` method receives only the already-consumed
authorization and the matching prepared state.

Immediately before clicking, it rechecks:

- live browser-session ID;
- SHA-256 of the live document URL;
- exactly one element matches the authorized selector;
- the element is visible and enabled;
- a deterministic fingerprint of the live submit control matches the reviewed
  fingerprint;
- the document identity has not changed during preflight.

The caller cannot provide a different selector at execution time.

The submit-control fingerprint intentionally avoids input values. It is derived
from structural control metadata such as tag/type, ID/name, accessible label,
visible control text, disabled state, and owning-form action/method.

## Success versus indeterminate outcomes

A click is not treated as proof of successful application submission.

The executor accepts a bounded success probe supplied by the live ATS runtime.
It reports `SUCCEEDED` only when that probe observes the configured confirmation
condition.

If submit was invoked but confirmation cannot be proven, the result is
`INDETERMINATE`.

Examples:

- click timeout after execution starts;
- success probe throws;
- submit click occurs but no confirmation state is observed.

An indeterminate attempt is never automatically retried with the same
authorization. Manual reconciliation is required because the employer may have
received the application even when JobOps cannot prove it.

Preflight failures that occur before clicking are recorded as `FAILED` with
`submit_invoked=false`.

## Attempt states

Submission attempts use these states:

- `EXECUTING` — authorization consumed and execution started;
- `SUCCEEDED` — submit invoked and configured success confirmation observed;
- `FAILED` — fail-closed preflight rejected execution before submit;
- `INDETERMINATE` — submit may have occurred but success/failure cannot be
  proven safely.

## API boundary

The HTTP API exposes the control plane:

```text
POST /v1/submissions/readiness
POST /v1/submissions/authorizations
GET  /v1/submissions/authorizations/{authorization_id}
POST /v1/submissions/authorizations/{authorization_id}/revoke
GET  /v1/submissions/attempts/{attempt_id}
```

There is deliberately no stateless HTTP endpoint that accepts arbitrary browser
state and clicks Submit.

Actual final-submit execution requires the live browser page/session object that
was bound into the prepared state. Keeping execution inside the browser runtime
prevents an API request from fabricating a session binding that the server cannot
verify.

A future UI may make review -> authorize -> execute feel like one ergonomic flow,
but those remain separate backend capabilities.

## Privacy

Authorization and receipt storage is metadata-only.

The submit gate must never persist:

- candidate answer text as receipt/debug material;
- passwords;
- cookies;
- browser storage;
- bearer/auth tokens;
- API keys;
- MFA/CAPTCHA material;
- raw browser authentication state.

Executor receipt metadata passes through the same sanitization philosophy as
M3.6:

- answer/value/token/auth/session/cookie/credential-like keys are omitted;
- visible PII in ordinary text values is redacted;
- URL-like values are sanitized;
- raw executor exception messages are not persisted.

If an executor raises after authorization consumption, JobOps stores a generic
reconciliation message rather than the exception text.

## Non-goals

M3.7 does not add:

- autonomous mass application submission;
- LinkedIn account automation;
- CAPTCHA bypass;
- MFA automation;
- automatic Candidate Home authentication;
- automatic account creation;
- fallback clicking by visible text when the authorized control changed;
- automatic retries after indeterminate submission.

Those would weaken the explicit capability boundary rather than complete it.

## Testing

CI uses only controlled synthetic application pages.

Regression coverage includes:

- readiness blockers;
- stale audit rejection;
- exact-state fingerprint binding;
- cross-job authorization rejection;
- short-lived authorization expiry;
- one-use replay prevention;
- revocation;
- duplicate-success prevention;
- exception -> indeterminate behavior;
- PostgreSQL persistence of browser/session bindings;
- cross-session proof that authorization consumption and the `EXECUTING`
  attempt are committed before the executor receives control;
- database rejection of a second application execution lock from a different
  authorization;
- lock release after a definite pre-click failure and lock retention for
  uncertain/successful execution;
- safe receipt metadata sanitization;
- real Chromium execution of one authorized synthetic final-submit control;
- second execution rejection without a second click;
- live submit-control drift rejection before click;
- API separation between readiness, authorization, revocation, and receipt
  lookup;
- absence of a stateless HTTP submit bypass.

No real employer application is submitted by CI.
