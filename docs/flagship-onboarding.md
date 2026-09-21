# Flagship v1 candidate onboarding

F8 turns the Flagship pipeline into a repeatable local job-hunt product. Candidate facts, verified evidence, resume-family mappings, and run defaults are persisted in the local JobOps database instead of being supplied in every run request.

## Privacy boundary

Do not commit real onboarding bundles or resumes.

The recommended local layout is:

```text
data/private/<candidate>/
  onboarding.yaml
  project-overview.pdf
  resumes/
    general.pdf
    data-analytics.pdf
    ai-ml.pdf
    ml-infrastructure.pdf
```

`data/private/` is ignored by Git.

Onboarding intentionally does not store passwords, browser cookies, MFA material, or final-submit authorization. F5's exact-state one-shot authorization remains separate.

## Import onboarding and search profiles

Start from `examples/onboarding.example.yaml`, then run:

```powershell
jobops-onboard --config data\private\<candidate>\onboarding.yaml
```

The command validates ownership and resume-family mappings, saves the onboarding record, upserts any bundled search profiles, and prints a minimized readiness summary.

Exit codes:

- `0`: onboarding is ready for Flagship runs;
- `1`: invalid input or persistence failure;
- `2`: onboarding was saved but is not ready to run.

## Readiness

A candidate is **ready to run** when the evidence base contains at least one resume family and at least one verified evidence item.

A candidate is **ready for application execution** when every configured resume family also has a local resume asset mapping.

The minimized status endpoint is:

```text
GET /v1/candidates/{candidate_id}/onboarding/status
```

The complete local record is available at:

```text
GET /v1/candidates/{candidate_id}/onboarding
```

Resume assets can be resolved by family through:

```text
GET /v1/candidates/{candidate_id}/onboarding/resume-assets/{family_id}
```

## Run the real hunt

With the API running:

```powershell
uvicorn jobops.api.main:app --reload
```

open:

```text
http://127.0.0.1:8000/command-center
```

Select the search profile. When onboarding is ready, the dashboard shows **Run Job Hunt**.

The button invokes:

```text
POST /v1/search-profiles/{profile_id}/run-onboarded
```

No candidate/resume payload is sent by the browser. JobOps loads the candidate and evidence from local onboarding, runs the normal F3 pipeline, saves the normal F4 readiness snapshot, and refreshes the F6/F7 command center.

## Daily automation

F7 now prefers persisted onboarding automatically. The legacy `data/private/flagship-runs/<profile_id>.json` input remains only as a backward-compatible fallback when no onboarding record exists.

That means the scheduled command remains:

```powershell
jobops-flagship-daily --input-dir data\private\flagship-runs
```

but onboarded profiles no longer require a per-profile run-input file.

## First real-hunt checklist

1. Put resume PDFs and supporting evidence files under `data/private/`.
2. Build the private onboarding YAML with candidate facts, verified evidence, resume families, and resume asset paths.
3. Include at least one search profile, such as remote data/AI roles with a $65,000 annual salary floor.
4. Run `jobops-onboard`.
5. Start the API and open `/command-center`.
6. Confirm onboarding shows ready.
7. Click **Run Job Hunt**.
8. Review new matches, ready jobs, and review exceptions.
9. For supported Greenhouse/Lever applications, continue through F5 preparation and explicit final-submit authorization.
10. Schedule `jobops-flagship-daily` after the manual run behaves as expected.

## Updating onboarding

Re-run `jobops-onboard --config ...` after changing facts, evidence, resume families, resume files, or run defaults. The candidate row and bundled search-profile IDs are updated in place.

Keep uncertain or sensitive facts out of verified candidate facts until they have been reviewed. Legal/sensitive application questions continue through the approval workflow rather than being inferred.
