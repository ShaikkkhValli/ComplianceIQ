"""Regulation Monitor Agent.

Reads requirements.jsonl and produces per-file digests (RegulationSummary)
that compliance officers can scan in 30 seconds. Optionally filters by
source file or domain.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Iterable

from pydantic import BaseModel, Field

from complianceiq.agents.base import BaseAgent, load_requirements, write_jsonl
from complianceiq.agents.prompts import REGULATION_MONITOR_SYSTEM
from complianceiq.config import PROCESSED_DIR, REQUIREMENTS_FILE
from complianceiq.models import Domain, RegulationSummary, Requirement, Severity

logger = logging.getLogger(__name__)

SUMMARIES_FILE = PROCESSED_DIR / "regulation_summaries.jsonl"


_USER_PROMPT = """\
Source file : {source_file}
Domain      : {domain}
Total reqs  : {total} (high={high}, medium={medium}, low={low})

Mandatory actions extracted from this document:
{actions}

Produce key_obligations and a 3-5 sentence summary.
"""


class _RegulationDigestLLM(BaseModel):
    key_obligations: list[str] = Field(default_factory=list)
    summary: str


class RegulationMonitorAgent(BaseAgent):
    """Summarize regulatory documents from already-extracted requirements."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.chain = self.make_chain(
            system_prompt=REGULATION_MONITOR_SYSTEM,
            user_template=_USER_PROMPT,
            schema=_RegulationDigestLLM,
            agent_name="regulation_monitor",
        )

    def summarize_file(self, file_name: str, reqs: list[Requirement]) -> RegulationSummary:
        if not reqs:
            raise ValueError(f"No requirements provided for {file_name}")

        # All reqs share the same source_file; use the most common domain.
        domain = Counter(r.domain for r in reqs).most_common(1)[0][0]
        sev_counts = Counter(r.severity.value for r in reqs)
        actions = "\n".join(f"- {r.mandatory_action}" for r in reqs[:30])

        try:
            digest = self.chain.invoke({
                "source_file": file_name,
                "domain": domain.value,
                "total": len(reqs),
                "high":   sev_counts.get(Severity.HIGH.value, 0),
                "medium": sev_counts.get(Severity.MEDIUM.value, 0),
                "low":    sev_counts.get(Severity.LOW.value, 0),
                "actions": actions,
            })
        except Exception as e:
            logger.warning("Summary generation failed for %s: %s", file_name, e)
            digest = _RegulationDigestLLM(
                key_obligations=[r.mandatory_action for r in reqs[:5]],
                summary="(LLM summary unavailable.)",
            )

        return RegulationSummary(
            source_file=file_name,
            domain=domain,
            total_requirements=len(reqs),
            high_severity_count=sev_counts.get(Severity.HIGH.value, 0),
            medium_severity_count=sev_counts.get(Severity.MEDIUM.value, 0),
            low_severity_count=sev_counts.get(Severity.LOW.value, 0),
            key_obligations=digest.key_obligations,
            summary=digest.summary,
        )

    def summarize_all(
        self,
        requirements: Iterable[Requirement],
        file_filter: str | None = None,
        domain: Domain | None = None,
    ) -> list[RegulationSummary]:
        reqs = [r for r in requirements if r.doc_type == "regulatory"]
        if domain:
            reqs = [r for r in reqs if r.domain == domain]
        if file_filter:
            reqs = [r for r in reqs if file_filter.lower() in r.source_file.lower()]

        by_file: dict[str, list[Requirement]] = defaultdict(list)
        for r in reqs:
            by_file[r.source_file].append(r)

        summaries: list[RegulationSummary] = []
        for file_name, file_reqs in by_file.items():
            logger.info("Summarizing %s (%d reqs)", file_name, len(file_reqs))
            summaries.append(self.summarize_file(file_name, file_reqs))
        return summaries


# ── CLI helper ────────────────────────────────────────────────
def run_regulation_summary(
    file_filter: str | None = None,
    domain: Domain | None = None,
) -> dict:
    requirements = load_requirements(REQUIREMENTS_FILE)
    agent = RegulationMonitorAgent()
    summaries = agent.summarize_all(requirements, file_filter=file_filter, domain=domain)
    write_jsonl(SUMMARIES_FILE, summaries)

    print()
    print("=" * 60)
    print("WEEK 4 — REGULATION MONITOR DIGESTS")
    print("=" * 60)
    for s in summaries:
        print(f"\n{s.source_file}  [{s.domain.value}]")
        print(f"  reqs: {s.total_requirements}  "
              f"(H={s.high_severity_count} M={s.medium_severity_count} L={s.low_severity_count})")
        print(f"  summary: {s.summary}")
        if s.key_obligations:
            print("  key obligations:")
            for k in s.key_obligations:
                print(f"    - {k}")

    print(f"\nSaved to: {SUMMARIES_FILE}")
    return {"summaries": len(summaries), "summaries_file": str(SUMMARIES_FILE)}
