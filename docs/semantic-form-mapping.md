# Semantic form-field mapping

M3.2 turns the structural browser snapshot from M3.1 into typed application semantics without filling or submitting the browser.

## Boundary

The semantic mapper answers one question: **what does this form control appear to ask for?**

It does not decide what the candidate's answer should be, create candidate facts, or bypass M2 review policy. Candidate values still come from verified evidence, preferences, approved drafts, or explicit human review.

The pipeline is:

```text
Employer / ATS HTML
        |
        v
Guarded Playwright inspection
        |
        v
BrowserPageSnapshot
        |
        v
SemanticFieldClassifier
        |
        +--> deterministic mapping
        |
        +--> optional model-assisted fallback for unresolved fields
        |
        v
SemanticPageMapping
        |
        v
M2 Green / Yellow / Red policy
        |
        v
SemanticPreparationPlan
        |
        X  no browser write or submission in M3.2
```

## Supported semantic categories

The current typed vocabulary includes:

- identity/contact: first name, last name, full name, email, phone, street address, city, region, postal code, country;
- professional links: LinkedIn URL as a data value only, GitHub URL, portfolio URL, personal website;
- documents: resume/CV and cover letter;
- preferences: salary/compensation, relocation, work mode, travel, start date;
- consequential factual fields: work authorization, sponsorship, prior employment, certifications, education, security clearance;
- open-ended narrative questions;
- demographic / EEO / self-identification controls;
- submit controls;
- unresolved/unknown controls.

## Deterministic-first classification

`SemanticFieldClassifier` uses browser-visible structure and text such as:

- label;
- accessible name;
- `name` and `id`;
- placeholder;
- input type and field kind;
- select/radio option labels.

Known mappings include a confidence score and matched signals. If two competing semantic rules are effectively tied, the field becomes `UNKNOWN` with `ambiguous=true` rather than silently choosing one interpretation.

Unknown controls remain unresolved. The system does not infer a candidate answer merely because a field looks similar to something known.

## M2 policy reuse

Semantic mappings reuse the same application-question policy concepts already established in M2:

### Green

Ordinary factual mappings may route to verified fact resolution, for example:

- first/last/full name;
- email and phone;
- address components;
- GitHub/portfolio/website URLs;
- resume document selection;
- education or certifications when backed by verified facts.

Green means the field may eventually resolve from verified candidate data. It does **not** mean the browser may currently submit anything.

### Yellow

Preference or narrative mappings require review, including:

- salary expectations;
- relocation;
- remote/hybrid/on-site preference;
- travel;
- start date;
- narrative prompts;
- cover-letter content.

### Red

Consequential or sensitive mappings require explicit human review, including:

- work authorization;
- sponsorship;
- prior employment attestations;
- security clearance;
- demographic / EEO / self-identification questions;
- unknown or ambiguous fields;
- submit controls.

## Optional model-assisted fallback

`AssistedSemanticFieldClassifier` may use the existing provider-neutral `LLMProvider` only when deterministic classification leaves a field unresolved.

The fallback receives form-control metadata only and is instructed to classify the field, never answer it or infer candidate facts.

Safety rules are asymmetric:

- deterministic matches are not replaced by model guesses;
- invalid or low-confidence model output leaves the field unresolved;
- model-assisted ordinary mappings are capped at Yellow and require review;
- model-assisted sensitive mappings remain Red;
- the model cannot downgrade a sensitive field to an autofill path;
- `SUBMIT_CONTROL` and `UNKNOWN` are not model-selectable application semantics.

This makes local/NPU inference useful for unusual ATS wording without granting it authority over consequential actions.

## Semantic preparation plan

`SemanticPreparationPlanner` converts semantic mappings into non-executing preparation operations:

- `resolve_fact` — locate a verified candidate fact or document;
- `draft_with_review` — use the existing M2 draft/review workflow;
- `human_review` — require an explicit person decision;
- `escalate` — unresolved meaning must not be guessed;
- `blocked_submit` — submit-capable controls remain unavailable.

`submission_allowed` remains `false` for the entire M3.2 plan.

## LinkedIn boundary

A LinkedIn profile URL may be treated as a candidate data field on an employer's application form. JobOps still does not automate LinkedIn account actions or navigate LinkedIn as part of the ATS browser layer.

## Testing

M3.2 includes:

- deterministic mapping tests for ordinary, preference, narrative, sensitive, demographic, unknown, and submit fields;
- ambiguity tests;
- model-assisted fallback tests using fake providers rather than live model downloads;
- preparation-plan tests proving M2 routing is preserved;
- a real headless Chromium integration test that inspects controlled HTML with M3.1 and feeds the resulting `BrowserPageSnapshot` into M3.2 semantic classification.

CI therefore validates both the pure domain mapping and the real browser-to-semantic boundary.

## What M3.2 intentionally does not do

M3.2 does not:

- fill live employer forms;
- upload candidate documents to employers;
- click application progression controls;
- execute final submission;
- invent or infer missing candidate facts;
- turn model-assisted classifications into Green autofill decisions.

Those capabilities must be added incrementally behind the existing approval and submit gates in later M3 slices.
