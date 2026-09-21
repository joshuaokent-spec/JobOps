# ruff: noqa: E501
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from jobops.api.dependencies import get_session
from jobops.db import (
    SqlAlchemyApprovalRepository,
    SqlAlchemyFlagshipReadinessRepository,
    SqlAlchemyJobRepository,
)
from jobops.db.onboarding_repository import SqlAlchemyCandidateOnboardingRepository
from jobops.db.search_profile_repository import SqlAlchemySearchProfileRepository
from jobops.flagship.command_center import CommandCenterService
from jobops.models.command_center import CommandCenterView

router = APIRouter(tags=["command-center"])


@router.get("/v1/command-center/{profile_id}", response_model=CommandCenterView)
def get_command_center(
    profile_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> CommandCenterView:
    profile = SqlAlchemySearchProfileRepository(session).get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="search profile not found")

    return CommandCenterService(
        SqlAlchemyFlagshipReadinessRepository(session),
        SqlAlchemyJobRepository(session),
        SqlAlchemyApprovalRepository(session),
        SqlAlchemyCandidateOnboardingRepository(session),
    ).build(profile)


@router.get("/command-center", response_class=HTMLResponse, include_in_schema=False)
def command_center_dashboard() -> HTMLResponse:
    return HTMLResponse(_DASHBOARD_HTML)


_DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JobOps Command Center</title>
<style>
:root { color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
* { box-sizing: border-box; }
body { margin: 0; background: #0b1020; color: #e8edf7; }
header { padding: 22px 28px; border-bottom: 1px solid #24304b; background: #10182c; }
h1 { margin: 0 0 4px; font-size: 24px; }
header p { margin: 0; color: #98a6bf; }
main { max-width: 1200px; margin: 0 auto; padding: 24px; }
.toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 20px; flex-wrap: wrap; }
select, input, button, a.button { border: 1px solid #334363; background: #17223a; color: #eef3ff; border-radius: 8px; padding: 9px 12px; text-decoration: none; }
button { cursor: pointer; }
.hunt-filters { display: grid; grid-template-columns: minmax(260px, 2fr) repeat(3, minmax(150px, 1fr)); gap: 12px; margin: 12px 0; align-items: end; }
.filter-field { display: grid; gap: 6px; }
.filter-field label { color: #b8c4d8; font-size: 13px; }
.filter-field select[multiple] { min-height: 132px; }
@media (max-width: 850px) { .hunt-filters { grid-template-columns: 1fr; } }
.grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); margin: 16px 0 24px; }
.metric, .panel, .job { border: 1px solid #263552; background: #111a2e; border-radius: 10px; }
.metric { padding: 14px; }
.metric strong { display: block; font-size: 24px; }
.metric span, .muted { color: #95a4bd; }
.panel { padding: 18px; margin-bottom: 18px; }
.panel h2 { margin: 0 0 12px; font-size: 18px; }
.jobs { display: grid; gap: 10px; }
.job { padding: 14px; }
.job h3 { margin: 0 0 4px; font-size: 16px; }
.job .meta { color: #9cabc3; font-size: 13px; }
.job .score { font-weight: 700; float: right; }
.job a { color: #8fc3ff; }
.pill { display: inline-block; border: 1px solid #40567d; border-radius: 999px; padding: 2px 7px; font-size: 12px; margin-right: 5px; }
.empty { color: #93a2ba; padding: 8px 0; }
.error { color: #ffb6b6; }
ul { padding-left: 20px; }
code { color: #a9d1ff; }
</style>
</head>
<body>
<header>
  <h1>JobOps Command Center</h1>
  <p>Flagship job-search status, ready applications, and review exceptions.</p>
</header>
<main>
  <div class="toolbar">
    <label for="profile">Search profile</label>
    <select id="profile"></select>
    <button id="refresh">Refresh</button>
    <a class="button" href="/docs">API docs</a>
  </div>
  <div id="status" class="muted">Loading profiles…</div>
  <div id="content"></div>
</main>
<script>
const profileSelect = document.getElementById("profile");
const content = document.getElementById("content");
const statusEl = document.getElementById("status");

function money(job) {
  if (job.salary_min == null && job.salary_max == null) return "Salary not listed";
  const c = job.salary_currency || "USD";
  const fmt = value => {
    if (value == null) return "?";
    try {
      return new Intl.NumberFormat("en-US", {style:"currency", currency:c, maximumFractionDigits:0}).format(value);
    } catch {
      return `${c} ${Number(value).toLocaleString("en-US")}`;
    }
  };
  return job.salary_min === job.salary_max ? fmt(job.salary_min) : `${fmt(job.salary_min)} – ${fmt(job.salary_max)}`;
}
function text(tag, value, cls) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  node.textContent = value;
  return node;
}
function jobCard(job) {
  const card = document.createElement("div");
  card.className = "job";
  const score = text("span", `${job.score.toFixed(1)} fit`, "score");
  card.appendChild(score);
  card.appendChild(text("h3", `${job.title} — ${job.company}`));
  card.appendChild(text("div", `${job.location || "Location unknown"} · ${job.work_mode} · ${money(job)}`, "meta"));
  const tags = document.createElement("div");
  tags.style.marginTop = "8px";
  for (const label of [`#${job.rank}`, job.source || "source unknown", job.resume_family_id]) {
    tags.appendChild(text("span", label, "pill"));
  }
  card.appendChild(tags);
  if (job.readiness_reasons.length) {
    const ul = document.createElement("ul");
    for (const reason of job.readiness_reasons) ul.appendChild(text("li", reason));
    card.appendChild(ul);
  }
  const url = job.apply_url || job.source_url;
  if (url && /^https?:\/\//i.test(url)) {
    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Open posting";
    card.appendChild(link);
  }
  return card;
}
function panel(title) {
  const box = document.createElement("section");
  box.className = "panel";
  box.appendChild(text("h2", title));
  return box;
}
function render(view) {
  content.replaceChildren();
  statusEl.textContent = `${view.profile.name} · ${view.profile.active ? "active" : "inactive"}`;

  const onboarding = panel("Candidate onboarding");
  const o = view.onboarding;
  const onboardingGrid = document.createElement("div");
  onboardingGrid.className = "grid";
  for (const [value, label] of [
    [o.resume_family_ids.length, "Resume families"],
    [o.verified_evidence_count, "Verified evidence"],
    [o.verified_fact_count, "Verified facts"],
    [o.missing_resume_asset_family_ids.length, "Missing resume files"]
  ]) {
    const item = document.createElement("div");
    item.className = "metric";
    item.appendChild(text("strong", String(value)));
    item.appendChild(text("span", label));
    onboardingGrid.appendChild(item);
  }
  onboarding.appendChild(onboardingGrid);

  if (!o.onboarded) {
    onboarding.appendChild(text("p", "No candidate onboarding record exists yet. Import a private onboarding bundle with jobops-onboard.", "empty"));
  } else if (!o.ready_to_run) {
    onboarding.appendChild(text("p", "Onboarding exists but needs at least one resume family and verified evidence before the Flagship can run.", "empty"));
  } else {
    const filters = document.createElement("div");
    filters.className = "hunt-filters";

    const roleField = document.createElement("div");
    roleField.className = "filter-field";
    roleField.appendChild(text("label", "Role focus"));
    const roleSelect = document.createElement("select");
    roleSelect.multiple = true;
    roleSelect.size = Math.min(Math.max(view.profile.role_queries.length, 4), 8);
    roleSelect.title = "Choose one or more saved target roles for this hunt.";
    for (const role of view.profile.role_queries) {
      const option = document.createElement("option");
      option.value = role;
      option.textContent = role;
      option.selected = true;
      roleSelect.appendChild(option);
    }
    roleField.appendChild(roleSelect);
    roleField.appendChild(text("span", "Ctrl/Cmd-click to narrow this run.", "muted"));
    filters.appendChild(roleField);

    const salaryField = document.createElement("div");
    salaryField.className = "filter-field";
    salaryField.appendChild(text("label", "Minimum salary"));
    const salaryInput = document.createElement("input");
    salaryInput.type = "number";
    salaryInput.min = "0";
    salaryInput.step = "1000";
    salaryInput.placeholder = "No floor";
    salaryInput.value = view.profile.minimum_salary == null ? "" : String(view.profile.minimum_salary);
    salaryField.appendChild(salaryInput);
    filters.appendChild(salaryField);

    const modeField = document.createElement("div");
    modeField.className = "filter-field";
    modeField.appendChild(text("label", "Work mode"));
    const modeSelect = document.createElement("select");
    for (const [value, label] of [
      ["profile", "Use saved profile"],
      ["remote", "Remote only"],
      ["hybrid", "Hybrid only"],
      ["onsite", "Onsite only"],
      ["any", "Any work mode"]
    ]) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      modeSelect.appendChild(option);
    }
    modeField.appendChild(modeSelect);
    filters.appendChild(modeField);

    const fitField = document.createElement("div");
    fitField.className = "filter-field";
    fitField.appendChild(text("label", "Minimum fit score"));
    const fitInput = document.createElement("input");
    fitInput.type = "number";
    fitInput.min = "0";
    fitInput.max = "100";
    fitInput.step = "1";
    fitInput.placeholder = "No minimum";
    fitInput.value = view.profile.minimum_fit_score == null ? "" : String(view.profile.minimum_fit_score);
    fitField.appendChild(fitInput);
    filters.appendChild(fitField);

    onboarding.appendChild(filters);

    const runButton = document.createElement("button");
    runButton.textContent = "Run Job Hunt";
    runButton.addEventListener("click", async () => {
      const selectedRoles = Array.from(roleSelect.selectedOptions).map(option => option.value);
      if (view.profile.role_queries.length && !selectedRoles.length) {
        statusEl.textContent = "Select at least one role focus before running the hunt.";
        statusEl.className = "error";
        return;
      }

      const runFilters = {role_queries: selectedRoles};
      if (salaryInput.value.trim()) {
        runFilters.minimum_salary = Number(salaryInput.value);
      } else {
        runFilters.clear_minimum_salary = true;
      }
      if (fitInput.value.trim()) {
        runFilters.minimum_fit_score = Number(fitInput.value);
      } else if (view.profile.minimum_fit_score != null) {
        runFilters.clear_minimum_fit_score = true;
      }
      if (modeSelect.value === "any") {
        runFilters.allowed_work_modes = [];
      } else if (modeSelect.value !== "profile") {
        runFilters.allowed_work_modes = [modeSelect.value];
      }

      runButton.disabled = true;
      runButton.textContent = "Running…";
      statusEl.className = "muted";
      statusEl.textContent = `Running Flagship hunt across ${selectedRoles.length} role target(s)…`;
      try {
        const response = await fetch(view.actions.run_onboarded, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(runFilters)
        });
        if (!response.ok) {
          const detail = await response.json().catch(() => ({}));
          throw new Error(detail.detail || "Flagship run failed.");
        }
        statusEl.textContent = "Flagship run complete.";
        await loadSelected();
      } catch (error) {
        statusEl.textContent = error.message;
        statusEl.className = "error";
      } finally {
        runButton.disabled = false;
        runButton.textContent = "Run Job Hunt";
      }
    });
    onboarding.appendChild(runButton);
    onboarding.appendChild(
      text(
        "p",
        o.ready_for_application_execution
          ? "Onboarding is ready. Filters above apply only to this hunt; the saved profile remains unchanged."
          : "Job hunting is ready. Add the missing resume-family files before live application preparation.",
        "muted"
      )
    );
  }
  content.appendChild(onboarding);

  if (!view.has_run) {
    const box = panel("No Flagship run yet");
    box.appendChild(text("p", "This profile is configured, but it does not have a saved Flagship run yet.", "empty"));
    const docs = document.createElement("a");
    docs.href = view.actions.api_docs;
    docs.textContent = "Open API docs to run this profile";
    box.appendChild(docs);
    content.appendChild(box);
    return;
  }

  const m = view.metrics;
  const metrics = document.createElement("div");
  metrics.className = "grid";
  for (const [value, label] of [
    [m.total_examined, "Examined"],
    [m.total_hard_eligible, "Hard-eligible"],
    [m.prepared_count, "Prepared"],
    [m.ready_count, "Ready"],
    [m.review_required_count, "Needs review"],
    [view.pending_approval_count, "Pending approvals"]
  ]) {
    const item = document.createElement("div");
    item.className = "metric";
    item.appendChild(text("strong", String(value)));
    item.appendChild(text("span", label));
    metrics.appendChild(item);
  }
  content.appendChild(metrics);

  if (view.tracking) {
    const t = view.tracking;
    const changes = panel(t.has_previous_run ? "Since the previous run" : "First tracked run");
    const changeGrid = document.createElement("div");
    changeGrid.className = "grid";
    for (const [value, label] of [
      [t.new_job_ids.length, "New matches"],
      [t.no_longer_prepared_job_ids.length, "Dropped matches"],
      [t.newly_ready_job_ids.length, "Became ready"],
      [t.newly_review_required_job_ids.length, "Now need review"],
      [t.readiness_changed_job_ids.length, "Readiness changes"]
    ]) {
      const item = document.createElement("div");
      item.className = "metric";
      item.appendChild(text("strong", String(value)));
      item.appendChild(text("span", label));
      changeGrid.appendChild(item);
    }
    changes.appendChild(changeGrid);
    if (!t.has_previous_run) {
      changes.appendChild(text("p", "This is the baseline run; future daily runs will show deltas against it.", "muted"));
    }
    content.appendChild(changes);
  }

  const actions = panel("Operator links");
  const actionLinks = [
    ["Profile JSON", view.actions.profile],
    ["Readiness JSON", view.actions.readiness],
    ["Exceptions JSON", view.actions.exceptions],
    ["Tracking JSON", view.actions.tracking],
    ["Onboarding status", view.actions.onboarding],
    ["Pending approvals", view.actions.approvals + "?status=pending"],
    ["API docs", view.actions.api_docs]
  ];
  for (const [label, href] of actionLinks) {
    const link = document.createElement("a");
    link.href = href;
    link.textContent = label;
    link.style.marginRight = "12px";
    actions.appendChild(link);
  }
  actions.appendChild(text("p", `Manual payload endpoint: POST ${view.actions.run} · onboarded endpoint: POST ${view.actions.run_onboarded}`, "muted"));
  content.appendChild(actions);

  const ready = panel(`Ready jobs (${view.ready_jobs.length})`);
  const readyList = document.createElement("div");
  readyList.className = "jobs";
  if (!view.ready_jobs.length) readyList.appendChild(text("div", "No ready jobs in the latest run.", "empty"));
  for (const job of view.ready_jobs) readyList.appendChild(jobCard(job));
  ready.appendChild(readyList);
  content.appendChild(ready);

  const review = panel(`Review required (${view.review_required_jobs.length})`);
  const reviewList = document.createElement("div");
  reviewList.className = "jobs";
  if (!view.review_required_jobs.length) reviewList.appendChild(text("div", "No job-level review exceptions.", "empty"));
  for (const job of view.review_required_jobs) reviewList.appendChild(jobCard(job));
  review.appendChild(reviewList);
  content.appendChild(review);

  const approvals = panel(`Pending approvals (${view.pending_approvals.length})`);
  if (!view.pending_approvals.length) {
    approvals.appendChild(text("div", "No pending approval items.", "empty"));
  } else {
    const ul = document.createElement("ul");
    for (const item of view.pending_approvals) {
      const li = document.createElement("li");
      li.textContent = `[${item.review_band}] ${item.question} · job ${item.job_id}`;
      ul.appendChild(li);
    }
    approvals.appendChild(ul);
    const link = document.createElement("a");
    link.href = view.actions.approvals + "?status=pending";
    link.textContent = "Open pending approvals API";
    approvals.appendChild(link);
  }
  content.appendChild(approvals);

  if (Object.keys(m.rejection_summary).length) {
    const rejects = panel("Latest rejection summary");
    const ul = document.createElement("ul");
    for (const [reason, count] of Object.entries(m.rejection_summary)) {
      ul.appendChild(text("li", `${reason}: ${count}`));
    }
    rejects.appendChild(ul);
    content.appendChild(rejects);
  }
}

async function loadProfiles() {
  const response = await fetch("/v1/search-profiles?limit=100");
  if (!response.ok) throw new Error("Could not load search profiles.");
  const payload = await response.json();
  profileSelect.replaceChildren();
  for (const profile of payload.items) {
    const option = document.createElement("option");
    option.value = profile.profile_id;
    option.textContent = profile.name;
    profileSelect.appendChild(option);
  }
  if (!payload.items.length) {
    statusEl.textContent = "No search profiles exist yet.";
    content.replaceChildren(text("div", "Create a search profile from /docs first.", "empty"));
    return;
  }
  await loadSelected();
}
async function loadSelected() {
  const profileId = profileSelect.value;
  if (!profileId) return;
  statusEl.textContent = "Loading command center…";
  const response = await fetch("/v1/command-center/" + encodeURIComponent(profileId));
  if (!response.ok) throw new Error("Could not load command-center state.");
  render(await response.json());
}
document.getElementById("refresh").addEventListener("click", loadSelected);
profileSelect.addEventListener("change", loadSelected);
loadProfiles().catch(error => {
  statusEl.textContent = error.message;
  statusEl.className = "error";
});
</script>
</body>
</html>
"""
