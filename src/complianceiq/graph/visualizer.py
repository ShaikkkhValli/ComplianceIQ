"""Graph visualizations for the compliance knowledge graph.

Two outputs:
  1. coverage_heatmap.png  — regulatory_files × policy_files matrix
  2. domain_coverage.png   — bar chart of weighted scores by domain (from compliance_score.json)

Matplotlib is imported lazily so the rest of the package works without it.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from complianceiq.config import (
    DOMAIN_CHART_FILE,
    HEATMAP_FILE,
    SCORE_FILE,
    ensure_graph_dir,
)
from complianceiq.graph.analytics import coverage_matrix
from complianceiq.graph.builder import ComplianceGraph

logger = logging.getLogger(__name__)


def _require_matplotlib():
    try:
        import matplotlib
        matplotlib.use("Agg")  # headless
        import matplotlib.pyplot as plt
        return plt
    except ImportError:
        raise RuntimeError(
            "matplotlib is not installed. Run: pip install matplotlib  "
            "(or `uv pip install matplotlib`) to enable graph visualizations."
        )


def render_coverage_heatmap(
    graph: ComplianceGraph,
    out_path: Path = HEATMAP_FILE,
) -> Path:
    """Heatmap: regulatory files (rows) × policy files (cols), cell = #covered reqs."""
    plt = _require_matplotlib()
    ensure_graph_dir()

    matrix = coverage_matrix(graph)
    if not matrix:
        logger.warning("Coverage matrix is empty; nothing to render.")
        return out_path

    reg_files = sorted(matrix.keys())
    pol_files = sorted({p for cols in matrix.values() for p in cols.keys()})

    if not pol_files:
        logger.warning("No policy files found in coverage matrix.")
        return out_path

    data = [
        [matrix[r].get(p, 0) for p in pol_files] for r in reg_files
    ]

    fig_w = max(8, 0.45 * len(pol_files) + 6)
    fig_h = max(5, 0.4 * len(reg_files) + 2)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    im = ax.imshow(data, aspect="auto", cmap="YlGnBu")

    ax.set_xticks(range(len(pol_files)))
    ax.set_xticklabels(pol_files, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(reg_files)))
    ax.set_yticklabels(reg_files, fontsize=8)

    for i, row in enumerate(data):
        for j, val in enumerate(row):
            if val > 0:
                ax.text(j, i, str(val), ha="center", va="center",
                        fontsize=7, color="black" if val < 5 else "white")

    ax.set_title("Coverage matrix: regulations × policies (cell = matching requirements)")
    fig.colorbar(im, ax=ax, label="matching requirements")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    logger.info("Wrote %s", out_path)
    return out_path


def render_domain_coverage(
    score_file: Path = SCORE_FILE,
    out_path: Path = DOMAIN_CHART_FILE,
) -> Path:
    """Bar chart of weighted vs unweighted coverage per domain."""
    plt = _require_matplotlib()
    ensure_graph_dir()

    if not Path(score_file).exists():
        raise FileNotFoundError(
            f"{score_file} not found. Run `python main.py score` or "
            "`python main.py orchestrate` first."
        )
    with score_file.open("r", encoding="utf-8") as f:
        score = json.load(f)

    by_domain = sorted(score.get("by_domain", []), key=lambda d: d["weighted_score"])
    if not by_domain:
        logger.warning("No per-domain data in %s", score_file)
        return out_path

    domains   = [d["domain"] for d in by_domain]
    weighted  = [d["weighted_score"] for d in by_domain]
    unweighted = [d["coverage_score"] for d in by_domain]

    n = len(domains)
    fig_h = max(4, 0.4 * n + 2)
    fig, ax = plt.subplots(figsize=(10, fig_h))

    y = range(n)
    bar_h = 0.4
    ax.barh([yi - bar_h / 2 for yi in y], weighted,
            height=bar_h, color="#2b8cbe", label="severity-weighted")
    ax.barh([yi + bar_h / 2 for yi in y], unweighted,
            height=bar_h, color="#a6bddb", label="unweighted")

    ax.set_yticks(list(y))
    ax.set_yticklabels(domains)
    ax.set_xlim(0, 1)
    ax.set_xlabel("Coverage score")
    ax.set_title(
        f"Per-domain coverage   "
        f"(org-wide weighted={score.get('weighted_overall_score', 0):.2f})"
    )
    ax.axvline(0.7, color="gray", linestyle=":", linewidth=1, label="0.70 target")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    logger.info("Wrote %s", out_path)
    return out_path
