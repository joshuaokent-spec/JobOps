# Workday browser prototype

M3.5 models Workday external applications as **stateful workflows**, not as one large HTML form.

The prototype is intentionally non-executing. It can identify a likely Workday application context, classify the visible wizard step, map visible candidate controls through the existing JobOps semantic/review policy, inventory progression/account actions, and produce a typed preparation result. It cannot advance the wizard or perform employer-side writes.

## Why Workday is different

Greenhouse and Lever can often be represented as one selected application document/form. Workday's current external-career-site documentation describes an application wizard that can contain contact information, experience, application questions, voluntary disclosures, terms and conditions, and final review. Workday also supports Candidate Home, configurable account requirements, Quick Apply/resume parsing, and Apply with LinkedIn.

Most importantly for the browser safety model, Workday documents that external applications are automatically saved when a candidate selects **Next**. Candidate Home can display those saved draft applications. That means `Next` is not safely equivalent to read-only navigation: advancing the wizard can create or update candidate-side state in the employer's Workday tenant.

References used for this prototype:

- [Workday — Career Sites](https://doc.workday.com/workday-education/en-us/course-manuals/recruiting-for-administrators/career-sites.html)
- [Workday — Prospects and Candidates](https://doc.workday.com/workday-education/en-us/course-manuals/recruiting-for-administrators/prospects-and-candidates.html)
- [Workday — Steps: Set Up External Career Sites](https://doc.workday.com/admin-guide/en-us/human-capital-management/recruiting/career-sites/san1431625385171.html)
- [Workday — Populate Job Applications with LinkedIn Profile](https://doc.workday.com/admin-guide/en-us/human-capital-management/recruiting/career-sites/uph1530136584993.html)
- [Workday — Create External Career Sites](https://doc.workday.com/admin-guide/en-us/human-capital-management/recruiting/career-sites/san1394588983205.html)

## Shared browser capability added in M3.5

The guarded Playwright inspector now records more than native forms. A `BrowserPageSnapshot` can include:

- visible headings;
- page-level buttons, links, and button-role controls;
- action text and accessible names;
- hrefs when the action is a link;
- disabled state;
- stable selectors;
- the existing form/field inventory.

This is still observation only. Recording that a `Next` button exists does not make the button executable.

Meaningful child frames are retained when they contain forms, headings, or page actions. This matters for embedded wizard states such as final review or account access that may have no native `<form>` element.

## Typed workflow model

`WorkdayPreparationResult` contains:

- `WorkdayDetection` — vendor/context confidence, reasons, selected document, embedding state, and available metadata;
- `WorkdayWizardStep` — the visible wizard-state category and deterministic evidence;
- `BrowserPageSnapshot` — the inspected document/frame;
- the existing `SemanticPageMapping`;
- the existing non-executing `SemanticPreparationPlan`;
- `WorkdayBlockedAction[]` — visible actions that are consequential or out of scope;
- explicit `progression_allowed = false`;
- explicit `live_writes_allowed = false`;
- explicit `submission_allowed = false`.

### Wizard step categories

The prototype recognizes these categories:

- `account_access`
- `resume`
- `contact_information`
- `experience`
- `application_questions`
- `voluntary_disclosures`
- `terms_consent`
- `final_review`
- `unknown`

Classification is deterministic-first. Headings provide strong evidence, while existing M3.2 semantic mappings provide secondary evidence. The prototype does not ask a language model to invent or advance workflow state.

## Consequential action inventory

Visible page actions can be classified into blocked operations:

| Operation | Prototype behavior | Reason |
| --- | --- | --- |
| `next` | blocked | Workday may save/update the application draft when the wizard advances. |
| `save_for_later` | blocked | Explicit draft persistence is an employer-side write. |
| `sign_in` | blocked | Candidate Home authentication is outside the prototype boundary. |
| `create_account` | blocked | Account creation is outside the prototype boundary. |
| `apply_with_linkedin` | blocked | LinkedIn account automation is outside JobOps ATS automation scope. |
| `submit` | blocked | Final submission remains behind a future explicit submission gate. |
| `other_progression` | blocked | Stateful progression is not executable until its write behavior is modeled. |

The blocked-action list is an audit artifact, not an execution queue.

## Detection model

The current prototype uses multiple signals rather than a single selector:

- known Workday external-career host suffixes observed in current public deployments;
- Workday-style `/job/` paths;
- known wizard headings;
- write-relevant wizard controls;
- candidate-entry controls such as resume/CV, identity/contact, authorization, demographic, or consent fields;
- source attribution when present.

A Workday-looking URL alone is insufficient. Ordinary Workday job-detail pages commonly contain global **Apply** and **Sign In** controls, so those controls are not treated as proof that the application wizard has started.

For controlled embedded-frame cases, a meaningful child frame may inherit already-verified Workday parent context and metadata. The child still needs actual application-context evidence; arbitrary child frames are not claimed merely because their parent is Workday-hosted.

## Metadata

When reliably derivable, detection preserves:

- tenant/account hostname prefix;
- career-site path segment;
- locale;
- requisition identifier parsed from a posting slug;
- `source` query attribution.

These values are audit metadata. Host/path/requisition parsing is a **prototype heuristic**, not a universal Workday API contract, and must fail gracefully when a tenant uses a different public shape.

## Semantic and review-policy reuse

M3.5 does not create a second answer policy. Visible controls continue through the existing semantic classifier and M2 review routing.

Examples:

- verified ordinary contact facts may remain Green fact-resolution candidates;
- narrative application questions remain Yellow draft-with-review;
- work authorization and sponsorship remain Red human review;
- demographic/EEO/self-identification remains Red;
- consent/attestation remains Red;
- unknown/ambiguous controls remain Red/escalated.

ATS-specific code cannot downgrade those requirements.

## Candidate Home boundary

The prototype may recognize Candidate Home, Sign In, Create Account, or similar account-access states. It does not:

- create an account;
- enter account credentials;
- sign in;
- recover/reset credentials;
- reuse an authenticated browser session;
- accept account-creation consent.

A later implementation would need a separately reviewed authentication/session design.

## LinkedIn boundary

Workday supports Apply with LinkedIn / LinkedIn-assisted population in configured external career sites. JobOps may recognize those controls as UI state, but LinkedIn account/browser automation remains out of scope. The prototype emits a blocked `apply_with_linkedin` action and does not interact with the control.

## Controlled test matrix

M3.5 uses controlled real-Chromium fixtures for representative states:

- initial resume/CV step;
- My Information/contact information;
- My Experience with education/document fields;
- Application Questions;
- Voluntary Disclosures;
- Terms and Conditions;
- Candidate Home/account access;
- Apply with LinkedIn boundary;
- Final Review with no form;
- embedded final review in a child frame;
- ordinary Workday job-detail false-positive rejection;
- non-Workday lookalike rejection.

No fixture depends on making a live employer-side write.

## What M3.5 proves

The portfolio point is not that JobOps can click through Workday. It is that the automation architecture recognizes when **clicking itself changes the risk model**.

M3.5 demonstrates:

- stateful workflow modeling;
- separation of read-only observation from write-capable progression;
- cross-step semantic reuse;
- vendor-specific detection without vendor-specific answer policy;
- embedded UI handling;
- auditable blocked actions;
- false-positive resistance;
- explicit account/social/submission boundaries.

## Later executable Workday slice

A later Workday implementation may add controlled field preparation only after the workflow/write boundary is evaluated. Any capability that advances the wizard must distinguish at minimum:

1. local browser-only edits that have not been transmitted;
2. employer-side draft writes;
3. authentication/account operations;
4. consent/attestation decisions;
5. final application submission.

Those are separate consequential operations and should not be collapsed into one generic `click()` capability.
