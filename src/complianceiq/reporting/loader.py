"""JSONL loaders shared by the dashboard and the report generators.

All Week 8 readers go through these so we have a single source of truth for
how the persisted artifacts are decoded back into Pydantic objects.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from complianceiq.config import (
    COVERAGE_FILE,
    EVIDENCE_FILE,
    GAPS_FILE,
    HISTORY_FILE,
    REMEDIATION_FILE,
    REQUIREMENTS_FILE,
    SCORE_FILE,
)
from complianceiq.models import (
    AssessmentSnapshot,
    ComplianceScore,
    CoverageAssessment,
    EvidencePacket,
    Gap,
    RegulationSummary,
    RemediationItem,
    Requirement,
)

logger = logging.getLogger(__name__)


def _read_jsonl(path: Path, model_cls):
    if not path.exists():
        logger.info("File not found, returning []: %s", path)
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(model_cls.model_validate_json(line))
            except Exception as e:
                logger.warning("Skipping malformed line in %s: %s", path, e)
    return out


def load_requirements() -> list[Requirement]:
    return _read_jsonl(REQUIREMENTS_FILE, Requirement)


def load_gaps() -> list[Gap]:
    return _read_jsonl(GAPS_FILE, Gap)


def load_coverage() -> list[CoverageAssessment]:
    return _read_jsonl(COVERAGE_FILE, CoverageAssessment)


def load_remediation() -> list[RemediationItem]:
    return _read_jsonl(REMEDIATION_FILE, RemediationItem)


def load_evidence() -> list[EvidencePacket]:
    return _read_jsonl(EVIDENCE_FILE, EvidencePacket)


def load_history() -> list[AssessmentSnapshot]:
    return _read_jsonl(HISTORY_FILE, AssessmentSnapshot)


def load_score() -> ComplianceScore | None:
    if not SCORE_FILE.exists():
        return None
    try:
        with SCORE_FILE.open("r", encoding="utf-8") as f:
            return ComplianceScore.model_validate(json.load(f))
    except Exception as e:
        logger.warning("Failed to read %s: %s", SCORE_FILE, e)
        return None


def load_summaries():
    """Regulation Monitor summaries (lazy; path lives in agent module)."""
    from complianceiq.agents.regulation_monitor import SUMMARIES_FILE
    return _read_jsonl(SUMMARIES_FILE, RegulationSummary)
