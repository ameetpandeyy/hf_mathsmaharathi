"""Deduplication module."""

from pipeline.dedupe.hasher import (
    DedupeEngine,
    compute_simhash_64,
    hamming_distance,
    jaccard_similarity,
    normalize_math_text,
)

__all__ = [
    "DedupeEngine",
    "compute_simhash_64",
    "hamming_distance",
    "jaccard_similarity",
    "normalize_math_text",
]
