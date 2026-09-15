from fastapi import FastAPI

from jobops.api.jobs import router as jobs_router
from jobops.matching import BaselineJobScorer
from jobops.models.scoring import ScoreBreakdown, ScoreRequest

app = FastAPI(
    title="JobOps API",
    version="0.1.0",
    description="Evidence-grounded job-search intelligence API",
)
app.include_router(jobs_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/score", response_model=ScoreBreakdown)
def score_job(request: ScoreRequest) -> ScoreBreakdown:
    return BaselineJobScorer().score(request.candidate, request.job)
