"""Centralized configuration loaded from environment variables and project layout."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Project paths ─────────────────────────────────────────────
# config.py lives at src/complianceiq/config.py; project root is three parents up.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

DATA_DIR: Path        = PROJECT_ROOT / "data"
RAW_DIR: Path         = DATA_DIR
REGULATORY_DIR: Path  = DATA_DIR / "regulatory"
POLICIES_DIR: Path    = DATA_DIR / "policies"

PROCESSED_DIR: Path     = DATA_DIR / "processed"
DOCUMENTS_FILE: Path    = PROCESSED_DIR / "documents.jsonl"
CHUNKS_FILE: Path       = PROCESSED_DIR / "chunks.jsonl"
REQUIREMENTS_FILE: Path = PROCESSED_DIR / "requirements.jsonl"
GAPS_FILE: Path         = PROCESSED_DIR / "gaps.jsonl"
COVERAGE_FILE: Path     = PROCESSED_DIR / "coverage.jsonl"
EVIDENCE_FILE: Path     = PROCESSED_DIR / "evidence.jsonl"
SCORE_FILE: Path        = PROCESSED_DIR / "compliance_score.json"
REMEDIATION_FILE: Path  = PROCESSED_DIR / "remediation_plan.jsonl"

# ── Observability (Week 7) ────────────────────────────────────
AUDIT_LOG_FILE: Path    = PROCESSED_DIR / "audit_log.jsonl"
HISTORY_FILE: Path      = PROCESSED_DIR / "assessment_history.jsonl"

# ── Knowledge graph (Week 6) ──────────────────────────────────
GRAPH_DIR: Path         = DATA_DIR / "graph"
GRAPH_FILE: Path        = GRAPH_DIR / "compliance_graph.graphml"
GRAPH_JSON_FILE: Path   = GRAPH_DIR / "compliance_graph.json"
GRAPH_METRICS_FILE: Path = GRAPH_DIR / "graph_metrics.json"
HEATMAP_FILE: Path      = GRAPH_DIR / "coverage_heatmap.png"
DOMAIN_CHART_FILE: Path = GRAPH_DIR / "domain_coverage.png"

# ── Vector store (Week 3) ─────────────────────────────────────
CHROMA_DIR: Path           = DATA_DIR / "chroma"
CHUNKS_COLLECTION: str     = "chunks"
REQUIREMENTS_COLLECTION: str = "requirements"

# ── LLM / embedding settings (from spec) ──────────────────────
LLM_MODEL: str        = os.getenv("LLM_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL: str  = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0"))

# ── Chunking ──────────────────────────────────────────────────
CHUNK_SIZE: int       = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP: int    = int(os.getenv("CHUNK_OVERLAP", "200"))
MIN_CHUNK_CHARS: int  = int(os.getenv("MIN_CHUNK_CHARS", "60"))

# ── API keys (read-only references; do not log) ───────────────
OPENAI_API_KEY: str | None    = os.getenv("OPENAI_API_KEY")
LANGFUSE_PUBLIC_KEY: str | None = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY: str | None = os.getenv("LANGFUSE_SECRET_KEY")
LANGFUSE_HOST: str            = os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")


def ensure_processed_dir() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def ensure_chroma_dir() -> None:
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)


def ensure_graph_dir() -> None:
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)


def require_openai_key() -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Add it to .env before running extraction."
        )
    return OPENAI_API_KEY
