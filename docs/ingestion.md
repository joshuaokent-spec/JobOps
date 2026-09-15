# Job Source Ingestion

JobOps isolates ATS-specific APIs behind adapters that emit a shared `SourceJobPosting` contract. Adapters only fetch and parse source data; persistence happens later through the refresh runner after a complete source fetch has succeeded.

## Greenhouse

The Greenhouse adapter uses the public Job Board API:

`GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true`

Greenhouse documents GET job-board data as public and unauthenticated. `content=true` includes the full description plus department and office information. The source job-post `id` is retained as the stable source identifier, while the board token is retained as the source scope.

Official documentation: https://docs.greenhouse.io/job-board.html

## Lever

The Lever adapter uses the public Postings API:

`GET https://api.lever.co/v0/postings/{site}?mode=json&skip={n}&limit={n}`

The adapter follows Lever's documented `skip`/`limit` pagination and retains the posting `id` as the stable source identifier. Location, commitment, workplace type, URLs, and salary range are preserved when present. The Lever site slug is retained as the source scope.

Official documentation: https://github.com/lever/postings-api

## Shared source contract

Adapters emit source identity and scope, source job ID, configured company identity, title and description, location/workplace/employment data, compensation when exposed, source/apply URLs, update timestamps, and raw/source-specific metadata needed for auditability.

## Refresh pipeline

The scheduler-friendly entry point is:

```bash
jobops-ingest --config data/private/sources.yaml
```

Start from `data/examples/sources.example.yaml`. The command is intended to be invoked by cron, a container scheduler, or a workflow runner rather than keeping a scheduler process inside the API service.

Each configured feed executes independently:

`fetch -> normalize -> upsert -> deactivate missing -> commit`

A source is fetched completely before its database transaction begins. If fetching, parsing, normalization, or persistence fails, that source transaction is rolled back and previously active jobs are left unchanged. Only a successful refresh may deactivate jobs that disappeared from that exact `(source, source_scope)` feed.

Stable canonical IDs make repeated refreshes idempotent. Successful refreshes update existing records instead of creating uncontrolled duplicates.

## Metrics and logging

The refresh runner emits JSON log events for every source and for the complete run. Metrics include fetched records, upserted records, stale records deactivated, source success/failure counts, durations, and source-scoped error summaries. The CLI also writes the final run metrics as JSON and exits non-zero when any configured source fails.
