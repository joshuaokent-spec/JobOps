# Resume Evidence Model

M2 introduces a candidate-side evidence model so resume tailoring and application drafting can use rich career context without turning generated wording into a source of truth.

## Two evidence layers

JobOps deliberately separates two kinds of candidate knowledge.

### `TruthStore`

`TruthStore` remains the authority for atomic application facts such as a known preference, a verified status, or a standard answer. Its safety rule is unchanged: a fact can be known while still requiring human review because it is unverified or high-risk.

### `ResumeEvidenceStore`

`ResumeEvidenceStore` holds richer factual career evidence used for resumes and retrieval. Examples include:

- work accomplishments;
- projects;
- education;
- certifications;
- demonstrated skills;
- measurable achievements.

Each reusable evidence item has a stable evidence ID and provenance references. Verified evidence cannot exist without at least one source reference.

## Canonical evidence vs. generated wording

`ResumeEvidenceItem.claim` is canonical factual evidence. It is not an LLM-generated resume bullet.

Future resume and application agents may rewrite, shorten, combine, or reorder evidence for a specific role, but generated wording must retain the IDs of the evidence that supports it. Generated text is presentation; the evidence base remains factual state.

A `VerifiedResumePayload` therefore contains approved evidence IDs rather than treating generated prose as verified truth.

## Evidence sources

Sources are modeled separately from claims so one artifact can support many claims and one claim can cite multiple artifacts. Supported source categories include documents, project artifacts, employment records, education records, certification records, self-attested evidence, and other sources.

The public repository contains sanitized examples only. Private candidate documents, employment records, transcripts, contact information, and similar personal data should remain outside Git.

## Resume families

Role-specific resumes are definitions over the same master evidence base rather than duplicated resume files.

A `ResumeFamilyDefinition` contains:

- target role families;
- priority skills;
- optionally pinned evidence IDs;
- optionally excluded evidence IDs.

For example, the Data Engineering family can prioritize Python, SQL, ETL, and data-pipeline evidence while the Data Science family can prioritize machine learning, feature engineering, and evaluation. Both consume the same factual evidence records.

M2.1 provides deterministic family candidate pools. Learned or semantic resume-family selection is a later milestone.

## Retrieval

Every evidence item exposes a deterministic `retrieval_text()` representation containing its factual claim plus structured context such as type, organization, title, skills, role families, tags, and metrics.

`EvidenceQuery` supports filtering by:

- evidence kind;
- role family;
- skill;
- tag;
- verification state;
- recency cutoff.

When a recency cutoff is supplied, dated evidence older than the cutoff is excluded. Undated evergreen evidence such as a generally demonstrated skill remains eligible.

## Verification guardrail

`ResumeEvidenceStore.verified_payload()` refuses to produce a verified payload when:

- an evidence ID is unknown;
- the selected resume family explicitly excludes an evidence item;
- any selected evidence is unverified.

The schema also rejects verified evidence with no provenance, duplicate source/evidence/family IDs, invalid date ranges, and broken source or family references.

This is intentionally a structural guardrail. A later Evidence Verifier will add semantic checks that generated wording is actually entailed by the cited evidence.

## Example

The repository includes:

```text
data/examples/resume-evidence.example.yaml
```

It demonstrates a sanitized master evidence base and several resume-family definitions without committing real candidate PII.

## Relationship to later M2 work

```text
TruthStore -------------------------------> Application factual answers
                                                |
ResumeEvidenceBase -> ResumeEvidenceStore ----+----> Retrieval
                                                |
                                                +----> Resume-family selector
                                                |
                                                +----> Drafting agent
                                                          |
                                                          v
                                                   Evidence verifier
                                                          |
                                                          v
                                                    Approval queue
```

The core rule remains: **generated language may transform verified evidence, but it may not create new candidate facts.**
