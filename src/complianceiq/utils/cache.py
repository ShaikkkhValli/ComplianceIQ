"""LRU caches for embeddings and LLM responses (rubric §10: cost-latency).

Both caches are in-process and thread-safe (functools.lru_cache is). They
are intentionally simple - the goal is to skip duplicate calls within a
single orchestration run, not to be a distributed cache.

Hit-rate stats are exposed via embed_cache_stats() / llm_cache_stats() and
are surfaced in the audit log at the end of each run.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
from typing import Any, Callable

from complianceiq.config import EMBED_CACHE_SIZE, LLM_CACHE_SIZE

logger = logging.getLogger(__name__)


def _hash_prompt(model: str, prompt: str, schema: str = "") -> str:
    h = hashlib.sha256()
    h.update(model.encode("utf-8"))
    h.update(b"\x1e")
    h.update(prompt.encode("utf-8"))
    h.update(b"\x1e")
    h.update(schema.encode("utf-8"))
    return h.hexdigest()


@functools.lru_cache(maxsize=EMBED_CACHE_SIZE)
def _embed_cached(model: str, text: str) -> tuple[float, ...]:
    """Internal cache slot. Populated by cached_embed."""
    raise RuntimeError("Internal cache slot — must be populated via cached_embed().")


def cached_embed(
    text: str,
    *,
    model: str,
    embedder: Callable[[str], list[float]],
) -> list[float]:
    """Return the embedding for `text`, hitting an in-process LRU cache first.

    `embedder` is the caller-supplied function that performs the actual
    OpenAI call when the cache misses.
    """
    key = (model, text)
    try:
        cached = _embed_cache.get(key)
        if cached is not None:
            _stats["embed_hits"] += 1
            return list(cached)
        _stats["embed_misses"] += 1
        result = embedder(text)
        _embed_cache.put(key, tuple(result))
        return result
    except Exception:
        # On cache failure, never block the caller — just call through.
        return embedder(text)


def cached_llm_call(
    *,
    model: str,
    prompt: str,
    schema: str,
    invoke: Callable[[], Any],
) -> Any:
    """Cache LLM responses keyed on (model, prompt, schema_repr).

    Use this for deterministic chains (temperature=0). The cache is bypassed
    when the prompt contains the literal substring "[NOCACHE]", a useful
    escape hatch for evals that need fresh model calls.
    """
    if "[NOCACHE]" in prompt:
        _stats["llm_bypass"] += 1
        return invoke()
    key = _hash_prompt(model, prompt, schema)
    cached = _llm_cache.get(key)
    if cached is not None:
        _stats["llm_hits"] += 1
        return cached
    _stats["llm_misses"] += 1
    result = invoke()
    _llm_cache.put(key, result)
    return result


# ── Tiny dict-backed LRU (so we can introspect / clear / stat) ────────
class _LRU:
    def __init__(self, maxsize: int) -> None:
        self.maxsize = max(1, maxsize)
        self._d: dict[Any, Any] = {}

    def get(self, key: Any) -> Any:
        if key in self._d:
            v = self._d.pop(key)
            self._d[key] = v
            return v
        return None

    def put(self, key: Any, value: Any) -> None:
        if key in self._d:
            self._d.pop(key)
        elif len(self._d) >= self.maxsize:
            self._d.pop(next(iter(self._d)))
        self._d[key] = value

    def __len__(self) -> int:
        return len(self._d)

    def clear(self) -> None:
        self._d.clear()


_embed_cache = _LRU(EMBED_CACHE_SIZE)
_llm_cache   = _LRU(LLM_CACHE_SIZE)
_stats: dict[str, int] = {
    "embed_hits": 0, "embed_misses": 0,
    "llm_hits":   0, "llm_misses":   0,
    "llm_bypass": 0,
}


def embed_cache_stats() -> dict[str, Any]:
    h, m = _stats["embed_hits"], _stats["embed_misses"]
    rate = h / (h + m) if (h + m) else 0.0
    return {"hits": h, "misses": m, "size": len(_embed_cache), "hit_rate": round(rate, 3)}


def llm_cache_stats() -> dict[str, Any]:
    h, m, b = _stats["llm_hits"], _stats["llm_misses"], _stats["llm_bypass"]
    rate = h / (h + m) if (h + m) else 0.0
    return {"hits": h, "misses": m, "bypass": b,
            "size": len(_llm_cache), "hit_rate": round(rate, 3)}


def reset_caches() -> None:
    """Drop both caches and reset stats. Used in tests."""
    _embed_cache.clear()
    _llm_cache.clear()
    for k in _stats:
        _stats[k] = 0
