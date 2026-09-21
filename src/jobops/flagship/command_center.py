from jobops.db.approval_repository import ApprovalRepository
from jobops.db.flagship_repository import FlagshipReadinessRepository
from jobops.db.repositories import JobRepository
from jobops.models.approval import ApprovalStatus
from jobops.models.command_center import (
    CommandCenterActions,
    CommandCenterApproval,
    CommandCenterJob,
    CommandCenterRunMetrics,
    CommandCenterView,
)
from jobops.models.flagship_run import FlagshipReadiness
from jobops.models.search_profile import SearchProfile


class CommandCenterService:
    """Build one privacy-minimized operator view from existing Flagship state."""

    def __init__(
        self,
        readiness_repository: FlagshipReadinessRepository,
        job_repository: JobRepository,
        approval_repository: ApprovalRepository,
    ) -> None:
        self.readiness_repository = readiness_repository
        self.job_repository = job_repository
        self.approval_repository = approval_repository

    def build(self, profile: SearchProfile) -> CommandCenterView:
        actions = CommandCenterActions(
            profile=f"/v1/search-profiles/{profile.profile_id}",
            run=f"/v1/search-profiles/{profile.profile_id}/run",
            readiness=f"/v1/search-profiles/{profile.profile_id}/readiness",
            exceptions=f"/v1/search-profiles/{profile.profile_id}/exceptions",
            approvals="/v1/approvals",
        )
        summary = self.readiness_repository.latest(profile.profile_id)
        if summary is None:
            return CommandCenterView(
                profile=profile,
                has_run=False,
                actions=actions,
            )

        ready_jobs: list[CommandCenterJob] = []
        review_jobs: list[CommandCenterJob] = []
        missing_job_ids: list[str] = []

        for prepared in summary.prepared_jobs:
            job = self.job_repository.get(prepared.job_id)
            if job is None:
                missing_job_ids.append(prepared.job_id)
                continue

            card = CommandCenterJob(
                run_id=summary.run_id,
                job_id=prepared.job_id,
                rank=prepared.rank,
                score=prepared.score,
                readiness=prepared.readiness,
                readiness_reasons=list(prepared.readiness_reasons),
                resume_family_id=prepared.resume_family_id,
                resume_selection_score=prepared.resume_selection_score,
                title=job.title,
                company=job.company,
                location=job.location,
                work_mode=job.work_mode,
                salary_min=job.salary_min,
                salary_max=job.salary_max,
                salary_currency=job.salary_currency,
                source=job.source,
                source_url=job.source_url,
                apply_url=job.apply_url,
                active=job.active,
            )
            if prepared.readiness is FlagshipReadiness.READY:
                ready_jobs.append(card)
            else:
                review_jobs.append(card)

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
        approvals = [
            CommandCenterApproval(
                approval_id=item.approval_id,
                job_id=item.job_id,
                question=item.question,
                review_band=item.review_band,
                reason=item.reason.value,
                created_at=item.created_at,
            )
            for item in pending
        ]

        return CommandCenterView(
            profile=profile,
            has_run=True,
            metrics=CommandCenterRunMetrics(
                run_id=summary.run_id,
                started_at=summary.started_at,
                completed_at=summary.completed_at,
                total_examined=summary.total_examined,
                total_hard_eligible=summary.total_hard_eligible,
                total_hard_rejected=summary.total_hard_rejected,
                total_fit_eligible=summary.total_fit_eligible,
                total_fit_rejected=summary.total_fit_rejected,
                prepared_count=summary.prepared_count,
                ready_count=summary.ready_count,
                review_required_count=summary.review_required_count,
                rejection_summary=dict(summary.rejection_summary),
            ),
            ready_jobs=ready_jobs,
            review_required_jobs=review_jobs,
            pending_approvals=approvals,
            missing_job_ids=sorted(missing_job_ids),
            actions=actions,
        )
