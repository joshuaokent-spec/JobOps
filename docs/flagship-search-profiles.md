# Flagship search profiles and hard constraints

The JobOps Flagship begins with a persistent search profile: the user's explicit definition of which jobs are worth considering before fit ranking or application preparation happens.

## Hard constraints versus ranking

A search profile is not a scoring hint.

If a profile says:

```text
role: Data Engineer
work mode: remote
minimum salary: $65,000/year
```

then an onsite job, a non-matching role, or a job whose verified salary floor is below $65,000 is **ineligible**, regardless of how strong its skill match might be.

The pipeline is:

```text
discovered jobs
    |
    v
normalize / deduplicate
    |
    v
HARD SEARCH PROFILE
    |
    +--> reject with violation codes/reasons
    |
    v
eligible jobs only
    |
    v
fit scoring / ranking
```

## Persistent profile fields

Search profiles currently support:

- candidate ownership;
- one or more requested role-title queries;
- required keywords;
- excluded keywords;
- allowed work modes;
- allowed non-remote locations;
- employment types;
- annual salary floor;
- expected salary currency;
- strict minimum-bound versus range-can-reach salary policy;
- explicit policy for unknown compensation;
- excluded companies;
- allowed discovery sources;
- optional minimum fit-score threshold;
- active/inactive state.

## Salary semantics

The default policy is intentionally strict:

```text
salary_floor_policy = minimum_offered
unknown_compensation_policy = exclude
```

For a $65,000 floor:

- $70k-$90k -> eligible;
- $65k fixed -> eligible;
- $60k-$90k -> rejected;
- salary unknown -> rejected;
- wrong currency -> rejected;
- unverified/non-annual interval -> rejected unless a later normalization/provider contract resolves it.

A looser profile may explicitly choose:

```text
salary_floor_policy = range_can_reach
```

which allows a range whose upper bound reaches the threshold.

Unknown compensation may also be allowed explicitly, but JobOps never treats missing salary as proven to satisfy a floor.

## Work-mode semantics

If the allowed modes contain only `remote`, then:

- `remote` -> eligible;
- `hybrid` -> rejected;
- `onsite` -> rejected;
- `unknown` -> rejected.

Unknown work mode is not interpreted optimistically.

## Role matching

Requested role phrases are hard title constraints. Role tokens must be represented in the normalized title, with basic aliases such as:

- `AI` -> `artificial intelligence`;
- `ML` -> `machine learning`;
- `BI` -> `business intelligence`;
- `UX` -> `user experience`;
- `UI` -> `user interface`;
- compact web terms such as `frontend`, `fullstack`, and `backend` -> their split title forms.

Broader semantic role matching may be added later, but a probabilistic model must not silently widen a hard user constraint without an explicit profile policy.

## Stable rejection codes

Each rejected job returns machine-readable violation codes alongside human-readable reasons.

Current codes include:

- `profile_inactive`;
- `role`;
- `work_mode`;
- `location`;
- `employment_type`;
- `excluded_company`;
- `source`;
- `required_keyword`;
- `excluded_keyword`;
- `salary_floor`;
- `fit_score` for the optional post-filter fit threshold.

These make command-center summaries deterministic, for example:

```json
{
  "salary_floor": 12,
  "work_mode": 7,
  "role": 3
}
```

A job may violate more than one constraint, so violation counts may sum to more than the rejected-job count.

## API

```text
POST   /v1/search-profiles
GET    /v1/search-profiles
GET    /v1/search-profiles/{profile_id}
PATCH  /v1/search-profiles/{profile_id}
DELETE /v1/search-profiles/{profile_id}
POST   /v1/search-profiles/{profile_id}/preview
```

The preview endpoint evaluates active jobs from the current Job Store, rejects hard-constraint violations first, scores only eligible jobs, applies the optional minimum-fit threshold, and returns:

- examined count;
- eligible count;
- rejected count;
- ranked eligible jobs;
- a bounded rejected-job sample with reasons;
- stable rejection-code counts.

The preview candidate must match the profile's candidate owner.

## Flagship relationship

Search profiles are F1 of the Flagship roadmap.

Later Flagship slices use the same profile to:

1. derive provider discovery queries;
2. fan out across job sources;
3. normalize/deduplicate results;
4. reapply these hard constraints authoritatively;
5. rank surviving jobs;
6. prepare applications;
7. surface only review-required exceptions;
8. submit only through the existing one-shot submission authorization gate.

Provider-side search filters are optimizations. The persisted SearchProfile remains the authoritative constraint contract.


## Per-run Command Center filters

A broad saved profile can be narrowed for one hunt without changing the saved profile. The onboarded Flagship endpoint and Command Center support transient overrides for role focus, work mode, salary floor, and minimum fit score. This is useful when one candidate profile legitimately spans several career lanes, such as data/analytics, AI/ML, software/web development, and UX/product analysis.
