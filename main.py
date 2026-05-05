"""ComplianceIQ CLI entry point.

Usage:
    # Week 2
    python main.py ingest
    python main.py ingest --extract
    python main.py ingest --extract --limit 20
    python main.py extract
    python main.py extract --limit 20

    # Week 3
    python main.py index                          # upsert chunks + requirements into ChromaDB
    python main.py index --rebuild                # drop collections first (full re-embed)
    python main.py search "MFA for privileged accounts"
    python main.py search "cyber incident reporting" --collection requirements --top-k 5
    python main.py search "audit committee" --doc-type policy

    # Week 4 — Single-agent analysis
    python main.py analyze-regulation                                # summarize every regulatory file
    python main.py analyze-regulation --file "fraud-risk-framework"  # summarize one
    python main.py analyze-gaps --limit 20                           # detect gaps (LLM cost-controlled)
    python main.py analyze-gaps --domain information_security        # filter to one domain
    python main.py analyze-coverage                                  # roll up gaps into per-domain scores

    # Week 5 — Multi-agent orchestration
    python main.py orchestrate                                       # run the full pipeline end-to-end
    python main.py orchestrate --domain information_security --limit 30
    python main.py orchestrate --skip-summaries                      # skip Regulation Monitor step
    python main.py score                                             # recompute score from gaps.jsonl
    python main.py remediate                                         # build remediation plan

    # Week 6 — Knowledge graph
    python main.py graph-build                                       # build graph from gaps + requirements
    python main.py graph-stats                                       # node/edge counts, top-cited policies, orphans
    python main.py graph-visualize                                   # heatmap + per-domain coverage chart

    # Week 7 — Observability
    python main.py history                                           # last assessment snapshots
    python main.py history --compare                                 # delta vs previous run
    python main.py audit-log --tail 50                               # tail of compliance audit log
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Silence chromadb 0.4.x posthog telemetry noise (incompatible with newer posthog).
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

# Make the src/ layout importable without requiring `pip install -e .`
_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="complianceiq")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Run the Week 2 ingestion pipeline.")
    p_ingest.add_argument("--extract", action="store_true",
                          help="Also run the LLM requirement extractor.")
    p_ingest.add_argument("--limit", type=int, default=None,
                          help="Cap the number of chunks sent to the LLM.")

    p_extract = sub.add_parser("extract",
                               help="Extract requirements from existing chunks.jsonl.")
    p_extract.add_argument("--limit", type=int, default=None,
                           help="Cap the number of chunks sent to the LLM.")

    # Week 3 — index + search
    p_index = sub.add_parser("index",
                             help="Index chunks.jsonl and requirements.jsonl into ChromaDB.")
    p_index.add_argument("--rebuild", action="store_true",
                         help="Drop both collections before indexing (full re-embed).")
    p_index.add_argument("--limit", type=int, default=None,
                         help="Cap records indexed per collection (for cost-controlled dev runs).")

    p_search = sub.add_parser("search",
                              help="Run a semantic search against ChromaDB.")
    p_search.add_argument("query", help="Free-text query.")
    p_search.add_argument("--collection", choices=["chunks", "requirements"],
                          default="chunks",
                          help="Which collection to search (default: chunks).")
    p_search.add_argument("--doc-type", choices=["regulatory", "policy"],
                          default=None,
                          help="Filter by doc_type.")
    p_search.add_argument("--domain", default=None,
                          help="Filter by domain (e.g. information_security).")
    p_search.add_argument("--top-k", type=int, default=5,
                          help="Number of results to return.")

    # Week 4 — agents
    p_reg = sub.add_parser("analyze-regulation",
                           help="Summarize regulatory documents (Regulation Monitor Agent).")
    p_reg.add_argument("--file", default=None,
                       help="Filter to source files whose name contains this substring.")
    p_reg.add_argument("--domain", default=None,
                       help="Filter by domain (e.g. information_security).")

    p_gaps = sub.add_parser("analyze-gaps",
                            help="Find compliance gaps (Gap Detector Agent).")
    p_gaps.add_argument("--domain", default=None,
                        help="Filter regulations by domain.")
    p_gaps.add_argument("--limit", type=int, default=None,
                        help="Cap the number of regulations analyzed (cost control).")
    p_gaps.add_argument("--top-k", type=int, default=5,
                        help="Number of policy excerpts retrieved per regulation.")

    p_cov = sub.add_parser("analyze-coverage",
                           help="Roll gaps.jsonl into per-domain coverage (Policy Analyzer Agent).")
    p_cov.add_argument("--domain", default=None,
                       help="Filter to a single domain.")

    # Week 5 — orchestration
    p_orch = sub.add_parser("orchestrate",
                            help="Run the full multi-agent compliance workflow end-to-end.")
    p_orch.add_argument("--domain", default=None,
                        help="Filter regulations by domain.")
    p_orch.add_argument("--limit", type=int, default=None,
                        help="Cap the number of regulations analyzed.")
    p_orch.add_argument("--top-k", type=int, default=5,
                        help="Top-K policy excerpts retrieved per regulation.")
    p_orch.add_argument("--skip-summaries", action="store_true",
                        help="Skip the Regulation Monitor digest step.")

    p_score = sub.add_parser("score",
                             help="Compute compliance score from gaps.jsonl (no LLM).")

    p_rem = sub.add_parser("remediate",
                           help="Build remediation plan from gaps.jsonl (no LLM).")
    p_rem.add_argument("--top", type=int, default=20,
                       help="How many top remediation items to print (file always full).")

    # Week 6 — knowledge graph
    sub.add_parser("graph-build",
                   help="Build the regulation-policy knowledge graph from gaps + requirements.")
    sub.add_parser("graph-stats",
                   help="Print graph metrics (node counts, top-cited policies, orphans).")
    p_gv = sub.add_parser("graph-visualize",
                          help="Render coverage heatmap and per-domain coverage chart (PNG).")
    p_gv.add_argument("--no-heatmap", action="store_true",
                      help="Skip the coverage heatmap.")
    p_gv.add_argument("--no-chart", action="store_true",
                      help="Skip the per-domain coverage bar chart.")

    # Week 7 — observability
    p_hist = sub.add_parser("history",
                            help="Show recent compliance assessment snapshots.")
    p_hist.add_argument("-n", type=int, default=10,
                        help="How many recent snapshots to show.")
    p_hist.add_argument("--compare", action="store_true",
                        help="Print delta between the two most recent runs.")

    p_log = sub.add_parser("audit-log",
                           help="Show recent entries from the compliance audit log.")
    p_log.add_argument("--tail", type=int, default=30,
                       help="How many recent events to show.")

    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable DEBUG-level logging.")
    return parser


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.command == "ingest":
        from complianceiq.ingestion.pipeline import run_ingestion
        run_ingestion(extract=args.extract, limit=args.limit)
    elif args.command == "extract":
        from complianceiq.ingestion.pipeline import extract_only
        extract_only(limit=args.limit)
    elif args.command == "index":
        from complianceiq.vectorstore.indexer import build_index, report
        summary = build_index(rebuild=args.rebuild, limit=args.limit)
        report(summary)
    elif args.command == "search":
        _run_search(
            query=args.query,
            collection=args.collection,
            doc_type=args.doc_type,
            domain=args.domain,
            top_k=args.top_k,
        )
    elif args.command == "analyze-regulation":
        from complianceiq.agents import run_regulation_summary
        from complianceiq.models import Domain
        run_regulation_summary(
            file_filter=args.file,
            domain=Domain(args.domain) if args.domain else None,
        )
    elif args.command == "analyze-gaps":
        from complianceiq.agents import run_gap_detection
        from complianceiq.models import Domain
        run_gap_detection(
            domain=Domain(args.domain) if args.domain else None,
            limit=args.limit,
            top_k=args.top_k,
        )
    elif args.command == "analyze-coverage":
        from complianceiq.agents import run_coverage_analysis
        from complianceiq.models import Domain
        run_coverage_analysis(
            domain_filter=Domain(args.domain) if args.domain else None,
        )
    elif args.command == "orchestrate":
        from complianceiq.orchestration import run_workflow
        from complianceiq.models import Domain
        run_workflow(
            domain=Domain(args.domain) if args.domain else None,
            limit=args.limit,
            skip_summaries=args.skip_summaries,
            gap_top_k=args.top_k,
        )
    elif args.command == "score":
        from complianceiq.orchestration import run_score_only
        run_score_only()
    elif args.command == "remediate":
        from complianceiq.orchestration import run_remediation_only
        run_remediation_only(top_n=args.top)
    elif args.command == "graph-build":
        from complianceiq.graph import (
            ComplianceGraph, compute_metrics, print_metrics, save_metrics,
        )
        graph = ComplianceGraph.build_from_artifacts()
        graph.save()
        metrics = compute_metrics(graph)
        save_metrics(metrics)
        print_metrics(graph, metrics)
    elif args.command == "graph-stats":
        from complianceiq.graph import (
            ComplianceGraph, compute_metrics, print_metrics,
        )
        graph = ComplianceGraph.load()
        metrics = compute_metrics(graph)
        print_metrics(graph, metrics)
    elif args.command == "graph-visualize":
        from complianceiq.graph import (
            ComplianceGraph, render_coverage_heatmap, render_domain_coverage,
        )
        graph = ComplianceGraph.load()
        if not args.no_heatmap:
            path = render_coverage_heatmap(graph)
            print(f"Heatmap saved to: {path}")
        if not args.no_chart:
            path = render_domain_coverage()
            print(f"Domain chart saved to: {path}")
    elif args.command == "history":
        from complianceiq.observability import print_history
        print_history(n=args.n, compare=args.compare)
    elif args.command == "audit-log":
        from complianceiq.observability import print_audit_log
        print_audit_log(tail=args.tail)
    else:
        parser.print_help()
        return 2

    return 0


def _run_search(query: str, collection: str, doc_type, domain, top_k: int) -> None:
    """Pretty-print top-k search results from the chosen collection."""
    from complianceiq.vectorstore.store import ChromaStore

    store = ChromaStore.load()

    where: dict = {}
    if doc_type:
        where["doc_type"] = doc_type
    if domain:
        where["domain"] = domain
    where_arg = where or None

    if collection == "chunks":
        hits = store.search_chunks(query, where=where_arg, top_k=top_k)
    else:
        hits = store.search_requirements(query, where=where_arg, top_k=top_k)

    if not hits:
        print("No results.")
        return

    print(f"\nTop {len(hits)} results from '{collection}' for: {query!r}")
    if where_arg:
        print(f"Filters: {where_arg}")
    print("=" * 70)
    for i, hit in enumerate(hits, start=1):
        meta = hit.metadata
        loc = (
            f"page {meta.get('page_number')}" if meta.get("page_number")
            else meta.get("section") or meta.get("page_or_section") or ""
        )
        head = meta.get("file_name") or meta.get("source_file") or hit.id
        snippet = (hit.text or "").replace("\n", " ").strip()
        if len(snippet) > 220:
            snippet = snippet[:220] + "..."
        print(f"\n{i}. [distance={hit.distance:.4f}] {head}  {loc}")
        print(f"   domain={meta.get('domain')}  doc_type={meta.get('doc_type')}")
        if "severity" in meta:
            print(f"   severity={meta.get('severity')}")
        print(f"   {snippet}")


if __name__ == "__main__":
    sys.exit(main())
