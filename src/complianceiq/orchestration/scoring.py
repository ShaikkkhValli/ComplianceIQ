"""Compliance scoring + remediation planning.

Pure-Python aggregation over Gap records — no LLM calls. Coverage scores are
deterministic; severity-weighted versions emphasize high-impact gaps.

Severity weights:  high=3, medium=2, low=1
Coverage values :  fully=1.0, partially=0.5, not=0.0
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Iterable

from complianceiq.models import (
    ComplianceScore,
    CoverageQuality,
    Domain,
    DomainScore,
    Gap,
    RemediationItem,
    RemediationPlan,
    Severity,
)

logger = logging.getLogger(__name__)


_SEVERITY_WEIGHT = {
    Severity.HIGH:   3,
    Severity.MEDIUM: 2,
    Severity.LOW:    1,
}

_COVERAGE_VALUE = {
    CoverageQuality.FULLY_COVERED:     1.0,
    CoverageQuality.PARTIALLY_COVERED: 0.5,
    CoverageQuality.NOT_COVERED:       0.0,
}


# ── scoring ───────────────────────────────────────────────────
def _round(x: float) -> float:
    return round(x, 3)


def score_domain(domain: Domain, gaps: list[Gap]) -> DomainScore:
    if not gaps:
        return DomainScore(
            domain=domain,
            total_requirements=0,
            fully_covered=0, partially_covered=0, not_covered=0,
            coverage_score=0.0, weighted_score=0.0,
            high_severity_open=0, medium_severity_open=0, low_severity_open=0,
        )

    counts = Counter(g.coverage for g in gaps)
    full = counts.get(CoverageQuality.FULLY_COVERED, 0)
    part = counts.get(CoverageQuality.PARTIALLY_COVERED, 0)
    none = counts.get(CoverageQuality.NOT_COVERED, 0)
    total = len(gaps)

    coverage_score = (full * 1.0 + part * 0.5) / total

    # Severity-weighted: each gap contributes coverage_value * severity_weight.
    num = sum(_COVERAGE_VALUE[g.coverage] * _SEVERITY_WEIGHT[g.severity] for g in gaps)
    den = sum(_SEVERITY_WEIGHT[g.severity] for g in gaps)
    weighted = num / den if den else 0.0

    open_gaps = [g for g in gaps if g.coverage != CoverageQuality.FULLY_COVERED]
    sev = Counter(g.severity for g in open_gaps)

    return DomainScore(
        domain=domain,
        total_requirements=total,
        fully_covered=full,
        partially_covered=part,
        not_covered=none,
        coverage_score=_round(coverage_score),
        weighted_score=_round(weighted),
        high_severity_open=sev.get(Severity.HIGH, 0),
        medium_severity_open=sev.get(Severity.MEDIUM, 0),
        low_severity_open=sev.get(Severity.LOW, 0),
    )


def compute_compliance_score(gaps: Iterable[Gap]) -> ComplianceScore:
    gaps_list = list(gaps)
    if not gaps_list:
        return ComplianceScore(
            overall_score=0.0, weighted_overall_score=0.0,
            total_requirements=0, fully_covered=0,
            partially_covered=0, not_covered=0,
            high_priority_gaps=0, by_domain=[],
            risk_summary="No gap records available.",
        )

    by_domain_gaps: dict[Domain, list[Gap]] = defaultdict(list)
    for g in gaps_list:
        by_domain_gaps[g.domain].append(g)

    domain_scores = [score_domain(d, dgaps) for d, dgaps in by_domain_gaps.items()]
    domain_scores.sort(key=lambda d: d.weighted_score)

    counts = Counter(g.coverage for g in gaps_list)
    total = len(gaps_list)
    full = counts.get(CoverageQuality.FULLY_COVERED, 0)
    part = counts.get(CoverageQuality.PARTIALLY_COVERED, 0)
    none = counts.get(CoverageQuality.NOT_COVERED, 0)

    overall_unweighted = (full * 1.0 + part * 0.5) / total
    num = sum(_COVERAGE_VALUE[g.coverage] * _SEVERITY_WEIGHT[g.severity] for g in gaps_list)
    den = sum(_SEVERITY_WEIGHT[g.severity] for g in gaps_list)
    overall_weighted = num / den if den else 0.0

    high_priority = sum(
        1 for g in gaps_list
        if g.coverage != CoverageQuality.FULLY_COVERED
        and (g.severity == Severity.HIGH or g.remediation_priority == Severity.HIGH)
    )

    weakest = [d.domain.value for d in domain_scores[:3]]
    risk_summary = (
        f"Org-wide weighted coverage {overall_weighted:.2f}. "
        f"{high_priority} high-priority open gaps. "
        f"Weakest domains: {', '.join(weakest)}."
    )

    return ComplianceScore(
        overall_score=_round(overall_unweighted),
        weighted_overall_score=_round(overall_weighted),
        total_requirements=total,
        fully_covered=full,
        partially_covered=part,
        not_covered=none,
        high_priority_gaps=high_priority,
        by_domain=domain_scores,
        risk_summary=risk_summary,
    )


# ── remediation planning ──────────────────────────────────────
def _priority_score(gap: Gap) -> float:
    """Higher = more urgent. Combines severity, remediation priority, and coverage gap."""
    coverage_gap = 1.0 - _COVERAGE_VALUE[gap.coverage]      # 0..1
    sev = _SEVERITY_WEIGHT[gap.severity]                    # 1..3
    pri = _SEVERITY_WEIGHT[gap.remediation_priority]        # 1..3
    return _round(coverage_gap * (sev + pri))


def build_remediation_plan(gaps: Iterable[Gap]) -> RemediationPlan:
    items: list[RemediationItem] = []
    for gap in gaps:
        # Skip fully covered — nothing to remediate.
        if gap.coverage == CoverageQuality.FULLY_COVERED:
            continue
        title = (gap.mandatory_action or gap.regulation_text or "")[:120]
        items.append(RemediationItem(
            requirement_id=gap.requirement_id,
            domain=gap.domain,
            severity=gap.severity,
            remediation_priority=gap.remediation_priority,
            coverage=gap.coverage,
            title=title,
            source_regulation=gap.regulation_source,
            mandatory_action=gap.mandatory_action,
            steps=gap.remediation_steps,
            evidence_needed=gap.evidence_needed,
            priority_score=_priority_score(gap),
        ))

    items.sort(key=lambda i: i.priority_score, reverse=True)

    pri_counts = Counter(i.remediation_priority for i in items)
    return RemediationPlan(
        items=items,
        high_priority_count=pri_counts.get(Severity.HIGH, 0),
        medium_priority_count=pri_counts.get(Severity.MEDIUM, 0),
        low_priority_count=pri_counts.get(Severity.LOW, 0),
    )


# ── pretty-print helpers ──────────────────────────────────────
def print_score(score: ComplianceScore) -> None:
    print()
    print("=" * 60)
    print("WEEK 5 — COMPLIANCE SCORE (org-wide)")
    print("=" * 60)
    print(f"Overall score (unweighted)        : {score.overall_score:.2f}")
    print(f"Overall score (severity-weighted) : {score.weighted_overall_score:.2f}")
    print(f"Total requirements                : {score.total_requirements}")
    print(f"  fully_covered                   : {score.fully_covered}")
    print(f"  partially_covered               : {score.partially_covered}")
    print(f"  not_covered                     : {score.not_covered}")
    print(f"High-priority gaps                : {score.high_priority_gaps}")
    print()
    print("By domain (weakest first):")
    for d in score.by_domain:
        print(f"  {d.domain.value:<24} weighted={d.weighted_score:.2f}  "
              f"unweighted={d.coverage_score:.2f}  "
              f"open=H{d.high_severity_open}/M{d.medium_severity_open}/L{d.low_severity_open}")
    print()
    print(f"Summary: {score.risk_summary}")


def print_plan(plan: RemediationPlan, top_n: int = 10) -> None:
    print()
    print("=" * 60)
    print(f"WEEK 5 — REMEDIATION PLAN (top {min(top_n, len(plan.items))} of {len(plan.items)})")
    print("=" * 60)
    print(f"Priority counts: high={plan.high_priority_count}  "
          f"medium={plan.medium_priority_count}  low={plan.low_priority_count}")
    for i, item in enumerate(plan.items[:top_n], start=1):
        print(f"\n{i:>2}. [{item.priority_score:.2f}] {item.domain.value} | "
              f"{item.severity.value} severity | "
              f"{item.coverage.value}")
        print(f"    {item.title}")
        print(f"    source : {item.source_regulation}")
        if item.steps:
            print(f"    steps  :")
            for s in item.steps[:4]:
                print(f"      - {s}")
