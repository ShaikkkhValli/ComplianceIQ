"""Tiered model routing (rubric §10: cost-latency tradeoffs).

Most calls go to the cheap default model (gpt-4o-mini). For high-stakes
decisions - high-severity requirements where retrieval was weak, or where
a previous attempt produced a low-confidence GapAssessment - we tier up
to a stronger model (gpt-4o) for the single re-call.

The routing rule is a small pure function so it can be unit-tested
without any LLM machinery.
"""

from __future__ import annotations

from complianceiq.config import (
    LLM_MODEL,
    LLM_MODEL_HIGH,
    LOW_CONFIDENCE_THRESHOLD,
    TIER_UP_ON_LOW_CONFIDENCE,
)
from complianceiq.models import Severity


def select_model(
    *,
    severity: Severity | None = None,
    retrieval_distance: float | None = None,
    last_confidence: float | None = None,
) -> str:
    """Pick a model for the next LLM call.

    Returns LLM_MODEL_HIGH when ALL of:
      - tier-up is enabled (config.TIER_UP_ON_LOW_CONFIDENCE)
      - the requirement is HIGH severity OR retrieval distance is poor (>0.45)
      - and either we have no prior confidence, OR the prior confidence
        was below LOW_CONFIDENCE_THRESHOLD.

    Otherwise returns the default LLM_MODEL.
    """
    if not TIER_UP_ON_LOW_CONFIDENCE:
        return LLM_MODEL

    high_stakes = (severity == Severity.HIGH) or (
        retrieval_distance is not None and retrieval_distance > 0.45
    )
    low_confidence = (
        last_confidence is not None and last_confidence < LOW_CONFIDENCE_THRESHOLD
    )

    if high_stakes and (last_confidence is None or low_confidence):
        return LLM_MODEL_HIGH
    return LLM_MODEL
