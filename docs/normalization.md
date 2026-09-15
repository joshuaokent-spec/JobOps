# Canonical Job Normalization and Deduplication

JobOps separates source ingestion from canonical normalization. ATS adapters emit
`SourceJobPosting`; `JobNormalizer` converts those source records into stable `JobPosting` objects
that are safe to persist, rank, and later use as ML features.

## Stable source identity

The canonical `job_id` is a deterministic SHA-256-derived identifier based only on the source name
and source job ID. A title or description edit therefore updates the same canonical record rather
than creating a new job.

## Cross-source duplicate fingerprint

`dedupe_key` is intentionally different from `job_id`. It hashes normalized company, title, and
location identity so materially identical postings found through different ATS sources can be
flagged together. Remote jobs use a common remote location bucket so `Remote`, `Remote - US`, and
similar source labels do not automatically create separate fingerprints.

The deterministic detector handles exact fingerprints today. `NearDuplicateComparator` defines the
interface that M1 can later implement with embeddings or a learned similarity model without changing
the normalization API.

## Conservative normalization

Normalization currently:

- collapses whitespace without forcing display text to lowercase;
- converts descriptions from source HTML to readable text while retaining the raw payload;
- maps explicit/inferred workplace signals to `remote`, `hybrid`, `onsite`, or `unknown`;
- de-duplicates skill strings case-insensitively;
- uppercases currency codes;
- annualizes recognized hourly, daily, weekly, and monthly salary intervals;
- preserves unknown salary intervals instead of pretending they are annual;
- keeps source metadata and raw payloads for debugging and auditability.

The matching scorer treats non-USD or non-annual compensation as unknown rather than making an
invalid numeric comparison against a USD annual salary preference.
