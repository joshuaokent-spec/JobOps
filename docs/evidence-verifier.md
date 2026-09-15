# Claim-level evidence verification

The evidence verifier audits generated application prose **after drafting and before approval**. Citation presence proves where a draft claims to come from; it does not prove that the wording is actually supported by that evidence.

## Layered authority model

Verification has two layers with intentionally different authority.

### Deterministic checks

High-confidence evidence mismatches can block a draft automatically. The verifier checks:

- draft/evidence job identity;
- resume-family identity;
- cited evidence IDs against the exact retrieval context;
- evidence verification state;
- unsupported numeric and percentage claims;
- unsupported currency claims;
- unsupported named skills and technologies from the controlled technical lexicon;
- unsupported credential, degree, clearance, or license language.

A deterministic blocker ends verification before any semantic model call. This prevents a probabilistic model from talking JobOps out of a concrete evidence failure.

### Optional semantic review

An `LLMProvider` may be supplied as a conservative entailment reviewer. It compares the draft against the cited verified evidence and returns possible unsupported claims.

The semantic layer can only:

- preserve a deterministic pass; or
- escalate a draft to `review`.

It cannot convert a deterministic `block` into a pass, and it is not the sole authority for canonical candidate truth. If the semantic provider is unavailable or malformed, the result escalates to human review rather than silently passing.

This means the same local Foundry model can assist verification without becoming the final policy authority.

## Outcomes

- `pass` — deterministic checks found no blocking mismatch and, when enabled, semantic review raised no concern.
- `review` — no deterministic blocker exists, but semantic verification is unavailable, malformed, or identifies a possible unsupported claim.
- `block` — one or more deterministic evidence violations were detected.

All outcomes remain human-review-required until the approval queue is implemented. Automated verification is a safety filter, not submission permission.

## Why citation containment is not enough

Consider verified evidence that says:

> Built a Python and SQL ETL pipeline processing 500 records daily.

A draft that cites the correct evidence ID but says any of the following is still unsafe:

- “processed 900 records daily”;
- “used Kubernetes to orchestrate the pipeline”;
- “as a certified data engineer...”;
- “saved $2 million annually.”

The verifier treats those as claim inflation rather than accepting them because the citation itself is real.

## Data flow

```text
NarrativeDraftResult
        |
        +---- cited evidence IDs
        |
        v
Exact EvidenceRetrievalResult
        |
        v
Deterministic claim audit
        |
        +---- blocker found ----------> BLOCK
        |
        v
Optional semantic entailment review
        |
        +---- concern/unavailable ----> REVIEW
        |
        v
PASS
        |
        v
Approval Queue (next M2 slice)
```

## Safety limitations and future expansion

The deterministic skill/tool detector intentionally uses a controlled vocabulary rather than pretending that a regular expression understands every possible technology. The semantic layer helps surface subtler paraphrase and implication problems, but its output remains advisory.

Future evaluation data can expand the technical vocabulary and add more structured entity checks without weakening the authority boundary: deterministic contradictions retain veto power, while probabilistic checks remain review-oriented.
