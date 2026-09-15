# Application question classification and review routing

JobOps classifies application questions **before** any answer-generation component runs. The classifier is a deterministic policy boundary: it identifies the question type, risk, handling route, and review priority, but it does not answer the question or create candidate facts.

## Categories

- `factual` — maps to an atomic candidate fact such as education, certifications, or portfolio links.
- `numerical` — should be answered by deterministic calculation rather than language generation.
- `preference` — salary, relocation, work mode, travel, start date, and similar contextual preferences.
- `narrative` — open-ended prompts that may later be drafted from retrieved evidence.
- `legal_sensitive` — work authorization, sponsorship, security clearance, legal attestations, protected/sensitive self-identification, and similarly consequential fields.
- `unknown` — no deterministic rule matched confidently enough to automate.

## Review bands

### Green

Green questions are safe for deterministic preparation. A factual question reaches Green only when it maps to a verified, low-risk `TruthStore` fact. Numerical questions may also route to Green when the answer can be computed deterministically.

### Yellow

Yellow questions require a draft or candidate confirmation. Preferences and narrative prompts are Yellow by default because their best answer can depend on context even when supporting facts exist.

### Red

Red questions require human review. Legal/sensitive questions are always Red even if JobOps has a verified value. Unknown or unresolved questions also escalate to Red instead of being guessed.

## TruthStore integration

`TruthStore.resolve()` deliberately distinguishes **known** from **safe to auto-answer**. A fact can exist and still require review when it is unverified or high-risk. The classifier carries that decision forward instead of treating fact availability as permission to submit it.

This is especially important for fields such as:

- work authorization and sponsorship;
- security clearance;
- criminal-history or prior-employment attestations;
- protected or sensitive self-identification;
- other consequential legal declarations.

## Separation from LLM generation

The classifier is intentionally model-independent. Future LLM providers may help draft Yellow narrative answers, but they do not get to override the classifier's route or risk level. A local or cloud model therefore remains downstream of deterministic policy controls.

The intended flow is:

```text
Raw application question
        |
        v
Rule-based classification
        |
        +--> factual ----------> TruthStore resolution
        |                            |
        |                            +--> verified low-risk -> Green / auto-fill
        |                            +--> review required ---> Yellow/Red
        |
        +--> numerical --------> deterministic calculation
        +--> preference -------> Yellow / draft-with-review
        +--> narrative --------> Yellow / evidence-grounded draft
        +--> legal/sensitive --> Red / mandatory human review
        +--> unknown ----------> Red / escalate
```

## Evaluation seam

The current rule classifier is an explainable baseline. Future learned or LLM-assisted classifiers can be evaluated against the same typed result contract, but any replacement must preserve the policy invariant that high-consequence or unresolved questions cannot silently bypass human review.
