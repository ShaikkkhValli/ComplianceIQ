"""Gap Detector Agent.

For each regulatory Requirement, retrieves the top-K most semantically similar
policy chunks from ChromaDB, then asks the LLM to judge coverage and produce
a structured GapAssessment. Results are stitched into Gap records.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Iterable

from complianceiq.agents.base import BaseAgent, load_requirements, write_jsonl
from complianceiq.agents.prompts import GAP_DETECTOR_SYSTEM
from complianceiq.config import GAPS_FILE, REQUIREMENTS_FILE
from complianceiq.models import (
    CoverageQuality,
    Domain,
    Gap,
    GapAssessment,
    PolicyMatch,
    Requirement,
)

logger = logging.getLogger(__name__)


_USER_PROMPT = """\
Regulation source : {source_file}
Domain            : {domain}
Severity (stated) : {severity}

Regulatory clause:
\"\"\"
{regulation_text}
\"\"\"

Mandatory action: {mandatory_action}

Top {k} candidate policy excerpts (lower distance = closer match):
{policy_excerpts}

Decide coverage and produce the structured assessment.
"""


def _format_excerpts(matches: list[PolicyMatch]) -> str:
    if not matches:
        return "(no matching policy excerpts found)"
    lines = []
    for i, m in enumerate(matches, start=1):
        snippet = m.excerpt.replace("\n", " ").strip()
        if len(snippet) > 400:
            snippet = snippet[:400] + "..."
        lines.append(
            f"[{i}] file={m.policy_file} | location={m.location} | distance={m.distance:.3f}\n"
            f"    {snippet}"
        )
    return "\n".join(lines)


class GapDetectorAgent(BaseAgent):
    """Compares regulatory requirements against indexed policy chunks."""

    def __init__(self, top_k: int = 5, **kwargs) -> None:
        super().__init__(**kwargs)
        self.top_k = top_k
        self.chain = self.make_chain(
            system_prompt=GAP_DETECTOR_SYSTEM,
            user_template=_USER_PROMPT,
            schema=GapAssessment,
            agent_name="gap_detector",
        )

    # ── retrieval ─────────────────────────────────────────────
    def find_policy_matches(self, requirement: Requirement) -> list[PolicyMatch]:
        """Search the chunks collection for policy excerpts related to the requirement."""
        query = f"{requirement.requirement_text}\n{requirement.mandatory_action}"
        # Filter to policy chunks only AND the same domain as the regulation,
        # so we don't surface unrelated content.
        where = {
            "$and": [
                {"doc_type": {"$eq": "policy"}},
                {"domain": {"$eq": requirement.domain.value}},
            ]
        }
        hits = self.store.search_chunks(query, where=where, top_k=self.top_k)

        # Fall back to any-domain policy search if the domain filter returned nothing
        # (some policies don't fit cleanly into the regulation's exact domain bucket).
        if not hits:
            hits = self.store.search_chunks(
                query,
                where={"doc_type": "policy"},
                top_k=self.top_k,
            )

        matches: list[PolicyMatch] = []
        for h in hits:
            meta = h.metadata
            location = (
                f"page {meta.get('page_number')}" if meta.get("page_number")
                else (meta.get("section") or "")
            )
            matches.append(PolicyMatch(
                policy_file=meta.get("file_name", "unknown"),
                location=location,
                excerpt=h.text,
                distance=h.distance,
            ))
        return matches

    # ── single-requirement detection ──────────────────────────
    def detect_gap(self, requirement: Requirement) -> Gap:
        matches = self.find_policy_matches(requirement)

        if not matches:
            # No policy coverage at all — fast-path without burning an LLM call.
            return Gap(
                requirement_id=requirement.requirement_id,
                regulation_source=requirement.source_file,
                regulation_text=requirement.requirement_text,
                mandatory_action=requirement.mandatory_action,
                domain=requirement.domain,
                coverage=CoverageQuality.NOT_COVERED,
                matching_policies=[],
                gap_description="No policy excerpts were retrieved for this requirement.",
                severity=requirement.severity,
                remediation_priority=requirement.severity,
                remediation_steps=[
                    f"Draft a policy section that addresses: {requirement.mandatory_action}"
                ],
                evidence_needed=requirement.evidence_needed,
                analyzed_by=self.model_name,
            )

        try:
            assessment: GapAssessment = self.chain.invoke({
                "source_file": requirement.source_file,
                "domain": requirement.domain.value,
                "severity": requirement.severity.value,
                "regulation_text": requirement.requirement_text,
                "mandatory_action": requirement.mandatory_action,
                "k": len(matches),
                "policy_excerpts": _format_excerpts(matches),
            })
        except Exception as e:
            logger.warning("Gap assessment failed for %s: %s",
                           requirement.requirement_id, e)
            # Conservative fallback so the run doesn't blow up on transient errors.
            assessment = GapAssessment(
                coverage=CoverageQuality.PARTIALLY_COVERED,
                gap_description=f"Could not run gap assessment: {e}",
                severity=requirement.severity,
                remediation_priority=requirement.severity,
                remediation_steps=[],
            )

        return Gap(
            requirement_id=requirement.requirement_id,
            regulation_source=requirement.source_file,
            regulation_text=requirement.requirement_text,
            mandatory_action=requirement.mandatory_action,
            domain=requirement.domain,
            coverage=assessment.coverage,
            matching_policies=matches,
            gap_description=assessment.gap_description,
            severity=assessment.severity,
            remediation_priority=assessment.remediation_priority,
            remediation_steps=assessment.remediation_steps,
            evidence_needed=requirement.evidence_needed,
            analyzed_by=self.model_name,
        )

    # ── batch ─────────────────────────────────────────────────
    def detect_gaps(
        self,
        requirements: Iterable[Requirement],
        domain: Domain | None = None,
        limit: int | None = None,
    ) -> list[Gap]:
        """Run gap detection over many requirements (regulatory only)."""
        reqs = [r for r in requirements if r.doc_type == "regulatory"]
        if domain:
            reqs = [r for r in reqs if r.domain == domain]

        gaps: list[Gap] = []
        for i, req in enumerate(reqs, start=1):
            if limit and i > limit:
                logger.info("Reached gap-detection limit of %d", limit)
                break
            gap = self.detect_gap(req)
            logger.info("[%d/%d] %s — %s",
                        i, len(reqs), req.source_file, gap.coverage.value)
            gaps.append(gap)
        return gaps


# ── CLI helper ────────────────────────────────────────────────
def run_gap_detection(
    domain: Domain | None = None,
    limit: int | None = None,
    top_k: int = 5,
) -> dict:
    """End-to-end: load requirements → detect gaps → save → summarize."""
    requirements = load_requirements(REQUIREMENTS_FILE)
    agent = GapDetectorAgent(top_k=top_k)
    gaps = agent.detect_gaps(requirements, domain=domain, limit=limit)
    write_jsonl(GAPS_FILE, gaps)

    coverage_counts = Counter(g.coverage.value for g in gaps)
    severity_counts = Counter(g.severity.value for g in gaps if g.coverage != CoverageQuality.FULLY_COVERED)

    print()
    print("=" * 60)
    print("WEEK 4 — GAP DETECTION REPORT")
    print("=" * 60)
    print(f"Regulations analyzed : {len(gaps)}")
    print(f"By coverage          : {dict(coverage_counts)}")
    print(f"Open gaps by severity: {dict(severity_counts)}")
    print(f"Saved to             : {GAPS_FILE}")

    return {
        "gaps_total": len(gaps),
        "by_coverage": dict(coverage_counts),
        "by_severity": dict(severity_counts),
        "gaps_file": str(GAPS_FILE),
    }
