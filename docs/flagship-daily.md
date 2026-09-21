# Flagship daily runs and tracking

F7 makes the Flagship job hunt repeatable without storing the candidate/resume payload in schedule metadata.

## Private run inputs

The daily runner reads one private `FlagshipRunRequest` file per active search profile from:

```text
data/private/flagship-runs/<profile_id>.json
```

YAML (`.yaml` / `.yml`) is also supported. `data/private/` is already gitignored.

A minimal shape looks like:

```json
{
  "candidate": {
    "candidate_id": "YOUR_CANDIDATE_ID",
    "target_roles": ["Data Engineer"],
    "skills": ["Python", "SQL"],
    "years_experience": 3,
    "preferred_work_modes": ["remote"],
    "minimum_salary": 65000
  },
  "resume_evidence": {
    "candidate_id": "YOUR_CANDIDATE_ID",
    "sources": [],
    "items": [],
    "families": []
  },
  "discovery": {
    "providers": ["jobicy", "adzuna"]
  },
  "candidate_pool": 1000,
  "max_jobs": 25
}
```

The real evidence base must contain at least one valid resume family before a run can succeed. F8 will replace this hand-authored private input with first-class candidate/resume onboarding.

## Run once

From the repository environment:

```powershell
jobops-flagship-daily --input-dir data\private\flagship-runs
```

The command prints one JSON batch summary. It runs every active search profile independently, so a malformed or failing profile does not stop the others.

Exit codes:

- `0`: every active profile ran successfully;
- `1`: at least one profile failed;
- `2`: no profile failed, but at least one active profile was skipped (for example, a missing private input file).

The command never creates final-submit authorization and never submits an application.

## Windows Task Scheduler

Use Windows Task Scheduler to invoke the command once per day.

1. Create a basic task such as **JobOps Daily Hunt** and choose a Daily trigger.
2. Set **Program/script** to the virtual-environment executable, for example:

```text
C:\path\to\JobOps\.venv\Scripts\jobops-flagship-daily.exe
```

3. Set **Add arguments** to:

```text
--input-dir data\private\flagship-runs
```

4. Set **Start in** to the JobOps repository root:

```text
C:\path\to\JobOps
```

The task should run under the same Windows account that owns the private input files and local environment configuration.

## cron example

On Linux/macOS, an equivalent daily run at 08:00 can be configured with:

```text
0 8 * * * cd /path/to/JobOps && .venv/bin/jobops-flagship-daily --input-dir data/private/flagship-runs >> data/private/flagship-daily.log 2>&1
```

## Tracking

Every successful scheduled run uses the normal F3 run service and F4 readiness repository. The tracking service compares the two newest durable snapshots for a profile.

It reports:

- new prepared job IDs;
- job IDs that are no longer prepared;
- jobs that became ready;
- jobs that now require review;
- jobs whose readiness changed;
- current prepared/ready/review-required counts.

Tracking is available at:

```text
GET /v1/search-profiles/{profile_id}/tracking
```

and is embedded in:

```text
GET /v1/command-center/{profile_id}
GET /command-center
```

On the first run, the current set becomes the baseline. All current jobs count as new, and their current readiness is reflected in the newly-ready/newly-review-required fields.
