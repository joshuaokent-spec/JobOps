# Human approval queue

The approval queue is the final M2 safety and audit boundary between AI-assisted application preparation and future browser automation.

An approval means **approved for preparation**, not submitted. M2 contains no external application-submission action. M3 will retain a separate explicit submit gate even for content that has already been approved here.

## Persistent review record

Each approval item preserves:

- job ID and selected resume family;
- original application question;
- question category, handling route, and review band;
- reason the item entered human review;
- original proposed answer or narrative draft;
- verification status and findings;
- cited evidence IDs;
- separate human-edited answer;
- final approved answer, when applicable;
- reviewer identity and decision note;
- created, updated, and reviewed timestamps;
- durable queue status.

The original model-produced wording is not overwritten by a human edit. This preserves an audit trail between generated text and the answer the candidate actually approved.

## Review reasons

The queue supports review items originating from:

- narrative drafts;
- factual questions that require confirmation;
- candidate preferences;
- legal or sensitive questions;
- evidence-verifier review findings;
- unresolved or escalated questions.

A verifier result of `block` cannot enter the approvable queue. Blocked content must be corrected or regenerated first.

## States

```text
pending
  |
  +--> approved
  +--> rejected
  +--> revision_required
```

A pending item may receive exactly one substantive decision. Repeating the exact same decision is idempotent so retried API requests do not create a conflicting state. A different second decision is rejected as an invalid transition.

`revision_required` is terminal for that specific proposed answer. A corrected/regenerated proposal should enter the queue as a new review item so the original review record remains auditable.

## Approval rules

Approving an item requires:

- an explicit reviewer;
- an explicit decision note;
- either an existing proposed answer or a human-edited answer.

When a human edit is supplied, that edited text becomes the final approved answer. Otherwise the original proposed answer becomes the final approved answer.

Rejected and revision-required items do not receive a final approved answer.

## API

The M2 API exposes:

```text
POST /v1/approvals
GET  /v1/approvals
GET  /v1/approvals/{approval_id}
POST /v1/approvals/{approval_id}/decision
```

Queue listings can be filtered by status and job ID. Results use stable creation-time ordering.

There is intentionally no submit endpoint in this router.

## Database boundary

Approval items are persisted in PostgreSQL through the `approval_items` table and linked to canonical jobs by foreign key. Generated content, verification findings, evidence IDs, edits, decisions, and timestamps therefore survive process restarts and can later support analytics and auditing.

## M2-to-M3 handoff

M2 ends when an answer is safely prepared and explicitly approved. M3 may later consume an approved item for browser form preparation, but must still enforce its own final submission gate.

```text
Question classification
        |
Verified evidence retrieval
        |
Local/cloud-pluggable draft generation
        |
Claim-level evidence verification
        |
Persistent human approval queue
        |
        v
APPROVED FOR PREPARATION
        |
        X  no submission in M2
        |
        v
M3 browser preparation + separate submit gate
```
