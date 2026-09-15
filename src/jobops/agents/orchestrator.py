from dataclasses import dataclass

from jobops.knowledge import TruthStore
from jobops.models.candidate import CandidateProfile
from jobops.models.job import JobPosting
from jobops.models.scoring import ScoreBreakdown
from jobops.matching import BaselineJobScorer


@dataclass(frozen=True, slots=True)
class ApplicationDecision:
    job_id: str
    score: ScoreBreakdown
    recommended: bool
    requires_human_approval: bool = True


class ApplicationOrchestrator:
    """M0 orchestration shell.

    Later milestones will add specialized tools/agents for job research, resume selection,
    application drafting, verification, and browser preparation. Submission remains a distinct
    human-approved action.
    """

    def __init__(self, candidate: CandidateProfile, threshold: float = 70.0):
        self.candidate = candidate
        self.truth_store = TruthStore(candidate)
        self.scorer = BaselineJobScorer()
        self.threshold = threshold

    def evaluate(self, job: JobPosting) -> ApplicationDecision:
        score = self.scorer.score(self.candidate, job)
        return ApplicationDecision(
            job_id=job.job_id,
            score=score,
            recommended=score.overall >= self.threshold,
        )
