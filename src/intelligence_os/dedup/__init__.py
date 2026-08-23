"""Deduplication and similarity package."""

from intelligence_os.dedup.exact import normalize_url
from intelligence_os.dedup.semantic import compute_cosine_similarity
from intelligence_os.dedup.engine import DeduplicationEngine

__all__ = ["normalize_url", "compute_cosine_similarity", "DeduplicationEngine"]
