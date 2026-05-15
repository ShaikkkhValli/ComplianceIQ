"""Unit tests for the model router (rubric §10: cost-latency)."""

import os
import importlib

import pytest

from complianceiq.models import Severity


def _reload_router():
    import complianceiq.config
    importlib.reload(complianceiq.config)
    import complianceiq.utils.model_router
    importlib.reload(complianceiq.utils.model_router)
    return complianceiq.utils.model_router


def test_cheap_model_when_no_signals(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("LLM_MODEL_HIGH", "gpt-4o")
    monkeypatch.setenv("TIER_UP_ON_LOW_CONFIDENCE", "true")
    router = _reload_router()
    # Low severity, good retrieval, no prior call -> cheap model.
    assert router.select_model(severity=Severity.LOW, retrieval_distance=0.1) == "gpt-4o-mini"


def test_tier_up_on_high_severity_first_pass(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("LLM_MODEL_HIGH", "gpt-4o")
    monkeypatch.setenv("TIER_UP_ON_LOW_CONFIDENCE", "true")
    router = _reload_router()
    # High severity + no prior confidence -> tier up.
    assert router.select_model(severity=Severity.HIGH, retrieval_distance=0.5) == "gpt-4o"


def test_tier_up_on_low_confidence_retry(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("LLM_MODEL_HIGH", "gpt-4o")
    monkeypatch.setenv("TIER_UP_ON_LOW_CONFIDENCE", "true")
    monkeypatch.setenv("LOW_CONFIDENCE_THRESHOLD", "0.5")
    router = _reload_router()
    # First pass returned 0.3 confidence on a high-severity req -> tier up retry.
    assert router.select_model(
        severity=Severity.HIGH, retrieval_distance=0.5, last_confidence=0.3,
    ) == "gpt-4o"


def test_no_tier_up_when_disabled(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("LLM_MODEL_HIGH", "gpt-4o")
    monkeypatch.setenv("TIER_UP_ON_LOW_CONFIDENCE", "false")
    router = _reload_router()
    assert router.select_model(severity=Severity.HIGH, retrieval_distance=0.9) == "gpt-4o-mini"


def test_no_tier_up_when_first_pass_was_confident(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("LLM_MODEL_HIGH", "gpt-4o")
    monkeypatch.setenv("TIER_UP_ON_LOW_CONFIDENCE", "true")
    monkeypatch.setenv("LOW_CONFIDENCE_THRESHOLD", "0.5")
    router = _reload_router()
    # High severity but prior confidence is fine -> stay cheap.
    assert router.select_model(
        severity=Severity.HIGH, retrieval_distance=0.5, last_confidence=0.9,
    ) == "gpt-4o-mini"
