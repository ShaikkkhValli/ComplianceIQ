"""Langfuse tracing helpers.

Centralized so every agent shares the same callback handler and so the rest
of the system degrades gracefully when Langfuse keys are missing or auth fails.

Public API:
    is_enabled()                 -> bool
    get_handler()                -> CallbackHandler | None
    flush()                      -> None
    score_run(run_id, name, val) -> None  (rubric §10: custom quality scores)
"""

from __future__ import annotations

import logging

from complianceiq.config import (
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY,
)

logger = logging.getLogger(__name__)

_handler = None
_langfuse_client = None
_initialized = False
_enabled = False


def is_enabled() -> bool:
    """True if Langfuse keys are present AND auth check succeeded on first init."""
    _ensure_initialized()
    return _enabled


def get_handler():
    """Return a Langfuse CallbackHandler, or None if Langfuse is unavailable."""
    _ensure_initialized()
    return _handler if _enabled else None


def flush() -> None:
    """Flush pending traces to Langfuse. Safe to call when disabled."""
    if _enabled and _langfuse_client is not None:
        try:
            _langfuse_client.flush()
        except Exception as e:
            logger.warning("Langfuse flush failed: %s", e)


def score_run(run_id: str, name: str, value: float, comment: str | None = None) -> None:
    """Attach a custom quality score to the Langfuse trace for ``run_id``.

    Used by the workflow to attach the deterministic compliance_score to
    every run so prompt versions can be A/B compared in the Langfuse dashboard.
    Safe to call when tracing is disabled (becomes a no-op).
    """
    _ensure_initialized()
    if not _enabled or _langfuse_client is None:
        return
    try:
        _langfuse_client.score(
            trace_id=run_id,
            name=name,
            value=float(value),
            comment=comment,
        )
    except Exception as e:
        logger.debug("Langfuse score() call failed (non-fatal): %s", e)


# ── internals ────────────────────────────────────────────────
def _ensure_initialized() -> None:
    global _initialized, _enabled, _handler, _langfuse_client
    if _initialized:
        return
    _initialized = True

    if not (LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY):
        logger.info("Langfuse keys not set; tracing disabled.")
        return

    try:
        from langfuse import Langfuse
        from langfuse.langchain import CallbackHandler
    except ImportError as e:
        logger.warning("langfuse import failed (%s); tracing disabled.", e)
        return

    try:
        _langfuse_client = Langfuse()
        if not _langfuse_client.auth_check():
            logger.warning("Langfuse auth_check failed; tracing disabled.")
            return
        _handler = CallbackHandler()
        _enabled = True
        logger.info("Langfuse tracing enabled.")
    except Exception as e:
        logger.warning("Langfuse initialization failed (%s); tracing disabled.", e)
