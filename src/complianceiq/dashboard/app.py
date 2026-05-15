"""Gradio compliance dashboard.

Six tabs reading from the JSONL artifacts produced by Weeks 2-7:
  1. Overview     — org-wide score + domain breakdown + history trend
  2. Gaps         — filterable table of every Gap, with drill-down
  3. Coverage     — per-domain coverage assessments
  4. Remediation  — prioritized action list
  5. Search       — semantic search across the ChromaDB index (optional LLM cost)
  6. Reports      — generate DOCX assessment report

Launch:
    python main.py dashboard
"""

from __future__ import annotations

import logging
from typing import Any

import gradio as gr
import pandas as pd

from complianceiq.config import (
    HITL_REQUIRED_FILE,
    POLICIES_DIR,
    REGULATORY_DIR,
    REPORT_DOCX_FILE,
)
from complianceiq.reporting import (
    generate_docx_report,
    load_coverage,
    load_gaps,
    load_history,
    load_remediation,
    load_score,
)

logger = logging.getLogger(__name__)


# ── data formatters ───────────────────────────────────────────
def _gaps_dataframe(domain_filter: str = "(all)",
                    coverage_filter: str = "(all)",
                    severity_filter: str = "(all)") -> pd.DataFrame:
    gaps = load_gaps()
    rows = []
    for g in gaps:
        if domain_filter != "(all)" and g.domain.value != domain_filter:
            continue
        if coverage_filter != "(all)" and g.coverage.value != coverage_filter:
            continue
        if severity_filter != "(all)" and g.severity.value != severity_filter:
            continue
        rows.append({
            "domain":   g.domain.value,
            "severity": g.severity.value,
            "coverage": g.coverage.value,
            "priority": g.remediation_priority.value,
            "regulation": g.regulation_source,
            "mandatory_action": g.mandatory_action,
            "gap_description": g.gap_description[:200],
            "n_matches": len(g.matching_policies),
        })
    return pd.DataFrame(rows)


def _coverage_dataframe() -> pd.DataFrame:
    rows = []
    for a in load_coverage():
        rows.append({
            "domain": a.domain.value,
            "coverage_score": a.coverage_score,
            "total": a.total_requirements,
            "full": a.fully_covered,
            "partial": a.partially_covered,
            "none": a.not_covered,
            "weakest": ", ".join(a.weakest_areas[:3]),
            "strongest": ", ".join(a.strongest_areas[:3]),
            "summary": a.summary,
        })
    return pd.DataFrame(rows).sort_values("coverage_score", ascending=True)


def _remediation_dataframe(top_n: int = 100) -> pd.DataFrame:
    items = sorted(load_remediation(), key=lambda i: i.priority_score, reverse=True)[:top_n]
    rows = []
    for i, item in enumerate(items, start=1):
        rows.append({
            "rank": i,
            "priority": f"{item.priority_score:.2f}",
            "domain": item.domain.value,
            "severity": item.severity.value,
            "coverage": item.coverage.value,
            "title": item.title,
            "regulation": item.source_regulation,
        })
    return pd.DataFrame(rows)


def _history_dataframe() -> pd.DataFrame:
    snaps = load_history()
    rows = []
    for s in snaps:
        rows.append({
            "finished_at": s.finished_at,
            "run_id": s.run_id[:8],
            "overall": s.overall_score,
            "weighted": s.weighted_overall_score,
            "total_reqs": s.total_requirements,
            "open_gaps": s.partially_covered + s.not_covered,
            "high_priority": s.high_priority_gaps,
        })
    return pd.DataFrame(rows)


# ── overview tab ──────────────────────────────────────────────
def _overview_panel():
    score = load_score()
    if score is None:
        return ("No `compliance_score.json` yet. Run `python main.py orchestrate` first.",
                pd.DataFrame(), pd.DataFrame())

    headline_md = (
        f"## Org-wide weighted coverage: **{score.weighted_overall_score:.2f}**\n\n"
        f"Unweighted: {score.overall_score:.2f}  •  "
        f"Total requirements: {score.total_requirements}  •  "
        f"High-priority gaps: **{score.high_priority_gaps}**\n\n"
        f"_{score.risk_summary}_"
    )

    domain_df = pd.DataFrame([
        {
            "domain": d.domain.value,
            "weighted": d.weighted_score,
            "unweighted": d.coverage_score,
            "total": d.total_requirements,
            "open_high": d.high_severity_open,
            "open_med": d.medium_severity_open,
            "open_low": d.low_severity_open,
        }
        for d in score.by_domain
    ])

    return headline_md, domain_df, _history_dataframe()


