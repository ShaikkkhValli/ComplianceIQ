"""Pydantic models and enums shared across the pipeline."""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────
class Domain(str, Enum):
    """Compliance domains as defined in the problem statement."""

    CORPORATE_GOVERNANCE  = "corporate_governance"
    RISK_MANAGEMENT       = "risk_management"
    INFORMATION_SECURITY  = "information_security"
    CLAIMS_MANAGEMENT     = "claims_management"
    REINSURANCE           = "reinsurance"
    INTERNAL_AUDIT        = "internal_audit"
    FRAUD_PREVENTION      = "fraud_prevention"
    UNDERWRITING          = "underwriting"
    INVESTMENT_MANAGEMENT = "investment_management"
    SALES_DISTRIBUTION    = "sales_distribution"
    GENERAL               = "general"


class Severity(str, Enum):
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"


class CoverageQuality(str, Enum):
    """How well a policy covers a regulatory requirement."""
    FULLY_COVERED     = "fully_covered"
    PARTIALLY_COVERED = "partially_covered"
    NOT_COVERED       = "not_covered"


DocType = Literal["regulatory", "policy"]


# ── Source documents ──────────────────────────────────────────
class DocumentMetadata(BaseModel):
    source: str
    file_name: str
    doc_type: DocType
    domain: Domain
    page_number: int | None = None
    section: str | None = None
    block_type: Literal["paragraph", "table", "heading"] = "paragraph"


class Document(BaseModel):
    """A logical text block extracted from a source file (page, paragraph, or table)."""

    text: str
    metadata: DocumentMetadata


class ChunkMetadata(DocumentMetadata):
    chunk_index: int
    total_chunks: int


class Chunk(BaseModel):
    text: str
    metadata: ChunkMetadata


# ── Requirements (LLM extraction output) ──────────────────────
class RawRequirement(BaseModel):
    """Semantic fields extracted by the LLM from a single chunk."""

    requirement_text: str = Field(
        ..., description="The verbatim regulatory clause or policy statement."
    )
    mandatory_action: str = Field(
        ...,
        description=(
            "What the organization must do, in one sentence. "
            "Use 'N/A' if the chunk only describes context, not an obligation."
        ),
    )
    evidence_needed: list[str] = Field(
        default_factory=list,
        description=(
            "Documentation, logs, or artifacts that would prove compliance. "
            "Empty list if no evidence is implied."
        ),
    )
    severity: Severity = Field(
        ...,
        description=(
            "high = breach causes regulatory penalty/material harm; "
            "medium = non-compliance creates audit findings; "
            "low = best-practice or advisory."
        ),
    )
    suggested_domain: Domain | None = Field(
        default=None,
        description="Optional refinement of the domain if the chunk fits one better.",
    )


class RequirementBatch(BaseModel):
    """Wrapper used as the LLM structured-output schema (a chunk may contain 0+ requirements)."""

    requirements: list[RawRequirement] = Field(default_factory=list)


class Requirement(BaseModel):
    """Full enriched requirement record persisted to disk."""

    requirement_id: str
    source_file: str
    page_or_section: str
    doc_type: DocType
    domain: Domain
    requirement_text: str
    mandatory_action: str
    evidence_needed: list[str]
    severity: Severity
    extracted_by: str

    @classmethod
    def from_raw(
        cls,
        raw: RawRequirement,
        chunk_meta: ChunkMetadata,
        extracted_by: str,
    ) -> "Requirement":
        page_or_section = (
            f"page {chunk_meta.page_number}"
            if chunk_meta.page_number is not None
            else (chunk_meta.section or "")
        )
        # Stable ID: hash of source + clause text (so re-runs are idempotent).
        rid_input = f"{chunk_meta.file_name}|{page_or_section}|{raw.requirement_text}"
        requirement_id = hashlib.sha1(rid_input.encode("utf-8")).hexdigest()[:16]

        return cls(
            requirement_id=requirement_id,
            source_file=chunk_meta.file_name,
            page_or_section=page_or_section,
            doc_type=chunk_meta.doc_type,
            domain=raw.suggested_domain or chunk_meta.domain,
            requirement_text=raw.requirement_text.strip(),
            mandatory_action=raw.mandatory_action.strip(),
            evidence_needed=[e.strip() for e in raw.evidence_needed if e.strip()],
            severity=raw.severity,
            extracted_by=extracted_by,
        )


# ── Agent outputs (Week 4) ────────────────────────────────────
class PolicyMatch(BaseModel):
    """A policy excerpt that the Gap Detector considered as evidence."""
    policy_file: str
    location: str           # page or section
    excerpt: str            # truncated chunk text
    distance: float         # cosine distance from the regulation; lower = closer


