"""ComplianceGraph — NetworkX graph linking regulations, policies, and domains.

Schema:
    Domain node ── contains ──> Requirement node
    Requirement node ── from_file ──> Regulatory file node
    Requirement node ── covered_by (weighted) ──> PolicyChunk node
    PolicyChunk node ── in_file ──> PolicyFile node
    PolicyFile node ── in_domain ──> Domain node

Node IDs are namespaced: req:<id>, chunk:<id>, pol_file:<name>,
reg_file:<name>, domain:<value>.

Edges of type 'covered_by' carry: coverage (full/partial/none), distance,
weight (1 - distance), severity.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import networkx as nx

from complianceiq.config import (
    GAPS_FILE,
    GRAPH_FILE,
    GRAPH_JSON_FILE,
    REQUIREMENTS_FILE,
    ensure_graph_dir,
)
from complianceiq.models import (
    CoverageQuality,
    Domain,
    Gap,
    PolicyMatch,
    Requirement,
)

logger = logging.getLogger(__name__)


# ── ID helpers ────────────────────────────────────────────────
def req_node(req_id: str) -> str:        return f"req:{req_id}"
def domain_node(d: Domain | str) -> str:
    val = d.value if isinstance(d, Domain) else d
    return f"domain:{val}"
def reg_file_node(name: str) -> str:     return f"reg_file:{name}"
def pol_file_node(name: str) -> str:     return f"pol_file:{name}"
def chunk_node(file_name: str, location: str, excerpt: str) -> str:
    h = hashlib.sha1(f"{file_name}|{location}|{excerpt}".encode("utf-8")).hexdigest()[:12]
    return f"chunk:{h}"


# ── builder ───────────────────────────────────────────────────
class ComplianceGraph:
    """Build, query, and persist the regulation-policy mapping graph."""

    def __init__(self, graph: nx.DiGraph | None = None) -> None:
        self.g: nx.DiGraph = graph if graph is not None else nx.DiGraph()

    # ── construction ──────────────────────────────────────────
    @classmethod
    def build(cls,
              requirements: list[Requirement],
              gaps: list[Gap]) -> "ComplianceGraph":
        graph = cls()
        for r in requirements:
            graph._add_requirement(r)
        for g in gaps:
            graph._add_gap(g)
        logger.info("Built graph: %d nodes, %d edges",
                    graph.g.number_of_nodes(), graph.g.number_of_edges())
        return graph

    @classmethod
    def build_from_artifacts(cls) -> "ComplianceGraph":
        if not Path(REQUIREMENTS_FILE).exists():
            raise FileNotFoundError(
                f"{REQUIREMENTS_FILE} not found. Run `python main.py ingest --extract` first."
            )
        requirements = _read_jsonl(REQUIREMENTS_FILE, Requirement)

        gaps: list[Gap] = []
        if Path(GAPS_FILE).exists():
            gaps = _read_jsonl(GAPS_FILE, Gap)
        else:
            logger.warning(
                "%s not found — graph will be built without coverage edges.", GAPS_FILE
            )
        return cls.build(requirements, gaps)

    # ── node insertion ────────────────────────────────────────
    def _add_requirement(self, r: Requirement) -> None:
        rn = req_node(r.requirement_id)
        self.g.add_node(rn,
                        type="requirement",
                        text=r.requirement_text[:200],
                        mandatory_action=r.mandatory_action[:200],
                        domain=r.domain.value,
                        severity=r.severity.value,
                        source_file=r.source_file)

        dn = domain_node(r.domain)
        self.g.add_node(dn, type="domain", name=r.domain.value)
        self.g.add_edge(dn, rn, relation="contains")

        rfn = reg_file_node(r.source_file)
        self.g.add_node(rfn, type="regulatory_file", name=r.source_file)
        self.g.add_edge(rn, rfn, relation="from_file")
        self.g.add_edge(rfn, dn, relation="in_domain")

    def _add_gap(self, gap: Gap) -> None:
        rn = req_node(gap.requirement_id)
        # The requirement might not be in the graph if requirements.jsonl was filtered
        if rn not in self.g:
            self.g.add_node(rn,
                            type="requirement",
                            text=gap.regulation_text[:200],
                            mandatory_action=gap.mandatory_action[:200],
                            domain=gap.domain.value,
                            severity=gap.severity.value,
                            source_file=gap.regulation_source)

        # Annotate the requirement with overall coverage status from the gap.
        self.g.nodes[rn]["coverage"] = gap.coverage.value
        self.g.nodes[rn]["remediation_priority"] = gap.remediation_priority.value

        for pm in gap.matching_policies:
            self._add_policy_match(rn, pm, gap)

    def _add_policy_match(self, rn: str, pm: PolicyMatch, gap: Gap) -> None:
        cn = chunk_node(pm.policy_file, pm.location, pm.excerpt)
        self.g.add_node(cn,
                        type="policy_chunk",
                        file_name=pm.policy_file,
                        location=pm.location,
                        excerpt=pm.excerpt[:300])

        weight = max(0.0, 1.0 - float(pm.distance))
        self.g.add_edge(rn, cn,
                        relation="covered_by",
                        coverage=gap.coverage.value,
                        distance=float(pm.distance),
                        weight=weight,
                        severity=gap.severity.value)

        pfn = pol_file_node(pm.policy_file)
        self.g.add_node(pfn, type="policy_file", name=pm.policy_file)
        self.g.add_edge(cn, pfn, relation="in_file")

        dn = domain_node(gap.domain)
        self.g.add_node(dn, type="domain", name=gap.domain.value)
        self.g.add_edge(pfn, dn, relation="in_domain")

    # ── persistence ───────────────────────────────────────────
    def save(self, graphml_path: Path = GRAPH_FILE,
             json_path: Path = GRAPH_JSON_FILE) -> None:
        ensure_graph_dir()
        nx.write_graphml(self.g, graphml_path)
        logger.info("Wrote %s", graphml_path)

        data = nx.node_link_data(self.g)
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Wrote %s", json_path)

    @classmethod
    def load(cls, graphml_path: Path = GRAPH_FILE) -> "ComplianceGraph":
        if not graphml_path.exists():
            raise FileNotFoundError(
                f"{graphml_path} not found. Run `python main.py graph-build` first."
            )
        g = nx.read_graphml(graphml_path)
        return cls(graph=g)


# ── helpers ───────────────────────────────────────────────────
def _read_jsonl(path: Path, model_cls):
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
