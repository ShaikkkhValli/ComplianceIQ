"""Cross-cutting utilities: retries, caching, model routing, citation parsing.

These modules are deliberately small and dependency-light so that they can
be reused by every layer (ingestion, agents, orchestration) without coupling
the layers together.
"""

from complianceiq.utils.retry import with_retries, RetryableError
from complianceiq.utils.cache import (
    cached_embed,
    cached_llm_call,
    embed_cache_stats,
    llm_cache_stats,
)
from complianceiq.utils.model_router import select_model
from complianceiq.utils.clause_ref import parse_clause_ref

__all__ = [
    "with_retries",
    "RetryableError",
    "cached_embed",
    "cached_llm_call",
    "embed_cache_stats",
    "llm_cache_stats",
    "select_model",
    "parse_clause_ref",
]