class GapAssessment(BaseModel):
    """LLM-produced judgment for a single regulation vs its candidate policies.

    This is the Pydantic schema used as the structured-output target by the
    Gap Detector chain.
    """
    coverage: CoverageQuality
    gap_description: str = Field(
        ..., description="What is missing or weak. Empty if fully covered."
    )
    severity: Severity = Field(
        ..., description="Severity of the gap if any (use the regulation's severity if covered)."
    )
    remediation_priority: Severity
    remediation_steps: list[str] = Field(
        default_factory=list,
        description="Concrete actions to close the gap. Empty if fully covered.",
    )


class Gap(BaseModel):
    """Final enriched gap record persisted to gaps.jsonl."""
    requirement_id: str
    regulation_source: str
    regulation_text: str
    mandatory_action: str
    domain: Domain
    coverage: CoverageQuality
    matching_policies: list[PolicyMatch]
    gap_description: str
    severity: Severity
    remediation_priority: Severity
    remediation_steps: list[str]
    evidence_needed: list[str]
    analyzed_by: str


class CoverageAssessment(BaseModel):
    """Domain-level coverage roll-up produced by the Policy Analyzer."""
    domain: Domain
    total_requirements: int
    fully_covered: int
    partially_covered: int
    not_covered: int
    coverage_score: float = Field(..., description="0..1; weighted average of coverage levels.")
    strongest_areas: list[str] = Field(default_factory=list)
    weakest_areas: list[str] = Field(default_factory=list)
    summary: str


class RegulationSummary(BaseModel):
    """High-level digest of a regulatory file produced by the Regulation Monitor."""
    source_file: str
    domain: Domain
    total_requirements: int
    high_severity_count: int
    medium_severity_count: int
    low_severity_count: int
    key_obligations: list[str]
    summary: str


# ── Week 5: Evidence & scoring ────────────────────────────────
class EvidenceItem(BaseModel):
    """A single chunk of supporting evidence for a requirement."""
    source_file: str
    location: str
    text: str
    doc_type: DocType
    distance: float | None = None  # populated when retrieved via vector search


class EvidencePacket(BaseModel):
    """All evidence collected for a single regulatory requirement."""
    requirement_id: str
    regulation: EvidenceItem
    policy_evidence: list[EvidenceItem] = Field(default_factory=list)
    additional_regulatory_context: list[EvidenceItem] = Field(default_factory=list)


class DomainScore(BaseModel):
    """Score for a single compliance domain."""
    domain: Domain
    total_requirements: int
    fully_covered: int
    partially_covered: int
    not_covered: int
    coverage_score: float = Field(..., description="Unweighted: (full + 0.5*partial)/total")
    weighted_score: float = Field(..., description="Severity-weighted version of coverage_score")
    high_severity_open: int
    medium_severity_open: int
    low_severity_open: int


class ComplianceScore(BaseModel):
    """Org-wide compliance score with per-domain breakdown."""
    overall_score: float
    weighted_overall_score: float
    total_requirements: int
    fully_covered: int
    partially_covered: int
    not_covered: int
    high_priority_gaps: int
    by_domain: list[DomainScore]
    risk_summary: str = ""


class RemediationItem(BaseModel):
    """One actionable remediation entry, prioritized."""
    requirement_id: str
    domain: Domain
    severity: Severity
    remediation_priority: Severity
    coverage: CoverageQuality
    title: str
    source_regulation: str
    mandatory_action: str
    steps: list[str]
    evidence_needed: list[str]
    priority_score: float = Field(..., description="Numeric priority for sorting; higher = more urgent.")


class RemediationPlan(BaseModel):
    """Prioritized list of remediation items."""
    items: list[RemediationItem]
    high_priority_count: int
    medium_priority_count: int
    low_priority_count: int


# ── Week 7: Observability ─────────────────────────────────────
class AuditEvent(BaseModel):
    """A single immutable entry in the compliance audit log."""
    event_id: str
    timestamp: str            # ISO 8601 UTC
    run_id: str               # workflow run that emitted this event
    event_type: str           # e.g. gap_detected, score_computed, requirements_extracted
    actor: str                # agent name + model, or "system"
    entity_type: str | None = None   # "requirement", "domain", "file", ...
    entity_id: str | None = None
    payload: dict = Field(default_factory=dict)


class AssessmentSnapshot(BaseModel):
    """Point-in-time snapshot of one full compliance assessment."""
    run_id: str
    started_at: str
    finished_at: str
    overall_score: float
    weighted_overall_score: float
    total_requirements: int
    fully_covered: int
    partially_covered: int
    not_covered: int
    high_priority_gaps: int
    by_domain_weighted_scores: dict[str, float] = Field(default_factory=dict)
    n_orphan_requirements: int | None = None
    notes: str = ""
