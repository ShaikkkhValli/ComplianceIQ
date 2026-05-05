"""Evidence Collector.

For each requirement (or each Gap), retrieves and packages the underlying
regulatory clause and supporting/non-supporting policy excerpts into a
structured EvidencePacket suitable for audit trails.
"""

from __future__ import annotations

import logging

from complianceiq.models import (
    EvidenceItem,
    EvidencePacket,
    Gap,
    Requirement,
)
from complianceiq.vectorstore.store import ChromaStore, SearchHit

logger = logging.getLogger(__name__)


class EvidenceCollector:
    """Bundles regulation + supporting policy evidence per requirement."""

    def __init__(self, store: ChromaStore | None = None, top_k: int = 5) -> None:
        self.store = store or ChromaStore.load()
        self.top_k = top_k

    # ── helpers ───────────────────────────────────────────────
    @staticmethod
    def _hit_to_item(hit: SearchHit, doc_type: str) -> EvidenceItem:
        meta = hit.metadata
        location = (
            f"page {meta.get('page_number')}" if meta.get("page_number")
            else (meta.get("section") or "")
        )
        return EvidenceItem(
            source_file=meta.get("file_name", "unknown"),
            location=location,
            text=hit.text,
            doc_type=doc_type,  # type: ignore[arg-type]
            distance=hit.distance,
        )

    @staticmethod
    def _regulation_item_from_requirement(req: Requirement) -> EvidenceItem:
        return EvidenceItem(
            source_file=req.source_file,
            location=req.page_or_section,
            text=req.requirement_text,
            doc_type="regulatory",
            distance=None,
        )

    # ── per-requirement collection ────────────────────────────
    def collect_for_requirement(self, requirement: Requirement) -> EvidencePacket:
        query = f"{requirement.requirement_text}\n{requirement.mandatory_action}"

        # Domain-filtered policy hits first.
        policy_hits = self.store.search_chunks(
            query,
            where={
                "$and": [
                    {"doc_type": {"$eq": "policy"}},
                    {"domain": {"$eq": requirement.domain.value}},
                ]
            },
            top_k=self.top_k,
        )
        if not policy_hits:
            policy_hits = self.store.search_chunks(
                query, where={"doc_type": "policy"}, top_k=self.top_k
            )

        # Additional regulatory context from related sections of the same domain.
        reg_hits = self.store.search_chunks(
            query,
            where={
                "$and": [
                    {"doc_type": {"$eq": "regulatory"}},
                    {"domain": {"$eq": requirement.domain.value}},
                ]
            },
            top_k=3,
        )

        return EvidencePacket(
            requirement_id=requirement.requirement_id,
            regulation=self._regulation_item_from_requirement(requirement),
            policy_evidence=[self._hit_to_item(h, "policy") for h in policy_hits],
            additional_regulatory_context=[
                self._hit_to_item(h, "regulatory") for h in reg_hits
            ],
        )

    # ── enrichment from existing Gap records ──────────────────
    def packet_from_gap(self, gap: Gap) -> EvidencePacket:
        """Build an EvidencePacket from an already-computed Gap.

        Reuses gap.matching_policies (already retrieved during gap detection)
        and only fetches the additional regulatory context separately.
        """
        regulation = EvidenceItem(
            source_file=gap.regulation_source,
            location="",
            text=gap.regulation_text,
            doc_type="regulatory",
            distance=None,
        )
        policy_evidence = [
            EvidenceItem(
                source_file=m.policy_file,
                location=m.location,
                text=m.excerpt,
                doc_type="policy",
                distance=m.distance,
            )
            for m in gap.matching_policies
        ]

        # Extra regulatory context (siblings / related clauses).
        reg_hits = self.store.search_chunks(
            f"{gap.regulation_text}\n{gap.mandatory_action}",
            where={
                "$and": [
                    {"doc_type": {"$eq": "regulatory"}},
                    {"domain": {"$eq": gap.domain.value}},
                ]
            },
            top_k=3,
        )
        additional = [self._hit_to_item(h, "regulatory") for h in reg_hits]

        return EvidencePacket(
            requirement_id=gap.requirement_id,
            regulation=regulation,
            policy_evidence=policy_evidence,
            additional_regulatory_context=additional,
        )
