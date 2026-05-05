"""ComplianceWorkflow — the Week 5 multi-agent orchestrator.

Chains:
  Regulation Monitor → Gap Detector → Evidence Collector → Policy Analyzer → Scorer + Planner

Each agent is independent and produces a JSONL artifact; the orchestrator is
just the glue that runs them in order, passes state, and aggregates results.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from complianceiq.agents.base import load_requirements, write_jsonl
from complianceiq.agents.gap_detector import GapDetectorAgent
from complianceiq.agents.policy_analyzer import PolicyAnalyzerAgent
from complianceiq.agents.regulation_monitor import RegulationMonitorAgent, SUMMARIES_FILE
from complianceiq.config import (
    COVERAGE_FILE,
    EVIDENCE_FILE,
    GAPS_FILE,
    REMEDIATION_FILE,
    REQUIREMENTS_FILE,
    SCORE_FILE,
)
from complianceiq.models import (
    ComplianceScore,
    Domain,
    Gap,
    Requirement,
)
from complianceiq.orchestration.evidence import EvidenceCollector
from complianceiq.orchestration.scoring import (
    build_remediation_plan,
    compute_compliance_score,
    print_plan,
    print_score,
)
from complianceiq.vectorstore.store import ChromaStore

logger = logging.getLogger(__name__)


class WorkflowResult(BaseModel):
    requirements_count: int
    summaries_count: int
    gaps_count: int
    evidence_count: int
    coverage_count: int
    overall_score: float
    weighted_overall_score: float
    output_files: dict[str, str]


class ComplianceWorkflow:
    """Sequential orchestrator over the three Week 4 agents + Week 5 add-ons."""

    def __init__(
        self,
        store: ChromaStore | None = None,
        gap_top_k: int = 5,
        evidence_top_k: int = 5,
    ) -> None:
        self.store = store or ChromaStore.load()
        self.regulation_monitor = RegulationMonitorAgent(store=self.store)
        self.gap_detector       = GapDetectorAgent(store=self.store, top_k=gap_top_k)
        self.policy_analyzer    = PolicyAnalyzerAgent(store=self.store)
        self.evidence_collector = EvidenceCollector(store=self.store, top_k=evidence_top_k)

    # ── steps ─────────────────────────────────────────────────
    def _step_summaries(self, requirements: list[Requirement],
                        domain: Domain | None = None,
                        skip_summaries: bool = False) -> int:
        if skip_summaries:
            logger.info("Skipping regulation summaries (skip_summaries=True)")
            return 0
        print("\n[Step 1/5] Regulation Monitor — summarizing regulatory documents")
        summaries = self.regulation_monitor.summarize_all(requirements, domain=domain)
        write_jsonl(SUMMARIES_FILE, summaries)
        return len(summaries)

    def _step_gaps(self, requirements: list[Requirement],
                   domain: Domain | None = None,
                   limit: int | None = None) -> list[Gap]:
        print("\n[Step 2/5] Gap Detector — analyzing regulatory requirements vs policies")
        gaps = self.gap_detector.detect_gaps(requirements, domain=domain, limit=limit)
        write_jsonl(GAPS_FILE, gaps)
        return gaps

    def _step_evidence(self, gaps: list[Gap]) -> int:
        print("\n[Step 3/5] Evidence Collector — bundling regulation + policy evidence")
        packets = [self.evidence_collector.packet_from_gap(g) for g in gaps]
        write_jsonl(EVIDENCE_FILE, packets)
        return len(packets)

    def _step_coverage(self, gaps: list[Gap]) -> int:
        print("\n[Step 4/5] Policy Analyzer — per-domain coverage rollup")
        # Group already happens inside assess_all; we just pass gaps.
        assessments = self.policy_analyzer.assess_all(gaps)
        write_jsonl(COVERAGE_FILE, assessments)
        return len(assessments)

    def _step_score(self, gaps: list[Gap]) -> ComplianceScore:
        print("\n[Step 5/5] Scorer + Remediation Planner — comprehensive compliance score")
        score = compute_compliance_score(gaps)
        SCORE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with SCORE_FILE.open("w", encoding="utf-8") as f:
            json.dump(score.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
        plan = build_remediation_plan(gaps)
        write_jsonl(REMEDIATION_FILE, plan.items)

        print_score(score)
        print_plan(plan, top_n=10)
        return score

    # ── full pipeline ─────────────────────────────────────────
    def run(
        self,
        domain: Domain | None = None,
        limit: int | None = None,
        skip_summaries: bool = False,
    ) -> WorkflowResult:
        if not Path(REQUIREMENTS_FILE).exists():
            raise FileNotFoundError(
                f"{REQUIREMENTS_FILE} not found. "
                "Run `python main.py ingest --extract` first."
            )

        requirements = load_requirements(REQUIREMENTS_FILE)
        print(f"\nLoaded {len(requirements)} requirements from {REQUIREMENTS_FILE}")
        if domain:
            print(f"Filtering to domain: {domain.value}")

        n_summaries = self._step_summaries(requirements, domain=domain, skip_summaries=skip_summaries)
        gaps        = self._step_gaps(requirements, domain=domain, limit=limit)
        n_evidence  = self._step_evidence(gaps)
        n_coverage  = self._step_coverage(gaps)
        score       = self._step_score(gaps)

        result = WorkflowResult(
            requirements_count=len(requirements),
            summaries_count=n_summaries,
            gaps_count=len(gaps),
            evidence_count=n_evidence,
            coverage_count=n_coverage,
            overall_score=score.overall_score,
            weighted_overall_score=score.weighted_overall_score,
            output_files={
                "summaries":  str(SUMMARIES_FILE),
                "gaps":       str(GAPS_FILE),
                "evidence":   str(EVIDENCE_FILE),
                "coverage":   str(COVERAGE_FILE),
                "score":      str(SCORE_FILE),
                "remediation": str(REMEDIATION_FILE),
            },
        )

        print("\n" + "=" * 60)
        print("WEEK 5 — WORKFLOW COMPLETE")
        print("=" * 60)
        print(f"Requirements       : {result.requirements_count}")
        print(f"Regulation digests : {result.summaries_count}")
        print(f"Gaps analyzed      : {result.gaps_count}")
        print(f"Evidence packets   : {result.evidence_count}")
        print(f"Coverage rollups   : {result.coverage_count}")
        print(f"Overall score      : {result.overall_score:.2f} "
              f"(weighted: {result.weighted_overall_score:.2f})")
        print("\nOutput files:")
        for k, v in result.output_files.items():
            print(f"  {k:<12} : {v}")
        return result


# ── CLI helpers ───────────────────────────────────────────────
def run_workflow(
    domain: Domain | None = None,
    limit: int | None = None,
    skip_summaries: bool = False,
    gap_top_k: int = 5,
) -> WorkflowResult:
    wf = ComplianceWorkflow(gap_top_k=gap_top_k)
    return wf.run(domain=domain, limit=limit, skip_summaries=skip_summaries)


def run_score_only() -> ComplianceScore:
    """Recompute compliance score from existing gaps.jsonl (no LLM cost)."""
    if not Path(GAPS_FILE).exists():
        raise FileNotFoundError(
            f"{GAPS_FILE} not found. Run `python main.py analyze-gaps` or "
            "`python main.py orchestrate` first."
        )
    gaps: list[Gap] = []
    with GAPS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                gaps.append(Gap.model_validate_json(line))

    score = compute_compliance_score(gaps)
    SCORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SCORE_FILE.open("w", encoding="utf-8") as f:
        json.dump(score.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
    print_score(score)
    return score


def run_remediation_only(top_n: int = 20):
    """Build remediation plan from existing gaps.jsonl (no LLM cost)."""
    if not Path(GAPS_FILE).exists():
        raise FileNotFoundError(
            f"{GAPS_FILE} not found. Run `python main.py analyze-gaps` first."
        )
    gaps: list[Gap] = []
    with GAPS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                gaps.append(Gap.model_validate_json(line))
    plan = build_remediation_plan(gaps)
    write_jsonl(REMEDIATION_FILE, plan.items)
    print_plan(plan, top_n=top_n)
    return plan
