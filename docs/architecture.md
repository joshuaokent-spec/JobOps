# JobOps Architecture

## System intent

JobOps is a decision-support and workflow-automation system, not an indiscriminate application bot. It should increase application quality and throughput while preserving factual accuracy and human control over consequential actions.

## Major bounded contexts

### Ingestion

Collect job postings from supported sources and convert them into one canonical representation. Future adapters should isolate source-specific parsing from downstream logic.

### Knowledge

Maintain a canonical candidate profile and `TruthStore`. Candidate claims should carry verification state, evidence, and risk classification.

### Matching

M0 uses a transparent weighted scorer. Once enough labeled outcomes exist, the learned ranker should be evaluated against this baseline rather than replacing it without evidence.

### Agent orchestration

Agents coordinate tools; they are not themselves the source of truth. Language-model outputs must be treated as proposed text or proposed actions and checked against candidate evidence and policy.

### Application preparation

Application questions should be classified into factual, preference, narrative, and consequential/legal categories. The system can auto-fill low-risk verified facts, draft narrative answers from retrieved evidence, and escalate uncertain or high-risk fields.

### Browser automation

Browser adapters should prepare applications and stop at an explicit approval boundary before final submission. ATS-specific adapters should implement a shared interface and avoid automating websites whose terms prohibit the activity.

### Learning and analytics

Track features, decisions, resume variants, outcomes, and user feedback. Learned models should predict useful quantities such as user-interest likelihood, callback likelihood, and resume-family performance while guarding against leakage and small-sample overfitting.

## Initial score model

The M0 baseline uses:

| Feature | Weight |
|---|---:|
| Title fit | 20% |
| Required skills | 30% |
| Preferred skills | 10% |
| Experience | 15% |
| Compensation | 15% |
| Work mode | 10% |

Weights are intentionally explicit so they can later become features/benchmarks for a supervised ranker.

## Human approval boundary

The intended flow is:

`discover -> normalize -> score -> draft -> verify -> prepare -> REVIEW -> submit -> track`

The REVIEW boundary should remain explicit even after browser automation is introduced.
