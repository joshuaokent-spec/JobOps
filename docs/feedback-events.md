# Feedback and outcome event stream

M4 starts with an append-only event stream rather than a mutable application-status column.

The purpose is to preserve **what happened, when it happened, and when JobOps learned about it** so later training datasets can be built without hindsight leakage.

## Temporal contract

Every event has two timestamps:

- `occurred_at` — when the underlying user action or hiring outcome happened;
- `observed_at` — when JobOps first recorded that fact.

`observed_at` is server controlled. A historical/imported event may have an older `occurred_at`, but a training dataset using a prediction cutoff must exclude any event whose `observed_at` is after that cutoff.

This distinction is required for questions such as:

- what feedback existed when a job was ranked?
- what resume family had been selected when an application was submitted?
- did a recruiter response become known before or after a model prediction?
- was a label actually available at training cutoff time?

## Event categories

The first schema covers:

- job views, saves, skips, and interest feedback;
- application start, abandon, preparation, submission, and withdrawal;
- recruiter response and recruiter screen;
- interview scheduling/completion;
- rejection and offer lifecycle;
- ranking feedback;
- resume-selection acceptance or override.

The event enum is intentionally explicit. Arbitrary free-form event names are not accepted because stable event semantics matter for downstream labels.

## Idempotency

Each event includes an `idempotency_key`.

Retries with the same key and the same semantic payload return the original event, even if the retry generated a different event UUID. Reusing the same key for different event contents is a conflict.

The database also enforces uniqueness on the idempotency key.

## Privacy boundary

The event stream is not a message archive and is not a second candidate profile.

It does not accept raw narrative answers, recruiter-message bodies, email/phone/address fields, authentication/session data, legal-identification values, EEO/demographic answers, work-authorization answers, tokens, cookies, or secrets inside event metadata.

Metadata is bounded to a small dictionary of primitive scalar values. It is intended for safe categorical context such as the product surface, ATS family, reason code, or model decision context.

## Model and experiment context

Events may optionally record:

- `model_name`;
- `model_version`;
- `experiment_id`.

This lets later analysis compare outcomes across ranking/resume-selection versions without making model context mandatory for ordinary user or employer events.

## Persistence and ordering

PostgreSQL stores events append-only.

Queries return deterministic chronological order by:

1. `occurred_at`;
2. `observed_at`;
3. `event_id`.

Indexes support job, application, event-type, and temporal lookup. The `observed_to` filter exists specifically so later dataset builders can request only facts that were available at a chosen cutoff.

## API

```text
POST /v1/feedback/events
GET  /v1/feedback/events
GET  /v1/feedback/events/{event_id}
```

The API validates the referenced job, enforces metadata constraints, assigns observation time inside the service, and preserves idempotent retry behavior.

## Next milestone

M4.2 will consume this event stream to build leakage-resistant training examples for learned ranking and downstream outcome models.
