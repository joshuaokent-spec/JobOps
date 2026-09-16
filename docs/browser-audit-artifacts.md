# Browser Audit Artifacts

M3.6 adds privacy-aware browser audit bundles so JobOps can prove what it inspected and planned without turning browser automation into a candidate-data archive.

## Goals

Each browser inspection/preparation run may emit a correlated bundle containing:

1. a privacy-redacted full-page screenshot;
2. a sanitized structural browser snapshot;
3. a sanitized semantic/preparation-plan payload;
4. sanitized ATS/workflow context;
5. a manifest containing run metadata and SHA-256 integrity records.

The audit layer is explanatory and reproducibility-oriented. It does not enable browser writes, candidate-account authentication, wizard progression, application submission, or answer generation.

## Capture boundary

`PlaywrightBrowserInspector.capture_url()` and `capture_html()` run inside the same guarded Playwright context used by normal inspection:

- service workers are blocked by default;
- mutating `POST`, `PUT`, `PATCH`, and `DELETE` requests remain blocked;
- post-load document navigation remains blocked while the submit gate is closed;
- DOM submit events, `form.submit()`, and `form.requestSubmit()` remain guarded;
- capture never clicks page actions or submits forms.

The screenshot is captured only after a DOM redaction pass.

## Screenshot redaction

Before pixels are captured, JobOps clears or masks candidate-entered UI state including:

- text, email, telephone, date, number, password, hidden, and similar input values;
- textarea content;
- selected values in select controls;
- checked radio/checkbox state;
- contenteditable text;
- visible email addresses, phone numbers, SSN-shaped values, and labelled sensitive text such as address, work authorization, sponsorship, EEO/disability/veteran status, or consent values.

The capture records how many DOM values/text nodes were redacted, but it does not persist the original values.

## Structural snapshot privacy

Browser snapshots intentionally describe structure rather than entered values. They contain form/action metadata, field descriptors, labels, options, selectors, headings, and page actions; input values are not part of the browser snapshot schema.

Before persistence, JobOps additionally sanitizes:

- source/document/action URLs;
- URL query values that look like credentials, auth/session data, PII, email addresses, phone numbers, or opaque secret-like values;
- page titles, headings, field labels, accessible names, placeholders, option text, and action text that echo email/phone/SSN or labelled sensitive values.

Safe attribution metadata such as `source`, `gh_jid`, `gh_src`, `lever-source`, and `lever-origin` may be preserved when it does not itself match an explicit PII pattern.

URL fragments are removed from persisted audit URLs.

## Semantic and ATS payload policy

`BrowserAuditBundleWriter` accepts optional semantic-plan and ATS/workflow payloads. These payloads are treated as plans/context, not candidate-answer storage.

The writer defensively replaces answer/value-style fields with `[OMITTED]`, including keys such as:

- `answer` / `candidate_answer` / `user_answer`;
- `value` / `current_value` / `selected_value` / `entered_value`;
- `response` / `prefill` / `prefilled_value`;
- credential, token, password, session, cookie, and API-key fields.

URL fields inside those payloads are sanitized with the same URL policy.

## Manifest and integrity

Each bundle receives a run ID and manifest with:

- schema version;
- UTC creation timestamp;
- sanitized source URL;
- ATS/vendor (`generic`, `greenhouse`, `lever`, or `workday`);
- browser engine;
- redaction count;
- explicit `live_writes_allowed=false` and `submission_allowed=false` state;
- artifact media type, relative path, byte length, and SHA-256 digest.

Current persisted artifact payloads are:

```text
<run-id>/
  screenshot.png
  browser-snapshot.json
  semantic-plan.json
  ats-context.json
  manifest.json
```

The manifest describes the four audit payload artifacts; the manifest itself is the bundle index and is not recursively listed as an artifact inside itself.

## Storage boundary

`BrowserAuditArtifactStore` is a protocol so persistence is not coupled to local disk. M3.6 includes `LocalBrowserAuditArtifactStore` as the development implementation.

The default local root is:

```text
artifacts/browser-audit/
```

`artifacts/` is gitignored. Production/private audit artifacts must not be committed to the public repository.

The local store validates run IDs and file names to reject path traversal.

Future stores may target private object storage or another controlled persistence layer while keeping the same bundle contract.

## Retention and access

Audit artifacts should be treated as potentially sensitive even after redaction. Production deployment should define:

- an explicit retention period;
- least-privilege read access;
- encryption at rest when using remote storage;
- deletion/cleanup behavior;
- environment-specific storage roots/buckets;
- no public web serving by default.

M3.6 defines the storage interface and privacy contract; it does not create a public artifact browser or upload private artifacts to GitHub.

## Tests

The M3.6 test matrix includes:

- URL attribution preservation plus sensitive-query redaction;
- structural text PII redaction;
- real Chromium screenshot capture from synthetic HTML;
- DOM redaction before screenshot generation;
- a synthetic mutating `POST` that remains blocked during capture;
- deterministic artifact byte-length/SHA-256 verification;
- answer/credential omission from semantic and ATS JSON;
- path-traversal rejection in the local store.

CI fixtures contain synthetic data only.

## Safety invariant

Audit capture must never weaken the browser safety boundary. If audit generation fails, that failure does not grant write capability, advance an ATS workflow, or open the final submit gate.
