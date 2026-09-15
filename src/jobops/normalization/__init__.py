from jobops.normalization.deduplication import (
    DeterministicDuplicateDetector,
    NearDuplicateComparator,
)
from jobops.normalization.job_normalizer import (
    JobNormalizer,
    canonical_work_mode,
    clean_display_text,
    dedupe_fingerprint,
    normalize_skills,
    source_identity,
    strip_html,
)
from jobops.normalization.semantic_deduplication import (
    DuplicateCandidate,
    DuplicateMatchType,
    DuplicateScanResult,
    EmbeddingNearDuplicateComparator,
    HybridDuplicateDetector,
    JobEmbeddingTextBuilder,
    cosine_similarity,
)
from jobops.normalization.semantic_evaluation import (
    LabeledDuplicatePair,
    SemanticEvaluationReport,
    ThresholdMetrics,
    evaluate_thresholds,
)

__all__ = [
    "DeterministicDuplicateDetector",
    "DuplicateCandidate",
    "DuplicateMatchType",
    "DuplicateScanResult",
    "EmbeddingNearDuplicateComparator",
    "HybridDuplicateDetector",
    "JobEmbeddingTextBuilder",
    "JobNormalizer",
    "LabeledDuplicatePair",
    "NearDuplicateComparator",
    "SemanticEvaluationReport",
    "ThresholdMetrics",
    "canonical_work_mode",
    "clean_display_text",
    "cosine_similarity",
    "dedupe_fingerprint",
    "evaluate_thresholds",
    "normalize_skills",
    "source_identity",
    "strip_html",
]
