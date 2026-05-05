"""Assessment history.

Each `orchestrate` run appends one AssessmentSnapshot to history.jsonl,
giving you a longitudinal view of compliance posture over time.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from complianceiq.config import HISTORY_FILE
from complianceiq.models import AssessmentSnapshot, ComplianceScore

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_snapshot(
    score: ComplianceScore,
    run_id: str,
    started_at: str,
    n_orphan_requirements: int | None = None,
    notes: str = "",
    path: Path = HISTORY_FILE,
) -> AssessmentSnapshot:
    """Append one snapshot to assessment_history.jsonl."""
    snap = AssessmentSnapshot(
        run_id=run_id,
        started_at=started_at,
        finished_at=_now_iso(),
        overall_score=score.overall_score,
        weighted_overall_score=score.weighted_overall_score,
        total_requirements=score.total_requirements,
        fully_covered=score.fully_covered,
        partially_covered=score.partially_covered,
        not_covered=score.not_covered,
        high_priority_gaps=score.high_priority_gaps,
        by_domain_weighted_scores={
            d.domain.value: d.weighted_score for d in score.by_domain
        },
        n_orphan_requirements=n_orphan_requirements,
        notes=notes,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(snap.model_dump(mode="json"), ensure_ascii=False))
            f.write("\n")
        logger.info("Recorded assessment snapshot to %s", path)
    except Exception as e:
        logger.warning("History write failed: %s", e)
    return snap


def list_snapshots(
    n: int | None = None,
    path: Path = HISTORY_FILE,
) -> list[AssessmentSnapshot]:
    if not path.exists():
        return []
    out: list[AssessmentSnapshot] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(AssessmentSnapshot.model_validate_json(line))
            except Exception:
                continue
    if n is not None:
        out = out[-n:]
    return out


def print_history(n: int = 10, compare: bool = False) -> None:
    snaps = list_snapshots(n=n)
    print()
    print("=" * 70)
    print(f"ASSESSMENT HISTORY (last {len(snaps)})")
    print("=" * 70)
    if not snaps:
        print("(no snapshots yet — run `python main.py orchestrate`)")
        return

    print(f"{'finished_at':<28} {'run':<10} {'score':>7} {'wt-score':>9} "
          f"{'reqs':>5} {'open':>5} {'hp-gaps':>8}")
    for s in snaps:
        open_gaps = s.partially_covered + s.not_covered
        run_short = s.run_id[:8]
        print(f"{s.finished_at:<28} {run_short:<10} "
              f"{s.overall_score:>7.2f} {s.weighted_overall_score:>9.2f} "
              f"{s.total_requirements:>5} {open_gaps:>5} {s.high_priority_gaps:>8}")

    if compare and len(snaps) >= 2:
        prev, curr = snaps[-2], snaps[-1]
        print("\nDelta vs previous run:")
        print(f"  weighted score : {prev.weighted_overall_score:.2f} -> "
              f"{curr.weighted_overall_score:.2f}  "
              f"({curr.weighted_overall_score - prev.weighted_overall_score:+.2f})")
        print(f"  high-pri gaps  : {prev.high_priority_gaps} -> "
              f"{curr.high_priority_gaps}  "
              f"({curr.high_priority_gaps - prev.high_priority_gaps:+d})")
        print(f"  not_covered    : {prev.not_covered} -> {curr.not_covered}  "
              f"({curr.not_covered - prev.not_covered:+d})")
