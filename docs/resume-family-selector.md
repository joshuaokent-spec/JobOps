# Explainable Resume-Family Selector

M2.2 adds a deterministic baseline for choosing which resume family should be used for a canonical job posting.

The selector does **not** write resume bullets and does not create candidate facts. Its job is narrower: choose the most relevant family and expose the verified evidence candidate pool available to downstream retrieval and drafting stages.

## Why a transparent baseline first

An LLM could be asked to choose between `data-engineer`, `data-scientist`, `ai-engineer`, and `analytics`, but that would make selection difficult to reproduce, evaluate, and train against later.

`ExplainableResumeFamilySelector` instead produces explicit features for every family. Those feature vectors can later become training data for the learned resume-selection model planned in M4.

## Feature vector

Each family is scored using four normalized features:

| Feature | Weight | Meaning |
| --- | ---: | --- |
| `title_role_fit` | 0.40 | Token overlap between the posting title and known aliases for the family's role categories |
| `priority_skill_fit` | 0.25 | Fraction of the family's priority skills found in explicit job skills or job text |
| `evidence_skill_coverage` | 0.20 | Fraction of explicit job skills demonstrated by verified evidence available to the family |
| `evidence_depth` | 0.15 | Amount of verified evidence available, capped at a configurable target |

The weighted value is converted to a 0–100 family score.

These weights are intentionally simple and auditable. They are a baseline, not a claim of optimal hiring-market behavior.

## Role aliases

The baseline contains small role-alias sets for:

- Data Engineering;
- Data Science;
- AI / ML Engineering;
- Analytics;
- Software Engineering;
- General roles.

For example, the Data Engineering category recognizes title patterns such as `Data Engineer`, `ETL Engineer`, `Data Platform Engineer`, and `Analytics Engineer`. The AI/ML category recognizes titles such as `Machine Learning Engineer`, `ML Engineer`, `AI Engineer`, `MLOps Engineer`, and `Applied Scientist`.

Later semantic or learned selection can replace this alias logic without changing the result contract.

## Evidence-aware selection

Family scoring is not based only on the job description. The selector asks `ResumeEvidenceStore` for the verified candidate pool available to each family.

This gives the selector a useful distinction:

> A family can look linguistically appropriate while still having weak evidence support.

The selector therefore exposes the evidence IDs used to compute each family candidate. Unverified evidence is not included in the candidate pool.

## Stable decisions

All family candidates are sorted by descending score with `family_id` as the deterministic tie-breaker. Running the same selector over the same job and evidence base therefore produces the same result.

## Confidence and fallback

The selector accepts a configurable `minimum_confidence` in the range 0–1.

If the best score is below that threshold, the result is marked `low_confidence`. A configured fallback family may then be used. The result reports both `low_confidence` and `used_fallback`, so fallback behavior is visible rather than silently changing the decision.

This is useful for sparse or unusual postings where the role cannot be classified reliably from the available structured/text signals.

## Result contract

`ResumeFamilySelection` returns:

- selected family ID;
- selected score;
- configured minimum confidence;
- low-confidence flag;
- fallback-use flag;
- the complete ordered list of family candidates.

Each `ResumeFamilyScore` contains:

- family ID/name;
- total score;
- typed feature vector;
- verified evidence IDs available to that family;
- human-readable reasons for the feature values.

## Evaluation path

The repository includes fixture postings for Data Engineering, Data Science, AI/ML Engineering, Analytics, and an intentionally ambiguous technical role. Tests verify correct family selection, stable tie-breaking, low-confidence fallback behavior, repeatability, and the exclusion of unverified evidence.

In M4, application outcomes can provide labels such as selected family, recruiter response, interview, and offer. A learned selector can then be compared against this deterministic baseline using the same family/evidence result boundary.

## Separation from drafting

Selection and wording are separate concerns:

```text
Canonical Job
     |
     v
Resume-Family Selector
     |
     +----> chosen family
     +----> feature breakdown
     +----> verified evidence pool
                 |
                 v
         Retrieval / Drafting
                 |
                 v
          Evidence Verifier
```

The selector may rank evidence, but it never invents a resume claim.
