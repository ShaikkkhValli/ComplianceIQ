"""Compliance scoring is pure-Python and must be deterministic + reproducible."""

from complianceiq.models import (
    CoverageQuality,
    Domain,
    Gap,
    PolicyMatch,
    Severity,
)
from complianceiq.orchestration.scoring import (
    build_remediation_plan,
    compute_compliance_score,
    score_domain,
)


def _gap(coverage: CoverageQuality,
         severity: Severity = Severity.MEDIUM,
         domain: Domain = Domain.RISK_MANAGEMENT,
         req_id: str = "abc") -> Gap:
    return Gap(
        requirement_id=req_id,
        regulation_source="reg.pdf",
        regulation_text="Some clause.",
        mandatory_action="Do something.",
        domain=domain,
        coverage=coverage,
        matching_policies=[],
        gap_description="" if coverage == CoverageQuality.FULLY_COVERED else "missing",
        severity=severity,
        remediation_priority=severity,
        remediation_steps=[],
        evidence_needed=[],
        analyzed_by="test",
    )


def test_empty_score_safe():
    score = compute_compliance_score([])
    assert score.overall_score == 0.0
    assert score.weighted_overall_score == 0.0
    assert score.total_requirements == 0
    assert score.by_domain == []


def test_all_fully_covered_is_one():
    gaps = [_gap(CoverageQuality.FULLY_COVERED) for _ in range(5)]
    score = compute_compliance_score(gaps)
    assert score.overall_score == 1.0
    assert score.weighted_overall_score == 1.0
    assert score.fully_covered == 5


def test_all_not_covered_is_zero():
    gaps = [_gap(CoverageQuality.NOT_COVERED) for _ in range(5)]
    score = compute_compliance_score(gaps)
    assert score.overall_score == 0.0
    assert score.weighted_overall_score == 0.0


def test_partial_is_half():
    gaps = [_gap(CoverageQuality.PARTIALLY_COVERED) for _ in range(4)]
    score = compute_compliance_score(gaps)
    assert score.overall_score == 0.5


def test_severity_weighted_punishes_high():
    # Two gaps: one high-severity not_covered, one low-severity fully_covered
    gaps = [
        _gap(CoverageQuality.NOT_COVERED, severity=Severity.HIGH, req_id="r1"),
        _gap(CoverageQuality.FULLY_COVERED, severity=Severity.LOW, req_id="r2"),
    ]
    score = compute_compliance_score(gaps)
    # Unweighted: (0 + 1) / 2 = 0.5
    assert score.overall_score == 0.5
    # Weighted: (0*3 + 1*1) / (3+1) = 0.25 — high gap dominates
    assert score.weighted_overall_score == 0.25


def test_high_priority_gap_count():
    gaps = [
        _gap(CoverageQuality.NOT_COVERED, severity=Severity.HIGH, req_id="r1"),
        _gap(CoverageQuality.NOT_COVERED, severity=Severity.LOW, req_id="r2"),
        _gap(CoverageQuality.FULLY_COVERED, severity=Severity.HIGH, req_id="r3"),
    ]
    score = compute_compliance_score(gaps)
    assert score.high_priority_gaps == 1  # only r1: not_covered AND high


def test_remediation_excludes_fully_covered():
    gaps = [
        _gap(CoverageQuality.FULLY_COVERED, req_id="r1"),
        _gap(CoverageQuality.PARTIALLY_COVERED, req_id="r2"),
        _gap(CoverageQuality.NOT_COVERED, req_id="r3"),
    ]
    plan = build_remediation_plan(gaps)
    ids = {i.requirement_id for i in plan.items}
    assert "r1" not in ids
    assert "r2" in ids and "r3" in ids


def test_remediation_sorted_high_priority_first():
    gaps = [
        _gap(CoverageQuality.PARTIALLY_COVERED, severity=Severity.LOW, req_id="r-low"),
        _gap(CoverageQuality.NOT_COVERED, severity=Severity.HIGH, req_id="r-high"),
    ]
    plan = build_remediation_plan(gaps)
    # not_covered + HIGH severity should rank above partial + LOW
    assert plan.items[0].requirement_id == "r-high"


def test_score_is_reproducible():
    gaps = [
        _gap(CoverageQuality.NOT_COVERED, severity=Severity.HIGH, req_id="r1"),
        _gap(CoverageQuality.PARTIALLY_COVERED, severity=Severity.MEDIUM, req_id="r2"),
        _gap(CoverageQuality.FULLY_COVERED, severity=Severity.LOW, req_id="r3"),
    ]
    s1 = compute_compliance_score(gaps)
    s2 = compute_compliance_score(gaps)
    assert s1.overall_score == s2.overall_score
    assert s1.weighted_overall_score == s2.weighted_overall_score
