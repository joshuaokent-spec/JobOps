# Evidence Retrieval for Job-Grounded Drafting

M2.3 defines the retrieval boundary between the candidate evidence base and future resume/application generation.

The resume-family selector answers **which family should represent the candidate for this job?** The evidence retriever answers **which verified facts from that family should be allowed into the drafting context?**

## Safety boundary

`EvidenceRetriever` never creates a qualification, rewrites a claim, or promotes unverified data. It ranks existing `ResumeEvidenceItem` records returned by `ResumeEvidenceStore.for_family(..., verified_only=True)` and returns the original evidence objects with their provenance intact.

That makes the retrieval result suitable for RAG: downstream generation receives a bounded context of traceable evidence rather than an unrestricted candidate history.

## Deterministic baseline

Without an embedding provider, each evidence item is scored from four normalized features:

| Feature | Weight | Meaning |
| --- | ---: | --- |
| `lexical_fit` | 0.30 | Token overlap between the job's title/skills and the evidence retrieval representation |
| `skill_fit` | 0.40 | Fraction of explicit required/preferred job skills demonstrated by the evidence item |
| `family_fit` | 0.20 | Alignment between the selected resume family's role categories and the evidence item's role categories |
| `specificity` | 0.10 | Density of concrete signals such as skills, metrics, organization, and title |

The baseline is deliberately transparent. Every hit includes its feature vector, total score, and human-readable reasons.

## Optional semantic blend

M2.3 reuses the `EmbeddingProvider` interface introduced for M1 semantic deduplication. No second vector-provider abstraction is introduced.

When a provider is supplied, the job and candidate evidence are embedded in one batch. Cosine similarity is blended with the deterministic score using a configurable `semantic_weight` (default `0.35`).

When no provider is supplied, retrieval remains fully functional with the default dependency set. This keeps CI and ordinary local development free of neural-model downloads.

## Bounded context

The retriever accepts a `limit` and returns at most that many evidence hits. This is intentional context-window discipline: later drafting agents should receive the strongest small set of evidence rather than the complete candidate record.

## Evidence-kind diversity

A purely score-sorted list can be dominated by several near-identical skill records. `max_per_kind` therefore limits how many items of one evidence kind may enter the first selection pass. Deferred high-scoring items are used afterward if space remains.

This preserves relevance while encouraging a drafting context that can include, for example, a project plus a skill rather than only multiple skill records.

## Provenance preservation

Each `EvidenceRetrievalHit` nests the original `ResumeEvidenceItem`. The evidence ID, source references, verification state, metrics, skills, dates, and other structured fields remain available to downstream components.

The result contract also records:

- canonical job ID;
- selected resume-family ID;
- retrieval limit;
- number of candidate evidence items considered;
- semantic model name when semantic retrieval is enabled;
- per-hit relevance features, total score, and reasons.

## Retrieval flow

```text
Canonical Job
     |
     v
Resume-Family Selector
     |
     v
Selected Resume Family
     |
     v
ResumeEvidenceStore (verified only)
     |
     v
EvidenceRetriever
  /        \
 lexical   optional embeddings
  \        /
   ranked + diversified
          |
          v
Bounded Evidence Context
          |
          v
Future Drafting Agent
          |
          v
Future Evidence Verifier
```

## Evaluation

Tests cover:

- Data Engineering evidence ranking;
- preservation of verification and provenance;
- optional semantic blending with a deterministic fake embedding provider;
- evidence-kind diversity;
- stable, bounded, reproducible retrieval.

Later M2/M4 work can add labeled relevance judgments and application outcomes to evaluate learned or semantic retrieval against this deterministic baseline.

## Core rule

**Retrieval decides which existing verified evidence is relevant. It does not decide what new facts are true.**
