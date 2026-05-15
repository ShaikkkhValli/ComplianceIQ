"""Golden-pair recall test for the Gap Detector (rubric §11: Accuracy).

This test exercises two layers:

1. The deterministic scoring + dataset-shape layer (always runs in CI).
   - Validates that the golden dataset is well-formed.
   - Validates that the scorer's coverage→value map is a strict 1.0 / 0.5 / 0.0
     mapping (so any silent change to scoring will fail this test).

2. The full Gap Detector recall layer (runs only when OPENAI_API_KEY is set
   AND ChromaDB has been populated). When run, it compares Gap Detector
   output against the golden dataset and asserts recall >= EVAL_RECALL_TARGET.

Recall is defined as:
    "Of the gaps the dataset says should be FOUND (NOT_COVERED or
     PARTIALLY_COVERED), what fraction did the agent surface?"

This intentionally errs on the side of false positives — for compliance,
missing a real gap is worse than flagging a non-gap for review.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from complianceiq.config import EVAL_GOLDEN_FILE, EVAL_RECALL_TARGET
from complianceiq.models import CoverageQuality, Severity


# ── Layer 1: dataset shape + scoring constants ────────────────
def _load_golden() -> list[dict]:
    assert EVAL_GOLDEN_FILE.exists(), (
        f"Golden eval dataset missing: {EVAL_GOLDEN_FILE}"
    )
    rows: list[dict] = []
    with EVAL_GOLDEN_FILE.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                pytest.fail(f"Malformed JSON on line {i}: {e}")
    return rows


def test_golden_dataset_is_well_formed() -> None:
    rows = _load_golden()
    assert len(rows) >= 20, "Golden dataset must contain >= 20 cases for recall to be meaningful"
    required = {"id", "domain", "regulation_excerpt",
                "expected_coverage", "expected_severity", "rationale"}
    valid_cov = {q.value for q in CoverageQuality}
    valid_sev = {s.value for s in Severity}
    seen_ids: set[str] = set()
    for r in rows:
        missing = required - r.keys()
        assert not missing, f"Row {r.get('id')!r} missing keys: {missing}"
        assert r["id"] not in seen_ids, f"Duplicate id: {r['id']}"
        seen_ids.add(r["id"])
        assert r["expected_coverage"] in valid_cov, (
            f"{r['id']}: bad expected_coverage={r['expected_coverage']!r}"
        )
        assert r["expected_severity"] in valid_sev, (
            f"{r['id']}: bad expected_severity={r['expected_severity']!r}"
        )


def test_scoring_constants_are_unchanged() -> None:
    """Lock down the scoring formula constants — auditors rely on these."""
    from complianceiq.orchestration.scoring import _COVERAGE_VALUE, _SEVERITY_WEIGHT

    assert _COVERAGE_VALUE[CoverageQuality.FULLY_COVERED]     == 1.0
    assert _COVERAGE_VALUE[CoverageQuality.PARTIALLY_COVERED] == 0.5
    assert _COVERAGE_VALUE[CoverageQuality.NOT_COVERED]       == 0.0
    assert _SEVERITY_WEIGHT[Severity.HIGH]   == 3
    assert _SEVERITY_WEIGHT[Severity.MEDIUM] == 2
    assert _SEVERITY_WEIGHT[Severity.LOW]    == 1


# ── Layer 2: live recall measurement (gated) ──────────────────
def _live_eval_enabled() -> bool:
    if not os.environ.get("OPENAI_API_KEY"):
        return False
    from complianceiq.config import CHROMA_DIR
    if not CHROMA_DIR.exists():
        return False
    return True


@pytest.mark.skipif(not _live_eval_enabled(),
                    reason="Live eval requires OPENAI_API_KEY and a populated ChromaDB.")
def test_gap_detector_meets_recall_target() -> None:
    """End-to-end: run the Gap Detector on the golden set and check recall."""
    from complianceiq.agents.gap_detector import GapDetectorAgent
    from complianceiq.models import (
        Document, DocumentMetadata, Domain, Requirement, Severity as Sev,
    )

    rows = _load_golden()
    agent = GapDetectorAgent(top_k=5)

    expected_findings = 0
    surfaced_findings = 0

    for r in rows:
        # Build a synthetic Requirement from the golden row
        domain = Domain(r["domain"])
        severity = Sev(r["expected_severity"])
        req = Requirement(
            requirement_id=f"eval-{r['id']}",
            source_file=f"eval/{r['id']}.txt",
            page_or_section="eval",
            doc_type="regulatory",
            domain=domain,
            requirement_text=r["regulation_excerpt"],
            mandatory_action=r["regulation_excerpt"],
            evidence_needed=[],
            severity=severity,
            extracted_by="eval-fixture",
        )
        gap = agent.detect_gap(req)

        # The agent should "find" anything not fully-covered
        gold_finding = r["expected_coverage"] != "fully_covered"
        agent_finding = gap.coverage != CoverageQuality.FULLY_COVERED

        if gold_finding:
            expected_findings += 1
            if agent_finding:
                surfaced_findings += 1

    if expected_findings == 0:
        pytest.skip("Golden set has no expected findings; recall undefined")

    recall = surfaced_findings / expected_findings
    assert recall >= EVAL_RECALL_TARGET, (
        f"Gap Detector recall {recall:.2f} below target {EVAL_RECALL_TARGET}"
    )
