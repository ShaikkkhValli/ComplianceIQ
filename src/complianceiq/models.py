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
    FULLY_COVERED     = "fully_covered"
    PARTIALLY_COVERED = "partially_covered"
    NOT_COVERED       = "not_covered"


DocType = Literal["regulatory", "policy"]


# ── Citations / clause references (rubric §5: domain extraction) ──
class ClauseRef(BaseModel):
    """Structured citation parsed from a regulatory clause string.

    Examples:
        "Regulation 4(2)(a)" -> ClauseRef(article="4", sub_clauses=["2","a"])
        "Section 12.3.1"     -> ClauseRef(article="12", sub_clauses=["3","1"])
    """
    raw: str = Field(..., description="The original citation string.")
    article: str | None = Field(None, description="Top-level numeric clause id.")
    sub_clauses: list[str] = Field(
        default_factory=list,
        description="Nested sub-clause path, e.g. ['2','a'] for '4(2)(a)'.",
    )
    page: int | None = None

    def canonical(self) -> str:
        if not self.article:
            return self.raw.strip().lower()
        return ".".join([self.article] + list(self.sub_clauses)).lower()


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
    requirement_text: str = Field(..., description="The verbatim regulatory clause.")
    mandatory_action: str = Field(
        ..., description="What the org must do, in one sentence. Use 'N/A' for context only.",
    )
    evidence_needed: list[str] = Field(
        default_factory=list,
        description="Documentation/logs that would prove compliance.",
    )
    severity: Severity = Field(
        ...,
        description="high = penalty/material harm; medium = audit findings; low = advisory.",
    )
    suggested_domain: Domain | None = Field(
        default=None, description="Optional refinement of the domain.",
    )


class RequirementBatch(BaseModel):
    requirements: list[RawRequirement] = Field(default_factory=list)


class Requirement(BaseModel):
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
    def from_raw(cls, raw, chunk_meta, extracted_by):
        page_or_section = (
            f"page {chunk_meta.page_number}" if chunk_meta.page_number is not None
            else (chunk_meta.section or "")
        )
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


# ── Agent outputs ─────────────────────────────────────────────
class PolicyMatch(BaseModel):
    policy_file: str
    location: str
    excerpt: str
    distance: float


class GapAssessment(BaseModel):
    """LLM output schema for a single regulation vs candidate policies."""
    coverage: CoverageQuality
    gap_description: str = Field(..., description="What is missing or weak. Empty if fully covered.")
    severity: Severity = Field(..., description="Severity of the gap if any.")
    remediation_priority: Severity
    remediation_steps: list[str] = Field(
        default_factory=list,
        description="Concrete actions to close the gap.",
    )
    confidence: float = Field(
        default=0.8, ge=0.0, le=1.0,
        description=(
            "Self-assessed confidence in this coverage decision (0..1). "
            "0.9+ = excerpts directly address the requirement; "
            "0.5 = excerpts tangential; <0.4 = no clear evidence."
        ),
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
    confidence: float = Field(
        default=0.8, ge=0.0, le=1.0,
        description="Confidence in the coverage decision (propagated from GapAssessment).",
    )
    needs_review: bool = Field(
        default=False,
        description="True when confidence is below the HITL threshold.",
    )
    clause_ref: ClauseRef | None = Field(
        default=None,
        description="Structured citation parsed from the regulation_source / regulation_text.",
    )


class CoverageAssessment(BaseModel):
    domain: Domain
    total_requirements: int
    fully_covered: int
    partially_covered: int
    not_covered: int
    coverage_score: float = Field(..., description="0..1; weighted average of coverage levels.")
    strongest_areas: list[str] = Field(default_factory=list)
    weakest_areas: list[str] = Field(default_factory=list)
    summary: str
    confidence: float = Field(
        default=0.8, ge=0.0, le=1.0,
        description="Confidence in the domain-level summary (0..1).",
    )


class RegulationSummary(BaseModel):
    source_file: str
    domain: Domain
    total_requirements: int
    high_severity_count: int
    medium_severity_count: int
    low_severity_count: int
    key_obligations: list[str]
    summary: str


# ── Evidence & scoring ────────────────────────────────────────
class EvidenceItem(BaseModel):
    source_file: str
    location: str
    text: str
    doc_type: DocType
    distance: float | None = None


class EvidencePacket(BaseModel):
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
    items: list[RemediationItem]
    high_priority_count: int
    medium_priority_count: int
    low_priority_count: int


# ── Observability ─────────────────────────────────────────────
class AuditEvent(BaseModel):
    event_id: str
    timestamp: str
    run_id: str
    event_type: str
    actor: str
    entity_type: str | None = None
    entity_id: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)


class AssessmentSnapshot(BaseModel):
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
