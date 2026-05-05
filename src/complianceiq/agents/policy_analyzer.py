"""Policy Analyzer Agent.

Aggregates Gap records into per-domain coverage assessments. Heavy lifting
(per-requirement coverage decision) was already done by the Gap Detector;
this agent rolls up and produces an executive-friendly summary per domain.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field

from complianceiq.agents.base import BaseAgent, write_jsonl
from complianceiq.agents.prompts import POLICY_ANALYZER_SYSTEM
from complianceiq.config import COVERAGE_FILE, GAPS_FILE
from complianceiq.models import (
    CoverageAssessment,
    CoverageQuality,
    Domain,
    Gap,
)

logger = logging.getLogger(__name__)


_USER_PROMPT = """\
Domain: {domain}

Requirements: {total_requirements}
  fully_covered     : {fully_covered}
  partially_covered : {partially_covered}
  not_covered       : {not_covered}

Worst-covered requirements (verbatim mandatory actions):
{worst_examples}

Best-covered requirements (verbatim mandatory actions):
{best_examples}

Produce the coverage assessment.
"""


# Schema returned by the LLM (subset of CoverageAssessment that the LLM produces).
class _CoverageAssessmentLLM(BaseModel):
    coverage_score: float = Field(..., ge=0.0, le=1.0)
    strongest_areas: list[str] = Field(default_factory=list)
    weakest_areas: list[str] = Field(default_factory=list)
    summary: str


def _load_gaps(path: Path) -> list[Gap]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python main.py analyze-gaps` first."
        )
    out: list[Gap] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(Gap.model_validate_json(line))
    return out


class PolicyAnalyzerAgent(BaseAgent):
    """Roll Gap records into per-domain CoverageAssessment objects."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.chain = self.make_chain(
            system_prompt=POLICY_ANALYZER_SYSTEM,
            user_template=_USER_PROMPT,
            schema=_CoverageAssessmentLLM,
            agent_name="policy_analyzer",
        )

    @staticmethod
    def _deterministic_score(counts: Counter) -> float:
        total = sum(counts.values())
        if total == 0:
            return 0.0
        full = counts.get(CoverageQuality.FULLY_COVERED.value, 0)
        part = counts.get(CoverageQuality.PARTIALLY_COVERED.value, 0)
        return round((full * 1.0 + part * 0.5) / total, 3)

    def assess_domain(self, gaps: list[Gap]) -> CoverageAssessment | None:
        if not gaps:
            return None

        domain = gaps[0].domain
        counts = Counter(g.coverage.value for g in gaps)
        total = len(gaps)

        # Sample 3 worst and 3 best by coverage tier.
        worst = [g for g in gaps if g.coverage == CoverageQuality.NOT_COVERED][:3]
        if len(worst) < 3:
            worst += [g for g in gaps
                      if g.coverage == CoverageQuality.PARTIALLY_COVERED][: 3 - len(worst)]
        best = [g for g in gaps if g.coverage == CoverageQuality.FULLY_COVERED][:3]

        worst_examples = "\n".join(f"- {g.mandatory_action}" for g in worst) or "(none)"
        best_examples  = "\n".join(f"- {g.mandatory_action}" for g in best) or "(none)"

        try:
            llm_out = self.chain.invoke({
                "domain": domain.value,
                "total_requirements": total,
                "fully_covered":     counts.get(CoverageQuality.FULLY_COVERED.value, 0),
                "partially_covered": counts.get(CoverageQuality.PARTIALLY_COVERED.value, 0),
                "not_covered":       counts.get(CoverageQuality.NOT_COVERED.value, 0),
                "worst_examples":    worst_examples,
                "best_examples":     best_examples,
            })
        except Exception as e:
            logger.warning("Policy analyzer LLM call failed for %s: %s", domain.value, e)
            llm_out = _CoverageAssessmentLLM(
                coverage_score=self._deterministic_score(counts),
                strongest_areas=[],
                weakest_areas=[],
                summary="(LLM summary unavailable; falling back to deterministic score.)",
            )

        # Always trust the deterministic score over the LLM's free-form one.
        score = self._deterministic_score(counts)

        return CoverageAssessment(
            domain=domain,
            total_requirements=total,
            fully_covered=counts.get(CoverageQuality.FULLY_COVERED.value, 0),
            partially_covered=counts.get(CoverageQuality.PARTIALLY_COVERED.value, 0),
            not_covered=counts.get(CoverageQuality.NOT_COVERED.value, 0),
            coverage_score=score,
            strongest_areas=llm_out.strongest_areas,
            weakest_areas=llm_out.weakest_areas,
            summary=llm_out.summary,
        )

    def assess_all(self, gaps: Iterable[Gap]) -> list[CoverageAssessment]:
        gaps_list = list(gaps)
        by_domain: dict[Domain, list[Gap]] = {}
        for g in gaps_list:
            by_domain.setdefault(g.domain, []).append(g)

        assessments: list[CoverageAssessment] = []
        for domain, dgaps in by_domain.items():
            logger.info("Analyzing domain: %s (%d gaps)", domain.value, len(dgaps))
            a = self.assess_domain(dgaps)
            if a:
                assessments.append(a)
        return assessments


# ── CLI helper ────────────────────────────────────────────────
def run_coverage_analysis(domain_filter: Domain | None = None) -> dict:
    gaps = _load_gaps(GAPS_FILE)
    if domain_filter:
        gaps = [g for g in gaps if g.domain == domain_filter]
        if not gaps:
            print(f"No gaps found for domain {domain_filter.value}")
            return {"assessments": 0}

    agent = PolicyAnalyzerAgent()
    assessments = agent.assess_all(gaps)
    write_jsonl(COVERAGE_FILE, assessments)

    print()
    print("=" * 60)
    print("WEEK 4 — POLICY COVERAGE ASSESSMENT")
    print("=" * 60)
    for a in sorted(assessments, key=lambda x: x.coverage_score):
        print(f"\n{a.domain.value}  —  coverage {a.coverage_score:.2f}")
        print(f"  total={a.total_requirements}  full={a.fully_covered}  "
              f"part={a.partially_covered}  none={a.not_covered}")
        if a.weakest_areas:
            print(f"  weakest: {', '.join(a.weakest_areas)}")
        if a.strongest_areas:
            print(f"  strongest: {', '.join(a.strongest_areas)}")
        print(f"  summary: {a.summary}")

    print(f"\nSaved to: {COVERAGE_FILE}")
    return {"assessments": len(assessments), "coverage_file": str(COVERAGE_FILE)}
