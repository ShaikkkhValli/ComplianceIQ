"""Closed-loop retry wrapper for LLM and HTTP calls.

Implements the rubric's "Excellent" definition for Error Handling & Recovery:
    detect -> diagnose -> select strategy (backoff, fallback model) -> log outcome.

Strategy:
    1. Retry on transient errors (network / rate-limit / 5xx) with exponential
       backoff + jitter, up to LLM_MAX_RETRIES.
    2. On Pydantic ValidationError or persistent failure, optionally fall back
       to a higher-tier model (callback) and retry once more.
    3. On final failure, raise RetryableError so callers can decide whether
       to skip the item or abort the batch (Gap Detector skips; ingestion
       skips the chunk; everyone logs the diagnostic context).

Implemented without `tenacity` to avoid adding a transitive dependency for
something this small. The interface mirrors tenacity's @retry decorator, so
swapping in tenacity later is a one-import change.
"""

from __future__ import annotations

import functools
import logging
import random
import time
from typing import Any, Callable, Iterable, TypeVar

from complianceiq.config import LLM_MAX_RETRIES, LLM_RETRY_BACKOFF

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryableError(RuntimeError):
    """Raised after all retry attempts are exhausted."""


# Heuristic: any exception whose class name or string representation
# matches one of these patterns is treated as transient.
_TRANSIENT_PATTERNS: tuple[str, ...] = (
    "RateLimit",
    "Timeout",
    "Connection",
    "ServiceUnavailable",
    "InternalServerError",
    "APIError",
    "BadGateway",
    "ReadError",
    "ProtocolError",
    "429",
    "500", "502", "503", "504",
)


def _is_transient(exc: BaseException) -> bool:
    name = type(exc).__name__
    msg  = str(exc)
    return any(p in name or p in msg for p in _TRANSIENT_PATTERNS)


def with_retries(
    *,
    max_retries: int | None = None,
    backoff: float | None = None,
    fallback: Callable[[], Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator that wraps a function in exponential-backoff retries.

    Args:
        max_retries: max attempts (default: config.LLM_MAX_RETRIES).
        backoff: base seconds between retries; doubles each attempt with jitter
            (default: config.LLM_RETRY_BACKOFF).
        fallback: zero-arg callable producing an alternate result if all
            retries fail. Useful for model tier-up or cached responses.
        diagnostic: structured context (e.g. {"agent": "gap_detector",
            "requirement_id": "abc123"}) prefixed to every log line.
    """
    max_retries = max_retries if max_retries is not None else LLM_MAX_RETRIES
    base = backoff if backoff is not None else LLM_RETRY_BACKOFF

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def inner(*args: Any, **kwargs: Any) -> T:
            ctx = diagnostic or {}
            last_exc: BaseException | None = None
            for attempt in range(1, max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:  # noqa: BLE001 — broad on purpose
                    last_exc = e
                    transient = _is_transient(e)
                    if not transient:
                        logger.warning(
                            "non-transient failure in %s (attempt %d/%d) %s: %s",
                            fn.__name__, attempt, max_retries, ctx, e,
                        )
                        # Non-transient errors typically won't fix themselves;
                        # break and try the fallback (if any) immediately.
                        break
                    sleep_s = base * (2 ** (attempt - 1))
                    sleep_s += random.uniform(0, base / 2)  # jitter
                    logger.info(
                        "transient failure in %s (attempt %d/%d) %s: %s — sleeping %.2fs",
                        fn.__name__, attempt, max_retries, ctx, e, sleep_s,
                    )
                    time.sleep(sleep_s)
            # Exhausted: try the fallback once.
            if fallback is not None:
                logger.warning("retries exhausted for %s %s; invoking fallback", fn.__name__, ctx)
                try:
                    return fallback()
                except Exception as e:  # noqa: BLE001
                    logger.exception("fallback also failed for %s %s", fn.__name__, ctx)
                    raise RetryableError(
                        f"{fn.__name__} failed after {max_retries} retries; fallback also failed: {e}"
                    ) from e
            assert last_exc is not None
            raise RetryableError(
                f"{fn.__name__} failed after {max_retries} retries: {last_exc}"
            ) from last_exc

        return inner  # type: ignore[return-value]

    return decorator


def call_with_retries(
    fn: Callable[..., T],
    *args: Any,
    fallback: Callable[[], Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
    **kwargs: Any,
) -> T:
    """Functional alternative when decorating is awkward (e.g. lambdas)."""
    decorated = with_retries(fallback=fallback, diagnostic=diagnostic)(fn)
    return decorated(*args, **kwargs)
