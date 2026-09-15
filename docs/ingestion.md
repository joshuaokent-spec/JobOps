# Job Source Ingestion

JobOps isolates ATS-specific APIs behind adapters that emit a shared `SourceJobPosting` contract.
The adapters fetch and parse source data only; they do **not** write to the database. This keeps a
partial or failed source request from mutating stored jobs and leaves normalization/deduplication as
an explicit downstream stage.

## Greenhouse

The Greenhouse adapter uses the public Job Board API:

`GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true`

Greenhouse documents GET job-board data as public and unauthenticated. `content=true` includes the
full description plus department and office information. The source job-post `id` is retained as the
stable source identifier.

Official documentation: https://docs.greenhouse.io/job-board.html

## Lever

The Lever adapter uses the public Postings API:

`GET https://api.lever.co/v0/postings/{site}?mode=json&skip={n}&limit={n}`

The adapter follows Lever's documented `skip`/`limit` pagination and retains the posting `id` as the
stable source identifier. Location, commitment, workplace type, URLs, and salary range are preserved
when present.

Official documentation: https://github.com/lever/postings-api

## Shared source contract

Adapters currently emit:

- source and source job ID;
- configured company identity;
- title and source description;
- location, workplace type, and employment type when available;
- compensation fields when exposed by the source;
- source/apply URLs;
- source update timestamp when exposed;
- source-specific metadata required for later normalization and auditability.

M1.3 will turn this source contract into canonical `JobPosting` records, including deterministic
identity, normalization, and duplicate handling.
