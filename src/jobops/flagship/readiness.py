from jobops.db.approval_repository import ApprovalRepository
from jobops.db.flagship_repository import FlagshipReadinessRepository
from jobops.models.approval import ApprovalStatus
from jobops.models.flagship_readiness import (
    FlagshipExceptionInbox,
    FlagshipReadinessSummary,
)
from jobops.models.flagship_run import FlagshipReadiness


class FlagshipReadinessService:
    """Read the latest durable Flagship snapshot and surface candidate attention only."""

    def __init__(
        self,
        readiness_repository: FlagshipReadinessRepository,
        approval_repository: ApprovalRepository,
    ) -> None:
        self.readiness_repository = readiness_repository
        self.approval_repository = approval_repository

    def latest(self, profile_id: str) -> FlagshipReadinessSummary | None:
        return self.readiness_repository.latest(profile_id)

    def exceptions(self, profile_id: str) -> FlagshipExceptionInbox | None:
        summary = self.readiness_repository.latest(profile_id)
        if summary is None:
            return None

        review_required = [
            item
            for item in summary.prepared_jobs
            if item.readiness is FlagshipReadiness.REVIEW_REQUIRED
        ]

        pending = []
        for prepared in summary.prepared_jobs:
            pending.extend(
                self.approval_repository.list(
                    status=ApprovalStatus.PENDING,
                    job_id=prepared.job_id,
                    limit=100,
                    offset=0,
                )
            )
        pending.sort(key=lambda item: (item.created_at, item.approval_id))

        return FlagshipExceptionInbox(
            run_id=summary.run_id,
            profile_id=summary.profile_id,
            candidate_id=summary.candidate_id,
            completed_at=summary.completed_at,
            review_required_jobs=review_required,
            pending_approvals=pending,
            total_exceptions=len(review_required) + len(pending),
        )
