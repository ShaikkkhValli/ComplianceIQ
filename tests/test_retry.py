"""Unit tests for the retry wrapper (rubric §3: error handling & recovery)."""

import pytest

from complianceiq.utils.retry import RetryableError, with_retries


class _RateLimit(Exception):
    """Looks transient by class name."""


class _BadRequest(Exception):
    """Non-transient — should NOT be retried."""


def test_retries_on_transient_error():
    calls = {"n": 0}

    @with_retries(max_retries=3, backoff=0.01)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _RateLimit("429 Too Many Requests")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3


def test_does_not_retry_non_transient():
    calls = {"n": 0}

    @with_retries(max_retries=4, backoff=0.01)
    def fails():
        calls["n"] += 1
        raise _BadRequest("400 invalid input")

    with pytest.raises(RetryableError):
        fails()
    # Non-transient should break out after the first attempt and go to fallback (none),
    # so we should see exactly one call.
    assert calls["n"] == 1


def test_fallback_invoked_when_retries_exhausted():
    calls = {"n": 0}

    @with_retries(max_retries=2, backoff=0.01, fallback=lambda: "fallback-value")
    def always_429():
        calls["n"] += 1
        raise _RateLimit("429")

    assert always_429() == "fallback-value"
    assert calls["n"] == 2


def test_raises_retryable_error_when_no_fallback_and_exhausted():
    @with_retries(max_retries=2, backoff=0.01)
    def always_500():
        raise _RateLimit("500 Internal Server Error")

    with pytest.raises(RetryableError):
        always_500()
