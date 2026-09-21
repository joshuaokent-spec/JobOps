# Leakage-resistant ranking training datasets

M4.2 turns JobOps feedback/outcome events into reproducible supervised-learning rows without allowing future knowledge to leak into historical features.

## Decision-point snapshots

Each row begins from an explicit `RankingDecisionPoint` containing:

- a candidate profile snapshot;
- a job posting snapshot;
- a prediction cutoff timestamp;
- optional application ID;
- optional selected resume-family ID.

The builder does **not** query today's mutable candidate/job row and pretend it represents the past. Callers are responsible for supplying the state snapshot that existed at the decision point.

## Temporal contract

For a prediction cutoff `T`:

### Features

Feature events are eligible only when:

```text
event.observed_at <= T
```

Observation time governs what JobOps knew. A late-imported event that happened earlier but was only observed later does not become a historical feature.

### Labels

A future event may contribute to a label only when:

```text
event.occurred_at > T
event.observed_at > T
event.observed_at <= T + label_window
```

Requiring the event itself to occur after the decision point prevents a historical action imported later from being misinterpreted as a future outcome.

Events observed after the label horizon are ignored.

## Initial target

The first dataset targets candidate interest / job-ranking behavior.

Default positive signals:

- `job_saved`;
- `interest_marked`;
- `strong_interest_marked`;
- `application_started`;
- `application_submitted`.

Default negative signals:

- `job_skipped`;
- `application_abandoned`.

Recruiter responses, interviews, rejections, and offers are **not** ranking labels by default. They remain available for later explicitly defined outcome datasets.

The positive and negative event sets are configurable through `RankingLabelPolicy`, and the schema rejects overlapping event definitions.

## Contradictory and unlabeled examples

If both a configured positive and negative event occur inside one label window, the row becomes:

```text
label_disposition = ambiguous
split = excluded
```

If neither side appears, it becomes:

```text
label_disposition = unlabeled
split = excluded
```

The builder never silently resolves contradictory behavior.

## Feature schema

The first version intentionally uses a fixed, inspectable feature schema:

- title fit;
- required-skill fit;
- preferred-skill fit;
- experience fit;
- compensation fit;
- work-mode fit;
- baseline overall score;
- posting age;
- source;
- work mode;
- salary-availability indicators;
- resume-family ID;
- prior positive feedback count;
- prior negative feedback count;
- prior application-event count;
- prior recruiter-response count;
- prior recruiter-screen count;
- prior interview count;
- prior rejection count;
- prior offer count.

The `RankingFeatureRow` validator requires **exactly** this schema. Arbitrary feature keys cannot be smuggled into the row payload, which also prevents raw narrative/PII fields from appearing under ad-hoc names.

Embeddings are deliberately excluded from v1. A future embedding feature must be an explicit versioned provider, not an opaque column added to the row.

## Historical aggregates

History aggregates may use events from other jobs, but only when those events were observed at or before the row cutoff.

This allows features such as prior application/recruiter/interview history without leaking the current row's future label.

## Chronological splitting

The default split is deterministic and time-aware:

1. retain only positive/negative labeled rows;
2. sort by prediction cutoff and stable point ID;
3. assign the earliest configured fraction to train;
4. assign the later rows to validation;
5. keep ambiguous/unlabeled rows excluded.

No random shuffle is used by default.

Future grouped splitting can extend this contract when enough data exists to enforce company/job/application grouping without destroying sample size.

## Reproducibility

The manifest records:

- dataset/schema/builder version;
- label window;
- positive and negative event definitions;
- fixed feature names;
- class counts;
- split counts;
- first/last prediction cutoff;
- maximum considered source-event observation cutoff;
- deterministic dataset SHA-256 fingerprint.

The fingerprint is based on the dataset specification, feature schema, and canonical serialized rows. It intentionally excludes `generated_at`, so rebuilding identical inputs produces the same fingerprint.

## Output

The writer emits:

```text
<output-dir>/
  rows.jsonl
  manifest.json
```

Only train/validation rows are written to `rows.jsonl`; ambiguous and unlabeled rows remain in the in-memory build result and diagnostics.

A CLI is registered as:

```bash
jobops-build-dataset \
  --points data/private/ranking-points.json \
  --events data/private/feedback-events.json \
  --spec data/private/ranking-spec.json \
  --output data/training/ranking-v1
```

Production training outputs belong in ignored/private paths. The public repository should contain synthetic fixtures only.

## Privacy boundary

Training features are numerical/categorical derived values and stable IDs. The first builder does not include:

- raw job descriptions;
- raw candidate narrative answers;
- recruiter-message bodies;
- email/phone/address fields;
- passwords/tokens/cookies/session data;
- legal-identification values;
- EEO/demographic answers;
- work-authorization answers.

## Relationship to M4.3

M4.3 will train the first logistic-regression ranking baseline from these model-ready rows.

The learned model should therefore inherit M4.2's temporal, feature-schema, lineage, and split contracts rather than rebuilding labels independently.
