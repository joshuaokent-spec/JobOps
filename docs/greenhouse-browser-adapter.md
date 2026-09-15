# Greenhouse browser adapter

M3.3 adds the first ATS-specific browser preparation adapter on top of the guarded M3.1 Playwright inspector and M3.2 semantic field mapper.

## Purpose

The Greenhouse adapter identifies a Greenhouse application context, isolates the application form from unrelated page controls, preserves Greenhouse source metadata when available, and routes the resulting form through existing JobOps semantic and review policy.

It does not create a second browser engine and it does not submit applications.

```text
Greenhouse-hosted or embedded careers page
                    |
                    v
        Guarded Playwright inspection
          /                     \
   top document             child frames
          \                     /
                    v
        Greenhouse context detection
                    |
                    v
        isolate application form(s)
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

Greenhouse can appear in more than one deployment shape, so detection uses multiple auditable signals instead of a single hostname check.

Signals currently include:

- a `greenhouse.io` host;
- `gh_jid` job metadata;
- `gh_src` source-tracking metadata;
- the conventional `#application_form` selector;
- Greenhouse-style `job_application[...]` field names;
- application actions that look Greenhouse-specific, including `/applications`.

Each matching signal contributes to a confidence score and is recorded in `GreenhouseDetection.reasons`. The highest-confidence document is selected only when it contains an application form and clears the configured confidence threshold. Otherwise the adapter fails closed with `GreenhouseDetectionError`.

## Hosted and embedded forms

The generic Playwright inspector now exposes document-level inspection methods in addition to the original single-page methods:

- `inspect_url_documents()`;
- `inspect_html_documents()`.

They return the top document plus child frames that contain forms. The original `inspect_url()` and `inspect_html()` interfaces remain backward-compatible and continue returning the top document.

This allows ATS adapters to handle embedded application forms without duplicating Playwright logic. Submission guards and network protections remain owned by the generic inspector and apply to the shared browser context.

## Metadata preservation

When present, the adapter carries forward:

- Greenhouse job ID from `gh_jid`, `job_id`, or a supported Greenhouse job URL path;
- Greenhouse source token from `gh_src`;
- board token when it can be inferred from a Greenhouse-hosted path.

This metadata is descriptive and audit-oriented. It does not authorize any browser action.

## Application-form isolation

Careers pages may contain search, filtering, newsletter, or other forms in addition to the actual application form. M3.3 isolates likely application forms before semantic mapping so decorative controls do not become candidate-answer tasks.

A form may qualify through Greenhouse-specific signals such as:

- `#application_form`;
- Greenhouse field naming;
- Greenhouse-like form action.

Common identity-field structure may help identify a candidate form, but a generic external careers page is not claimed as Greenhouse unless the document-level Greenhouse confidence threshold is also met.

## Policy reuse

After the application form is selected, the adapter delegates semantic meaning to M3.2 rather than implementing ATS-specific answer policy.

Examples:

- first name or email -> verified fact resolution path;
- resume/CV -> verified document resolution path;
- sponsorship or work authorization -> Red/human-review path;
- narrative custom questions -> Yellow/draft-with-review path;
- unknown custom questions -> unresolved/escalation path;
- submit controls -> blocked submit path.

The adapter therefore cannot downgrade M2 or M3.2 safety policy.

## Output contract

`GreenhousePreparationResult` contains:

- `GreenhouseDetection` with confidence and reasons;
- the isolated `BrowserPageSnapshot`;
- the M3.2 `SemanticPageMapping`;
- the `SemanticPreparationPlan`;
- `submission_allowed=false`.

This makes ATS detection, UI interpretation, and policy routing independently inspectable.

## Testing

M3.3 includes real headless Chromium tests for:

- a Greenhouse-hosted application page;
- a careers page containing both decorative/search and application forms;
- an application embedded in an iframe using controlled `srcdoc` content;
- preservation of job/source metadata across a root page and child frame;
- semantic routing for ordinary and sensitive fields;
- blocked submit controls;
- rejection of a generic non-Greenhouse application form.

CI interacts only with controlled fixtures. It does not submit applications to live employers.

## Safety boundary

M3.3 does not:

- fill live employer forms;
- upload documents to an employer;
- click progression or submit controls;
- submit an application;
- infer missing candidate facts from Greenhouse field names;
- override Green/Yellow/Red review policy;
- automate LinkedIn account actions.

Later M3 slices may add controlled preparation actions behind the same policy boundaries, with final submission remaining a separate explicit gate.
