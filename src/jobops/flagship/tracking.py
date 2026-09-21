from jobops.db.flagship_repository import FlagshipReadinessRepository
from jobops.models.flagship_run import FlagshipReadiness
from jobops.models.flagship_tracking import FlagshipTrackingSummary


class FlagshipTrackingService:
    """Compare the latest durable Flagship run to the immediately previous run."""

    def __init__(self, readiness_repository: FlagshipReadinessRepository) -> None:
        self.readiness_repository = readiness_repository

    def latest(self, profile_id: str) -> FlagshipTrackingSummary | None:
        history = list(self.readiness_repository.history(profile_id, limit=2))
        if not history:
            return None

        latest = history[0]
        previous = history[1] if len(history) > 1 else None

        latest_by_id = {item.job_id: item for item in latest.prepared_jobs}
        previous_by_id = (
            {item.job_id: item for item in previous.prepared_jobs}
            if previous is not None
            else {}
        )

        latest_ids = set(latest_by_id)
        previous_ids = set(previous_by_id)
        shared_ids = latest_ids & previous_ids

        new_job_ids = sorted(latest_ids - previous_ids)
        no_longer_prepared_job_ids = sorted(previous_ids - latest_ids)

        newly_ready = []
        newly_review_required = []
        readiness_changed = []

        for job_id in sorted(latest_ids):
            after = latest_by_id[job_id].readiness
            before_item = previous_by_id.get(job_id)
            if before_item is None:
                if after is FlagshipReadiness.READY:
                    newly_ready.append(job_id)
                elif after is FlagshipReadiness.REVIEW_REQUIRED:
                    newly_review_required.append(job_id)
                continue

            before = before_item.readiness
            if before is after:
                continue
            readiness_changed.append(job_id)
            if after is FlagshipReadiness.READY:
                newly_ready.append(job_id)
            elif after is FlagshipReadiness.REVIEW_REQUIRED:
                newly_review_required.append(job_id)

        return FlagshipTrackingSummary(
            profile_id=latest.profile_id,
            latest_run_id=latest.run_id,
            previous_run_id=previous.run_id if previous is not None else None,
            has_previous_run=previous is not None,
            latest_completed_at=latest.completed_at,
            previous_completed_at=(
                previous.completed_at if previous is not None else None
            ),
            prepared_count=latest.prepared_count,
            ready_count=latest.ready_count,
            review_required_count=latest.review_required_count,
            new_job_ids=new_job_ids,
            no_longer_prepared_job_ids=no_longer_prepared_job_ids,
            newly_ready_job_ids=sorted(set(newly_ready)),
            newly_review_required_job_ids=sorted(set(newly_review_required)),
            readiness_changed_job_ids=readiness_changed,
        )
