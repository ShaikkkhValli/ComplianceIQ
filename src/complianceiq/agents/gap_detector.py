"""Gap Detector Agent.

For each regulatory Requirement, retrieves the top-K most semantically similar
policy chunks from ChromaDB, then asks the LLM to judge coverage and produce
a structured GapAssessment. Results are stitched into Gap records.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
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
        output_file: Path | None = GAPS_FILE,
        resume: bool = True,
    ) -> list[Gap]:
        """Run gap detection over regulatory requirements.

        When `output_file` is set (default: GAPS_FILE), each Gap is appended
        to disk immediately so a crash mid-run loses at most one Gap.

        When `resume=True` (default) and `output_file` already contains gaps
        from a previous run, those requirement_ids are skipped — so re-running
        `orchestrate` after a crash picks up where it stopped.

        To start fresh, delete `output_file` first.
        """
        reqs = [r for r in requirements if r.doc_type == "regulatory"]
        if domain:
            reqs = [r for r in reqs if r.domain == domain]

        # Load completed requirement_ids from prior partial run (if any).
        done: set[str] = set()
        if resume and output_file and output_file.exists():
            for existing in _read_existing_gaps(output_file):
                done.add(existing.requirement_id)
            if done:
                logger.info("Resume: skipping %d already-analyzed requirements (delete %s for fresh run)",
                            len(done), output_file)

        # Set up incremental writer.
        out_fp = None
        if output_file is not None:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            out_fp = output_file.open("a", encoding="utf-8")

        gaps: list[Gap] = []
        processed = 0
        failures = 0
        try:
            for i, req in enumerate(reqs, start=1):
                if req.requirement_id in done:
                    continue
                processed += 1
                if limit and processed > limit:
                    logger.info("Reached gap-detection limit of %d", limit)
                    break

                # Per-iteration guard: a single network/API failure must not
                # crash the whole batch. The failed requirement_id is NOT
                # written, so a follow-up `orchestrate` will retry it.
                try:
                    gap = self.detect_gap(req)
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    failures += 1
                    logger.warning("[%d/%d] %s — FAILED (will retry on resume): %s",
                                   i, len(reqs), req.source_file, e)
                    continue

                logger.info("[%d/%d] %s — %s",
                            i, len(reqs), req.source_file, gap.coverage.value)
                gaps.append(gap)
                if out_fp is not None:
                    out_fp.write(json.dumps(gap.model_dump(mode="json"), ensure_ascii=False))
                    out_fp.write("\n")
                    out_fp.flush()
        finally:
            if out_fp is not None:
                out_fp.close()
            if failures:
                logger.warning("Completed with %d failed requirement(s); "
                               "re-run `orchestrate` to retry them.", failures)

        # Return the combined set of all gaps now on disk so the workflow
        # has the full collection (not just the ones produced in this run).
        if output_file is not None and output_file.exists():
            return _read_existing_gaps(output_file)
        return gaps


# ── disk helpers ──────────────────────────────────────────────
def _read_existing_gaps(path: Path) -> list[Gap]:
    out: list[Gap] = []
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(Gap.model_validate_json(line))
            except Exception:
                continue
    return out


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