# ── search tab ────────────────────────────────────────────────
def _do_search(query: str, collection: str, doc_type: str, top_k: int) -> pd.DataFrame:
    if not query.strip():
        return pd.DataFrame()
    from complianceiq.vectorstore.store import ChromaStore
    store = ChromaStore.load()
    where: dict[str, Any] = {}
    if doc_type != "(any)":
        where["doc_type"] = doc_type
    where_arg = where or None

    if collection == "chunks":
        hits = store.search_chunks(query, where=where_arg, top_k=top_k)
    else:
        hits = store.search_requirements(query, where=where_arg, top_k=top_k)

    rows = []
    for h in hits:
        meta = h.metadata
        loc = (
            f"page {meta.get('page_number')}" if meta.get("page_number")
            else (meta.get("section") or meta.get("page_or_section") or "")
        )
        rows.append({
            "distance": round(h.distance, 4),
            "source": meta.get("file_name") or meta.get("source_file") or "",
            "location": loc,
            "domain": meta.get("domain"),
            "doc_type": meta.get("doc_type"),
            "text": (h.text or "")[:300],
        })
    return pd.DataFrame(rows)


# ── reports tab ───────────────────────────────────────────────
def _generate_report() -> str:
    path = generate_docx_report()
    return f"Report generated: {path}"


# ── upload helpers (Upload tab) ───────────────────────────────
def _save_policy(file_obj: Any) -> str:
    if file_obj is None:
        return "No file selected."
    src = getattr(file_obj, "name", file_obj)
    from pathlib import Path
    import shutil
    src_path = Path(src)
    if src_path.suffix.lower() != ".docx":
        return "❌ Policies must be .docx files."
    POLICIES_DIR.mkdir(parents=True, exist_ok=True)
    target = POLICIES_DIR / src_path.name
    shutil.copy2(src_path, target)
    return (f"✅ Saved to `{target}`. "
            f"Run `python main.py ingest --extract && python main.py index && python main.py orchestrate` "
            f"to incorporate it.")


def _save_regulation(file_obj: Any, regulator: str) -> str:
    if file_obj is None:
        return "No file selected."
    src = getattr(file_obj, "name", file_obj)
    from pathlib import Path
    import shutil
    src_path = Path(src)
    if src_path.suffix.lower() != ".pdf":
        return "❌ Regulations must be .pdf files."
    target_dir = REGULATORY_DIR / (regulator or "other").lower()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / src_path.name
    shutil.copy2(src_path, target)
    return (f"✅ Saved to `{target}`. "
            f"Run `python main.py ingest --extract && python main.py index && python main.py orchestrate` "
            f"to incorporate it.")


