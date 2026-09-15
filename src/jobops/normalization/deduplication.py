from collections import defaultdict
from collections.abc import Iterable
from typing import Protocol

from jobops.models.job import JobPosting


class NearDuplicateComparator(Protocol):
    """Future embedding/ML comparators implement this interface."""

    def similarity(self, left: JobPosting, right: JobPosting) -> float: ...


class DeterministicDuplicateDetector:
    def is_duplicate(self, left: JobPosting, right: JobPosting) -> bool:
        if left.job_id == right.job_id:
            return True
        return bool(left.dedupe_key and left.dedupe_key == right.dedupe_key)

    def groups(self, jobs: Iterable[JobPosting]) -> list[list[JobPosting]]:
        grouped: dict[str, list[JobPosting]] = defaultdict(list)
        for job in jobs:
            key = job.dedupe_key or job.job_id
            grouped[key].append(job)
        return [group for group in grouped.values() if len(group) > 1]
