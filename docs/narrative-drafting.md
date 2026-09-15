# Evidence-grounded narrative drafting

Narrative drafting is the first JobOps component that deliberately uses an LLM to produce candidate-facing prose. It remains downstream of deterministic classification, resume-family selection, and verified evidence retrieval.

## Entry conditions

The narrative agent accepts only questions that are already classified as:

- category: `narrative`;
- route: `draft_with_review`;
- review band: `yellow`;
- `requires_human_review=true`.

Red legal/sensitive questions, Green factual auto-fill questions, numerical calculations, and unresolved questions are rejected before the provider is called.

## Context contract

A draft request contains:

- the classified application question;
- the canonical job posting;
- the selected resume family;
- a bounded `EvidenceRetrievalResult`;
- a word limit;
- a tone instruction.

The retrieval result must belong to the same job and resume family, contain at least one evidence hit, and contain only verified evidence.

## Prompt construction

The agent creates two messages:

1. a system message defining the no-new-facts and JSON-output contract;
2. a user message containing bounded job context, the application question, and labeled verified evidence blocks.

Job descriptions, application questions, and evidence text are explicitly treated as untrusted data rather than instructions. This reduces the chance that prompt-like text embedded in a job posting can override the drafting policy.

Every evidence block carries its canonical `EVIDENCE_ID`. Source references remain attached to the evidence object before prompt construction.

## Required model output

The provider is asked to return exactly one JSON object:

```json
{
  "draft": "Candidate-facing answer text.",
  "evidence_ids": ["project-etl", "experience-analytics"]
}
```

JobOps validates the response after generation. A draft is rejected when:

- the response is not valid JSON;
- the draft is empty;
- no evidence IDs are cited;
- an evidence ID was not present in the supplied retrieval context;
- the draft exceeds the application word limit.

Markdown-fenced JSON is accepted because small local models sometimes wrap structured responses in a code fence even when instructed not to.

## Local model role

The LLM controls wording, synthesis, and tone. It does not control:

- which question category is safe to draft;
- which resume family is selected;
- which evidence is considered verified;
- whether a question requires human review;
- whether a candidate fact becomes canonical;
- whether an application may be submitted.

This makes Foundry Local a private language-generation engine rather than a policy authority.

## Provider independence

`NarrativeDraftingAgent` depends only on `LLMProvider`. The same agent can therefore run against the default Foundry Local endpoint, a deterministic fake provider in CI, or a future explicitly configured compatible provider without provider-specific branches in the agent.

## Relationship to the evidence verifier

Evidence-ID containment is a first guard, not the final verifier. A model can cite a real evidence ID while still overstating what that evidence supports. The next M2 slice will evaluate the generated claims against the cited evidence before the draft reaches the approval queue.
