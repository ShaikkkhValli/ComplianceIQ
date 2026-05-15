"""Unit tests for the LRU caches (rubric §10: cost-latency)."""

from complianceiq.utils.cache import (
    cached_embed, cached_llm_call, embed_cache_stats, llm_cache_stats, reset_caches,
)


def test_embed_cache_hits_on_repeat():
    reset_caches()
    calls = {"n": 0}

    def _fake_embed(text: str) -> list[float]:
        calls["n"] += 1
        return [0.1, 0.2, 0.3]

    out1 = cached_embed("hello world", model="m", embedder=_fake_embed)
    out2 = cached_embed("hello world", model="m", embedder=_fake_embed)
    out3 = cached_embed("different text", model="m", embedder=_fake_embed)

    assert out1 == out2 == [0.1, 0.2, 0.3]
    assert out3 == [0.1, 0.2, 0.3]
    assert calls["n"] == 2  # second "hello world" is a cache hit
    stats = embed_cache_stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 2


def test_llm_cache_keyed_on_prompt_and_model():
    reset_caches()
    calls = {"n": 0}

    def _invoke():
        calls["n"] += 1
        return {"value": calls["n"]}

    a1 = cached_llm_call(model="A", prompt="p1", schema="S", invoke=_invoke)
    a2 = cached_llm_call(model="A", prompt="p1", schema="S", invoke=_invoke)
    b1 = cached_llm_call(model="B", prompt="p1", schema="S", invoke=_invoke)
    a3 = cached_llm_call(model="A", prompt="p2", schema="S", invoke=_invoke)

    assert a1 == a2 == {"value": 1}     # cache hit
    assert b1 == {"value": 2}           # different model -> miss
    assert a3 == {"value": 3}           # different prompt -> miss
    stats = llm_cache_stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 3


def test_llm_cache_bypass_via_marker():
    reset_caches()
    calls = {"n": 0}

    def _invoke():
        calls["n"] += 1
        return calls["n"]

    a = cached_llm_call(model="A", prompt="[NOCACHE] p1", schema="S", invoke=_invoke)
    b = cached_llm_call(model="A", prompt="[NOCACHE] p1", schema="S", invoke=_invoke)
    assert a == 1 and b == 2
    stats = llm_cache_stats()
    assert stats["bypass"] == 2
