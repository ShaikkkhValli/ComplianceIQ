"""Graph queries and metrics over the ComplianceGraph."""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx

from complianceiq.config import GRAPH_METRICS_FILE, ensure_graph_dir
from complianceiq.graph.builder import ComplianceGraph

logger = logging.getLogger(__name__)


# ── node-type filters ─────────────────────────────────────────
def _nodes_of_type(g: nx.DiGraph, type_name: str) -> list[str]:
    return [n for n, d in g.nodes(data=True) if d.get("type") == type_name]


# ── orphan + coverage queries ─────────────────────────────────
def orphan_requirements(graph: ComplianceGraph) -> list[dict]:
    """Requirements with zero policy coverage edges."""
    g = graph.g
    out = []
    for rn in _nodes_of_type(g, "requirement"):
        # Out-edges of relation 'covered_by' are policy matches.
        covered = any(
            data.get("relation") == "covered_by"
            for _, _, data in g.out_edges(rn, data=True)
        )
        if not covered:
            data = g.nodes[rn]
            out.append({
                "requirement_id": rn.replace("req:", ""),
                "domain": data.get("domain"),
                "severity": data.get("severity"),
                "source_file": data.get("source_file"),
                "mandatory_action": data.get("mandatory_action"),
            })
    return out


def top_cited_policies(graph: ComplianceGraph, top_n: int = 10) -> list[dict]:
    """Policy files most-frequently cited as covering some requirement."""
    g = graph.g
    citations: Counter = Counter()
    for cn in _nodes_of_type(g, "policy_chunk"):
        # Each chunk -> in_file -> policy_file
        # And requirements -> covered_by -> chunk (incoming)
        in_count = sum(
            1 for _, _, data in g.in_edges(cn, data=True)
            if data.get("relation") == "covered_by"
        )
        if in_count == 0:
            continue
        # Find the file the chunk belongs to
        for _, target, data in g.out_edges(cn, data=True):
            if data.get("relation") == "in_file":
                citations[target] += in_count

    ranked = citations.most_common(top_n)
    return [
        {
            "policy_file": pfn.replace("pol_file:", ""),
            "citations": count,
        }
        for pfn, count in ranked
    ]


def coverage_matrix(graph: ComplianceGraph) -> dict:
    """Return a {regulatory_file: {policy_file: count}} matrix.

    Counts how many requirements from each regulatory file are matched by
    chunks belonging to each policy file.
    """
    g = graph.g
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for rn in _nodes_of_type(g, "requirement"):
        reg_file = None
        for _, target, data in g.out_edges(rn, data=True):
            if data.get("relation") == "from_file":
                reg_file = target.replace("reg_file:", "")
                break
        if not reg_file:
            continue

        # Each chunk this requirement covers
        for _, chunk, data in g.out_edges(rn, data=True):
            if data.get("relation") != "covered_by":
                continue
            for _, target, edata in g.out_edges(chunk, data=True):
                if edata.get("relation") == "in_file":
                    pol_file = target.replace("pol_file:", "")
                    matrix[reg_file][pol_file] += 1

    return {k: dict(v) for k, v in matrix.items()}


def domain_subgraph(graph: ComplianceGraph, domain: str) -> nx.DiGraph:
    """Subgraph containing only nodes whose domain attribute matches."""
    g = graph.g
    nodes = {
        n for n, d in g.nodes(data=True)
        if d.get("domain") == domain or d.get("name") == domain
    }
    # Include policy chunks reachable from in-domain requirements.
    for rn in list(nodes):
        for _, target, data in g.out_edges(rn, data=True):
            if data.get("relation") == "covered_by":
                nodes.add(target)
                # And the policy_file it lives in
                for _, pfn, edata in g.out_edges(target, data=True):
                    if edata.get("relation") == "in_file":
                        nodes.add(pfn)
    return g.subgraph(nodes).copy()


# ── overall metrics ───────────────────────────────────────────
def compute_metrics(graph: ComplianceGraph) -> dict:
    g = graph.g
    type_counts = Counter(d.get("type") for _, d in g.nodes(data=True))
    coverage_counts: Counter = Counter()
    for rn in _nodes_of_type(g, "requirement"):
        coverage_counts[g.nodes[rn].get("coverage", "unknown")] += 1

    orphans = orphan_requirements(graph)
    top_policies = top_cited_policies(graph, top_n=10)

    return {
        "total_nodes": g.number_of_nodes(),
        "total_edges": g.number_of_edges(),
        "node_types": dict(type_counts),
        "requirement_coverage": dict(coverage_counts),
        "orphan_requirement_count": len(orphans),
        "top_cited_policies": top_policies,
    }


def save_metrics(metrics: dict, path: Path = GRAPH_METRICS_FILE) -> None:
    ensure_graph_dir()
    with path.open("w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    logger.info("Wrote %s", path)


# ── pretty-print ──────────────────────────────────────────────
def print_metrics(graph: ComplianceGraph, metrics: dict) -> None:
    print()
    print("=" * 60)
    print("WEEK 6 — COMPLIANCE KNOWLEDGE GRAPH")
    print("=" * 60)
    print(f"Total nodes : {metrics['total_nodes']}")
    print(f"Total edges : {metrics['total_edges']}")
    print(f"Node types  : {metrics['node_types']}")
    print(f"Coverage    : {metrics['requirement_coverage']}")
    print(f"Orphan reqs : {metrics['orphan_requirement_count']}")
    print()
    if metrics["top_cited_policies"]:
        print("Top-cited policy files:")
        for p in metrics["top_cited_policies"]:
            print(f"  {p['policy_file']:<60} {p['citations']:>3} citations")

    orphans = orphan_requirements(graph)
    if orphans:
        print(f"\nFirst 5 orphan requirements (no policy coverage at all):")
        for o in orphans[:5]:
            print(f"  [{o['domain']}/{o['severity']}] {o['source_file']}")
            print(f"    {o['mandatory_action']}")
