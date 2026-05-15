"""Centralized configuration loaded from environment variables and project layout."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Project paths
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

# Observability (Week 7)
AUDIT_LOG_FILE: Path    = PROCESSED_DIR / "audit_log.jsonl"
HISTORY_FILE: Path      = PROCESSED_DIR / "assessment_history.jsonl"

# Reporting (Week 8)
REPORTS_DIR: Path       = PROJECT_ROOT / "reports"
REPORT_DOCX_FILE: Path  = REPORTS_DIR / "compliance_assessment_report.docx"
REPORT_MD_FILE: Path    = REPORTS_DIR / "compliance_assessment_report.md"

# Knowledge graph (Week 6)
GRAPH_DIR: Path         = DATA_DIR / "graph"
GRAPH_FILE: Path        = GRAPH_DIR / "compliance_graph.graphml"
GRAPH_JSON_FILE: Path   = GRAPH_DIR / "compliance_graph.json"
GRAPH_METRICS_FILE: Path = GRAPH_DIR / "graph_metrics.json"
HEATMAP_FILE: Path      = GRAPH_DIR / "coverage_heatmap.png"
DOMAIN_CHART_FILE: Path = GRAPH_DIR / "domain_coverage.png"

# Vector store (Week 3)
CHROMA_DIR: Path           = DATA_DIR / "chroma"
CHUNKS_COLLECTION: str     = "chunks"
REQUIREMENTS_COLLECTION: str = "requirements"

# LLM / embedding settings
LLM_MODEL: str        = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_MODEL_HIGH: str   = os.getenv("LLM_MODEL_HIGH", "gpt-4o")
EMBEDDING_MODEL: str  = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0"))

# Resilience / cost-latency tuning
LLM_MAX_RETRIES: int      = int(os.getenv("LLM_MAX_RETRIES", "4"))
LLM_RETRY_BACKOFF: float  = float(os.getenv("LLM_RETRY_BACKOFF", "1.5"))
LLM_CACHE_SIZE: int       = int(os.getenv("LLM_CACHE_SIZE", "512"))
EMBED_CACHE_SIZE: int     = int(os.getenv("EMBED_CACHE_SIZE", "2048"))
GAP_CONCURRENCY: int      = int(os.getenv("GAP_CONCURRENCY", "8"))

# Confidence-based routing
LOW_CONFIDENCE_THRESHOLD: float = float(os.getenv("LOW_CONFIDENCE_THRESHOLD", "0.5"))
TIER_UP_ON_LOW_CONFIDENCE: bool = (
    os.getenv("TIER_UP_ON_LOW_CONFIDENCE", "true").lower() == "true"
)

# HITL gate
HITL_SCORE_THRESHOLD: float = float(os.getenv("HITL_SCORE_THRESHOLD", "0.6"))
HITL_REQUIRED_FILE: Path    = Path(os.getenv("HITL_REQUIRED_FILE", str(
    Path(__file__).resolve().parents[2] / "data" / "processed" / "hitl_required.json"
)))

# Eval framework
EVAL_DIR: Path           = PROJECT_ROOT / "tests" / "eval"
EVAL_GOLDEN_FILE: Path   = EVAL_DIR / "golden_gaps.jsonl"
EVAL_RECALL_TARGET: float = float(os.getenv("EVAL_RECALL_TARGET", "0.9"))

# Chunking
CHUNK_SIZE: int       = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP: int    = int(os.getenv("CHUNK_OVERLAP", "200"))
MIN_CHUNK_CHARS: int  = int(os.getenv("MIN_CHUNK_CHARS", "60"))

# API keys
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


def ensure_reports_dir() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def require_openai_key() -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Add it to .env before running extraction."
        )
    return OPENAI_API_KEY
