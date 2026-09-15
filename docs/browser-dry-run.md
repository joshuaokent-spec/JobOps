# Guarded browser dry-run inspection

M3.1 introduces Playwright as JobOps' browser-automation boundary, but deliberately stops before form filling or submission. The browser layer may navigate to an employer/ATS page, inventory native form controls, and produce a typed preparation plan. It does not receive authority to submit an application.

## Installation

Browser automation is an optional dependency:

```bash
pip install -e ".[browser]"
python -m playwright install chromium
```

CI installs the `browser` extra and a real Chromium binary, so the guarded inspection tests run against an actual browser rather than only mocks.

## Typed inspection contract

`PlaywrightBrowserInspector` returns a `BrowserPageSnapshot` containing:

- page URL and title;
- forms, methods, actions, and stable selectors where available;
- native input, textarea, select, button, checkbox, radio, and file controls;
- labels, names, placeholders, accessible names, required/disabled state, and select options;
- submit-capable controls as inventory metadata;
- count of network requests blocked by the dry-run guard.

The orchestration layer receives this typed snapshot rather than a raw Playwright `Page` object.

## Dry-run planning

`BrowserDryRunPlanner` converts structural field metadata into non-executing operations:

- text-like fields -> `fill`;
- selects -> `select`;
- checkboxes/radios -> `choose`;
- file controls -> `upload`;
- disabled/hidden controls -> `skip`;
- unknown controls -> `review`;
- submit controls -> `blocked_submit`.

The plan always reports `submission_allowed=false` in M3.1.

This is structural detection only. The next generic form-field slice will map discovered controls to semantic application concepts such as first name, work authorization, portfolio URL, salary expectation, and narrative questions.

## Submission safety

`BrowserSessionConfig.allow_submit` defaults to `false`.

When the gate is closed, the Playwright adapter layers several protections:

1. document-level submit events are prevented;
2. `HTMLFormElement.submit()` and `requestSubmit()` are replaced by blocking guards;
3. mutating HTTP methods (`POST`, `PUT`, `PATCH`, `DELETE`) are aborted at the browser-context routing layer;
4. document navigations that occur after the inspected page finishes its initial load are aborted;
5. JobOps' exposed `submit_form()` call raises `SubmissionBlockedError`.

Even if `allow_submit=true` is constructed manually, M3.1 still does not implement form submission and raises a policy error. A later M3 slice must add a distinct explicit submit gate rather than silently activating this method.

## Navigation policy

M3 browser automation targets employer and ATS application pages. LinkedIn navigation is rejected by the adapter rather than treating a LinkedIn account session as an ATS integration.

Only HTTP(S) navigation is accepted. `data:`, `javascript:`, `file:`, and other non-web URL schemes are rejected before browser launch.

## Browser isolation

Each inspection uses a fresh non-persistent Playwright browser context. Service workers are blocked by default so network routing remains an effective audit/safety boundary.

The browser instance is closed after each inspection. M3.1 does not persist cookies, authenticated state, or browser storage.

## CI fixture

The test suite launches Chromium against a controlled HTML application form containing text, email, select, checkbox, file, textarea, and submit controls. The fixture also attempts a POST request; CI verifies that the request is blocked while the form can still be inspected and planned.

This gives the repository a real browser-execution proof without interacting with any live employer or ATS site during tests.

## M3.1 boundary

```text
Approved M2 content
       |
       v
Employer / ATS page
       |
       v
Guarded Playwright context
       |
       v
Structural form snapshot
       |
       v
Dry-run preparation plan
       |
       X  no fill/submit execution in M3.1
       |
       v
Future semantic field mapping + ATS adapters
```
