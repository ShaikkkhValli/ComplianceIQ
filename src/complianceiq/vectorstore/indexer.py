"""Read JSONL outputs from Week 2 and upsert them into ChromaDB."""

from __future__ import annotations

import logging
from pathlib import Path

from complianceiq.config import (
    CHUNKS_FILE,
    REQUIREMENTS_FILE,
)
from complianceiq.models import Chunk, Requirement
from complianceiq.vectorstore.store import ChromaStore

logger = logging.getLogger(__name__)


def _read_jsonl(path: Path, model_cls):
    if not path.exists():
        logger.warning("File not found, skipping: %s", path)
        return []
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(model_cls.model_validate_json(line))
            except Exception as e:
                logger.warning("Skipping malformed line %d in %s: %s", line_no, path, e)
    logger.info("Loaded %d records from %s", len(records), path.name)
    return records


def build_index(rebuild: bool = False, limit: int | None = None) -> dict:
    """Index chunks.jsonl and requirements.jsonl into ChromaDB.

    Args:
        rebuild: If True, drop both collections first (full re-embed).
        limit:   If set, cap the number of records ingested per collection.
    """
    store = ChromaStore.load()
    if rebuild:
        logger.info("Rebuild requested — resetting collections")
        store.reset()

    chunks       = _read_jsonl(CHUNKS_FILE, Chunk)
    requirements = _read_jsonl(REQUIREMENTS_FILE, Requirement)

    if limit is not None:
        chunks = chunks[:limit]
        requirements = requirements[:limit]
        logger.info("Limit=%d applied to both collections", limit)

    n_chunks = store.upsert_chunks(chunks)
    n_reqs   = store.upsert_requirements(requirements)

    summary = {
        "chunks_indexed": n_chunks,
        "requirements_indexed": n_reqs,
        "totals": store.counts(),
    }
    return summary


def report(summary: dict) -> None:
    print()
    print("=" * 60)
    print("WEEK 3 — INDEXING REPORT")
    print("=" * 60)
    print(f"Chunks indexed       : {summary['chunks_indexed']}")
    print(f"Requirements indexed : {summary['requirements_indexed']}")
    print(f"Collection totals    : {summary['totals']}")