def _hitl_status() -> str:
    if not HITL_REQUIRED_FILE.exists():
        return "✅ No HITL review required for the latest run."
    try:
        import json
        payload = json.loads(HITL_REQUIRED_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        return f"⚠️ HITL signal present but unreadable: {e}"
    reason = payload.get("reason", "(no reason recorded)")
    score  = payload.get("weighted_overall_score", "?")
    flagged = len(payload.get("low_confidence_gap_ids", []))
    return (
        f"### ⚠️ HITL review required\n\n"
        f"- **Reason:** {reason}\n"
        f"- **Weighted score:** {score}\n"
        f"- **Low-confidence gaps flagged:** {flagged}\n"
        f"- **Run ID:** `{payload.get('run_id', '?')}`\n"
        f"- **Signal file:** `{HITL_REQUIRED_FILE}`"
    )


# ── domain options ────────────────────────────────────────────
def _domain_choices() -> list[str]:
    score = load_score()
    if score and score.by_domain:
        return ["(all)"] + sorted({d.domain.value for d in score.by_domain})
    return ["(all)"]


# ── app ───────────────────────────────────────────────────────
def build_app() -> gr.Blocks:
    with gr.Blocks(title="ComplianceIQ Dashboard", theme=gr.themes.Soft()) as app:
        gr.Markdown("# ComplianceIQ Dashboard")
        gr.Markdown(
            "Reads JSONL artifacts produced by the orchestration pipeline. "
            "Refresh each tab to reload from disk after a new run."
        )

        # Overview
        with gr.Tab("Overview"):
            headline = gr.Markdown()
            gr.Markdown("### Per-domain coverage")
            domain_table = gr.Dataframe(label="Domains (sorted by weighted score)")
            gr.Markdown("### Assessment history")
            history_table = gr.Dataframe(label="History")
            refresh_overview = gr.Button("Refresh", variant="primary")
            refresh_overview.click(_overview_panel, outputs=[headline, domain_table, history_table])
            app.load(_overview_panel, outputs=[headline, domain_table, history_table])

        # Gaps
        with gr.Tab("Gaps"):
            gr.Markdown("Filter the gap-detection results.")
            with gr.Row():
                domain_dd   = gr.Dropdown(choices=_domain_choices(), value="(all)", label="Domain")
                coverage_dd = gr.Dropdown(
                    choices=["(all)", "fully_covered", "partially_covered", "not_covered"],
                    value="(all)", label="Coverage")
                severity_dd = gr.Dropdown(choices=["(all)", "high", "medium", "low"],
                                          value="(all)", label="Severity")
            gaps_table = gr.Dataframe(label="Gaps")
            refresh_gaps = gr.Button("Refresh / Apply filters", variant="primary")
            refresh_gaps.click(
                _gaps_dataframe,
                inputs=[domain_dd, coverage_dd, severity_dd],
                outputs=gaps_table,
            )
            app.load(_gaps_dataframe,
                     inputs=[domain_dd, coverage_dd, severity_dd],
                     outputs=gaps_table)

        # Coverage
        with gr.Tab("Coverage"):
            gr.Markdown("Per-domain coverage assessments produced by the Policy Analyzer.")
        # Coverage
        with gr.Tab("Coverage"):
            gr.Markdown("Per-domain coverage assessments produced by the Policy Analyzer.")
            cov_table = gr.Dataframe(label="Coverage by domain")
            refresh_cov = gr.Button("Refresh", variant="primary")
            refresh_cov.click(_coverage_dataframe, outputs=cov_table)
            app.load(_coverage_dataframe, outputs=cov_table)

        # Remediation
        with gr.Tab("Remediation"):
            gr.Markdown("Prioritized list of remediation items (top 100 by priority score).")
            rem_table = gr.Dataframe(label="Remediation plan")
            refresh_rem = gr.Button("Refresh", variant="primary")
            refresh_rem.click(_remediation_dataframe, outputs=rem_table)
            app.load(_remediation_dataframe, outputs=rem_table)

        # Search
        with gr.Tab("Search"):
            gr.Markdown(
                "Semantic search against ChromaDB. **Note**: triggers an OpenAI "
                "embedding call per query.")
            with gr.Row():
                query_in = gr.Textbox(label="Query",
                                      placeholder="e.g. 'incident reporting within 24 hours'",
                                      scale=4)
                top_k_in = gr.Slider(1, 20, value=5, step=1, label="Top-K", scale=1)
            with gr.Row():
                collection_in = gr.Dropdown(["chunks", "requirements"],
                                            value="chunks", label="Collection")
                doc_type_in   = gr.Dropdown(["(any)", "regulatory", "policy"],
                                            value="(any)", label="Doc type")
            search_btn = gr.Button("Search", variant="primary")
            search_table = gr.Dataframe(label="Results")
            search_btn.click(_do_search,
                             inputs=[query_in, collection_in, doc_type_in, top_k_in],
                             outputs=search_table)

        # Reports
        with gr.Tab("Reports"):
            gr.Markdown("Generate the audit-ready DOCX assessment report.")
            gen_btn = gr.Button("Generate DOCX report", variant="primary")
            status = gr.Markdown()
            gen_btn.click(_generate_report, outputs=status)
            gr.Markdown(f"Report path: `{REPORT_DOCX_FILE}`")

        # Upload — file upload + HITL queue (rubric §13)
        with gr.Tab("Upload"):
            gr.Markdown(
                "## Add a new policy or regulation\n"
                "Drop a file below to add it to the corpus. "
                "Policies become `data/policies/<filename>.docx`; "
                "regulations become `data/regulatory/<regulator>/<filename>.pdf`. "
                "Run the orchestration afterwards (Reports tab → Generate, or "
                "`python main.py orchestrate`) to incorporate the new document."
            )
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### Policy (.docx)")
                    pol_file = gr.File(label="Upload policy DOCX", file_types=[".docx"])
                    pol_btn  = gr.Button("Save policy", variant="primary")
                    pol_status = gr.Markdown()
                    pol_btn.click(_save_policy, inputs=pol_file, outputs=pol_status)
                with gr.Column():
                    gr.Markdown("### Regulation (.pdf)")
                    reg_file = gr.File(label="Upload regulatory PDF", file_types=[".pdf"])
                    regulator_dd = gr.Dropdown(
                        choices=["irdai", "mas", "rbi", "sebi", "fca", "sec", "other"],
                        value="irdai", label="Regulator",
                    )
                    reg_btn  = gr.Button("Save regulation", variant="primary")
                    reg_status = gr.Markdown()
                    reg_btn.click(_save_regulation,
                                  inputs=[reg_file, regulator_dd], outputs=reg_status)
            gr.Markdown("---")
            gr.Markdown("### HITL queue")
            hitl_view = gr.Markdown()
            refresh_hitl = gr.Button("Refresh HITL status")
            refresh_hitl.click(_hitl_status, outputs=hitl_view)
            app.load(_hitl_status, outputs=hitl_view)

    return app


def launch(server_port: int = 7860, share: bool = False) -> None:
    app = build_app()
    print(f"\nLaunching ComplianceIQ dashboard on http://127.0.0.1:{server_port}\n")
    app.launch(server_port=server_port, share=share, inbrowser=True)
