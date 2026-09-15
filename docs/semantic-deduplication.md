# Semantic Near-Duplicate Detection

JobOps uses two separate duplicate-detection layers because exact identity and semantic similarity solve different problems.

## Deterministic layer

The deterministic layer remains authoritative. It uses stable source identity and a normalized cross-source fingerprint. A deterministic match can be explained entirely from structured fields and does not require a model.

## Semantic layer

The semantic layer handles cases where the same vacancy appears with wording drift across ATS feeds, for example:

- `Senior Data Engineer` vs. `Sr. Data Platform Engineer`;
- abbreviation changes such as `Business Intelligence Analyst` vs. `BI Analyst`;
- rewritten descriptions that preserve the same underlying responsibilities.

Semantic matches are **candidates for review**, not automatic merges. JobOps preserves both source records and their provenance.

## Representation

`JobEmbeddingTextBuilder` converts a canonical `JobPosting` into a deterministic text representation containing, when available:

- company;
- title;
- location;
- work mode;
- employment type;
- required skills;
- preferred skills;
- a bounded description window.

The representation is provider-neutral. An embedding provider only needs to implement the `EmbeddingProvider` protocol.

## Default local provider

The optional local implementation uses Sentence Transformers. It is intentionally not part of the default dependency set so CI and non-ML installations do not download a neural model.

```bash
pip install -e ".[ml]"
```

The default model configured by the CLI is:

```text
sentence-transformers/all-MiniLM-L6-v2
```

A different compatible provider or model can be substituted without changing duplicate-detection policy.

## Candidate generation

JobOps does not perform an unconstrained all-pairs semantic comparison. Jobs are first blocked by normalized company identity, then compared inside those blocks. By default, known postings from the same source are skipped so the semantic layer focuses on cross-source duplication.

Deterministic matches are resolved before semantic scoring. Only remaining candidate pairs require embeddings.

## Threshold policy

The default semantic threshold is `0.84`, but it is a baseline rather than a magic constant. Thresholds should be calibrated against labeled examples because the tradeoff is asymmetric:

- lowering the threshold increases recall but may suggest unrelated roles at the same company;
- raising it increases precision but can miss heavily rewritten copies of the same vacancy.

The repository includes a small labeled example dataset containing positive and hard-negative pairs. It is intentionally synthetic and is a starting point for the evaluation pipeline, not a claim of production-quality calibration.

Evaluate a threshold grid with:

```bash
jobops-semantic-dedup evaluate \
  --dataset data/evaluation/semantic-duplicate-pairs.example.json
```

The report contains pair-level similarity plus precision, recall, F1, confusion counts, and the best threshold on the supplied evaluation set.

As real JobOps review decisions accumulate, the synthetic evaluation set should be supplemented with adjudicated examples from actual feeds.

## Scanning stored jobs

After installing the optional ML dependencies and configuring the database:

```bash
jobops-semantic-dedup scan --threshold 0.84
```

The command emits structured JSON containing:

- jobs scanned;
- company blocks;
- pairs considered;
- semantic pairs scored;
- deterministic matches;
- semantic matches;
- each candidate's match type, similarity, model, threshold, and reasons.

The command does not mutate, merge, or delete jobs.

## Auditability

Every duplicate candidate identifies whether it came from deterministic or semantic matching. Semantic candidates retain the similarity score, threshold, provider/model name, and human-readable reasons. This keeps model output inspectable and allows future review decisions to become labeled ML data rather than silently changing the job store.
