# Lever browser adapter

M3.4 adds the second ATS-specific browser preparation adapter on top of the guarded Playwright inspector, M3.2 semantic mapping, and M2 review policy.

## Purpose

The Lever adapter identifies a Lever application context, isolates the candidate application form from unrelated page controls, preserves Lever posting/source metadata, and routes the selected form through existing JobOps semantic and review policy.

It does not call Lever's Apply API and it does not submit applications.

```text
Lever posting / apply experience
              |
              v
  Guarded Playwright inspection
      /                 \
 top document         child frames
      \                 /
              v
      Lever context detection
              |
              v
     isolate application form
              |
              v
      M3.2 semantic mapping
              |
              v
         M2 review policy
              |
              v
   semantic preparation plan
              |
              X  no fill / no submit
```

## Detection strategy

Lever exposes useful stable application signals, so detection uses multiple auditable features rather than fragile CSS classes.

Signals currently include:

- the `jobs.lever.co` host;
- the account/site token and posting UUID URL shape;
- the `/apply` path;
- `lever-source` or `lever-source[]` attribution metadata;
- `lever-origin` metadata;
- a verified Lever-host or Lever-API application form action;
- application-like form structure with common identity/resume controls.

Each signal contributes to a confidence score and is surfaced in `LeverDetection.reasons`.

The default detection threshold remains `0.65`. A verified Lever application action is treated as strong evidence, but a generic relative `/apply` action is deliberately **not** considered Lever evidence. This keeps embedded Lever forms detectable without weakening fail-closed behavior for ordinary careers pages.

## Metadata preservation

When available, `LeverDetection` carries:

- account/site token;
- posting UUID;
- one or more `lever-source` values;
- `lever-origin`;
- whether the selected experience is an `/apply` surface;
- whether the application form was selected from a child frame.

The adapter may recover posting metadata from either document URLs or form actions. This is useful for embedded forms whose frame document URL itself may be `about:srcdoc` or another non-Lever location.

## Hosted and embedded forms

M3.4 reuses the generic document-aware browser inspector introduced for Greenhouse. It does not create a Lever-specific Playwright implementation.

The adapter can therefore select:

- a Lever-hosted top-level application page; or
- an application form embedded inside a child frame on another careers domain.

The generic browser layer continues to own network blocking, submit guards, navigation policy, and frame inspection.

## Application-form isolation

The adapter separates the real candidate application from unrelated search/navigation forms before semantic mapping.

A likely Lever application form may be identified by:

- a verified Lever application action;
- an application-like structural selector plus recognizable candidate controls; or
- a recognizable identity/resume field set together with a submit-capable control.

Document-level Lever confidence must still clear the configured threshold. A generic external application form with action `/apply` is rejected rather than claimed as Lever.

A Lever posting-description page with no application form is also rejected by the preparation adapter. The adapter prepares applications; it does not treat a job-description page as an application simply because its URL is Lever-shaped.

## Policy reuse

Once the application form is isolated, M3.4 delegates field meaning to the generic semantic mapper and review policy.

Examples:

- resume/CV -> verified document resolution;
- full name/email/phone -> verified fact resolution;
- professional links -> verified fact resolution;
- narrative custom questions -> Yellow/draft-with-review;
- salary expectations -> Yellow/draft-with-review;
- work authorization -> Red/human review;
- EEO/demographic controls -> Red/human review;
- consent/attestation controls -> Red/human review;
- unknown custom questions -> escalation or the existing model-assisted review path;
- submit controls -> blocked submit.

## Consent and attestation semantic

M3.4 also adds a generic cross-ATS semantic:

```text
consent_attestation
```

The deterministic mapper recognizes language such as consent, certification/attestation, acknowledgement, privacy-policy agreement, terms, and data-retention permission on appropriate controls.

Consent/attestation always routes to:

- `QuestionCategory.LEGAL_SENSITIVE`;
- `HandlingRoute.HUMAN_REVIEW`;
- `ReviewBand.RED`;
- `requires_human_review=true`.

This is intentionally generic so Greenhouse, Lever, Workday, and later adapters inherit the same policy instead of implementing vendor-specific consent behavior.

## Output contract

`LeverPreparationResult` contains:

- `LeverDetection` with confidence and reasons;
- the isolated `BrowserPageSnapshot`;
- M3.2 `SemanticPageMapping`;
- `SemanticPreparationPlan`;
- `submission_allowed=false`.

## Testing

M3.4 includes real headless Chromium tests for:

- a Lever-hosted `/apply` page;
- source and origin metadata preservation;
- account/site and posting UUID extraction;
- resume, full name, email, phone, professional URL, narrative, authorization, salary, EEO, consent, and submit controls;
- an application embedded in an iframe;
- metadata recovery across the root document and child-form action;
- rejection of a generic external `/apply` form;
- rejection of a Lever posting-description page without an application form;
- blocked submit behavior;
- standalone regression coverage proving consent/attestation remains Red/human-review-required.

CI uses controlled fixtures only and never submits to a live employer.

## Safety boundary

M3.4 does not:

- fill live employer forms;
- upload candidate files to employers;
- click progression or submit controls;
- call Lever's Apply API;
- submit applications;
- infer candidate facts from Lever field names;
- answer consent or legal attestations automatically;
- lower M2 Green/Yellow/Red review requirements;
- automate LinkedIn account actions.

Later M3 work may add controlled preparation actions and audit artifacts behind these same boundaries. Final submission remains a separate explicit gate.
