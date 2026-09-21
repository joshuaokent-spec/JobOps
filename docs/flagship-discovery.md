# Flagship multi-provider discovery

Flagship F2 expands JobOps from configured employer ATS feeds into resilient internet job
discovery while keeping the saved SearchProfile authoritative.

## Providers

### Jobicy

Jobicy is enabled by default and uses its public remote-jobs endpoint. No API key is required.

JobOps derives a bounded set of search terms from the saved role queries and required keywords,
uses a supported geographic hint when possible, preserves Jobicy attribution and canonical listing
URLs, and normalizes returned compensation conservatively.

Because Jobicy is remote-only, profiles that explicitly exclude remote work are skipped with a
provider diagnostic instead of failing the discovery run.

### Adzuna

Adzuna is optional and is enabled only when both credentials are configured:

```text
JOBOPS_ADZUNA_APP_ID=...
JOBOPS_ADZUNA_APP_KEY=...
JOBOPS_ADZUNA_COUNTRY=us
```

Adzuna query parameters may narrow role, location, excluded keywords, and salary before results
return. Those provider-side filters are optimizations only.

Adzuna salaries marked as predicted are retained in source metadata but are not promoted into
verified canonical compensation fields. This prevents estimated compensation from satisfying a
strict salary floor.

## Authoritative pipeline

Every provider result follows the same path:

```text
provider result
    |
    v
canonical normalization
    |
    v
SearchProfile hard constraints
    |
    +--> reject + stable reason codes
    |
    v
eligible result
    |
    v
deduplicate against this run and the Job Store
    |
    v
persist canonical active job
```

The post-normalization SearchProfile evaluation is mandatory. A provider returning an onsite job,
a role outside the requested title set, or a job below the verified salary floor cannot bypass the
candidate's saved constraints.

## Resilience

Discovery providers are isolated from one another. An unavailable, unconfigured, unsupported, or
failing provider produces a bounded diagnostic and does not fail the entire run.

Provider exceptions are intentionally summarized by exception class rather than echoing raw
exception messages that may contain credentials, URLs, or other private details.

## API

```text
POST /v1/search-profiles/{profile_id}/discover
```

The request may select providers and set a per-provider result limit.

A discovery result reports:

- requested, succeeded, failed, and skipped provider counts;
- fetched and normalized job counts;
- eligible and hard-constraint-rejected counts;
- persisted and duplicate counts;
- stable rejection-code totals;
- IDs of jobs persisted by the run;
- per-provider query counts, result counts, rejection summaries, and safe errors.

The endpoint rejects inactive search profiles.

## Deduplication

Provider results use the existing canonical normalization and dedupe fingerprint. Discovery checks
both earlier results in the current run and active jobs already persisted in the Job Store.

This lets a direct employer/ATS record remain canonical when an aggregator returns the same opening.

## Flagship relationship

F2 supplies the broad discovery input for F3. The next flagship slice can now orchestrate:

```text
saved profile
  -> discover
  -> filter
  -> rank
  -> choose resume/evidence
  -> prepare application work
```

without manually invoking the existing backend components one by one.
