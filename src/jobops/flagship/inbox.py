from jobops.db.approval_repository import ApprovalRepository
from jobops.db.flagship_run_repository import FlagshipRunRepository
from jobops.models.approval import ApprovalStatus
from jobops.models.flagship_inbox import (
    FlagshipExceptionInbox,
    FlagshipExceptionItem,
    FlagshipExceptionKind,
    FlagshipReadinessSummary,
)
from jobops.models.flagship_run import FlagshipReadiness


class FlagshipInboxService:
    """Build the candidate-facing latest-run readiness and exception surfaces."""

    def __init__(
        self,
        runs: FlagshipRunRepository,
        approvals: ApprovalRepository,
    ) -> None:
        self.runs = runs
        self.approvals = approvals

    def readiness(self, profile_id: str) -> FlagshipReadinessSummary | None:
        return self.runs.latest(profile_id)

    def exceptions(self, profile_id: str) -> FlagshipExceptionInbox | None:
        summary = self.runs.latest(profile_id)
        if summary is None:
            return None

        items: list[FlagshipExceptionItem] = []
        pending_approvals = 0

        for job in summary.jobs:
            if job.readiness is FlagshipReadiness.REVIEW_REQUIRED:
                items.append(
                    FlagshipExceptionItem(
                        kind=FlagshipExceptionKind.READINESS,
                        job_id=job.job_id,
                        company=job.company,
                        title=job.title,
                        rank=job.rank,
                        reasons=list(job.readiness_reasons),
                    )
                )

            approvals = self.approvals.list(
                status=ApprovalStatus.PENDING,
                job_id=job.job_id,
                limit=100,
                offset=0,
            )
            for approval in approvals:
                pending_approvals += 1
                items.append(
                    FlagshipExceptionItem(
                        kind=FlagshipExceptionKind.APPROVAL,
                        job_id=job.job_id,
                        company=job.company,
                        title=job.title,
                        rank=job.rank,
                        reasons=[_approval_reason(approval.reason.value)],
                        approval=approval,
                    )
                )

        items.sort(
            key=lambda item: (
                item.rank,
                0 if item.kind is FlagshipExceptionKind.READINESS else 1,
                item.approval.approval_id if item.approval is not None else "",
            )
        )
        return FlagshipExceptionInbox(
            profile_id=summary.profile_id,
            run_id=summary.run_id,
            run_completed_at=summary.completed_at,
            ready_count=summary.ready_count,
            review_required_count=summary.review_required_count,
            pending_approval_count=pending_approvals,
            total_exceptions=len(items),
            items=items,
        )


def _approval_reason(reason: str) -> str:
    return f"Pending application review: {reason.replace('_', ' ')}."
