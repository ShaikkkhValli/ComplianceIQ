"""Week 2 ingestion pipeline.

Stages:
  1. Load regulatory PDFs and policy DOCX into Documents.
  2. Categorize each by compliance domain (already attached during loading).
  3. Chunk Documents into embedding-ready Chunks.
  4. Persist Documents and Chunks as JSONL.
  5. (Optional) Run LLM extractor to produce structured Requirements.

Run via:
    python main.py ingest                    # parse + chunk only
    python main.py ingest --extract          # parse + chunk + LLM extraction (full)
    python main.py ingest --extract --limit 20   # cap LLM calls for dev runs
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Iterable

from complianceiq.config import (
    CHUNKS_FILE,
    DOCUMENTS_FILE,
    POLICIES_DIR,
    PROJECT_ROOT,
    REGULATORY_DIR,
    REQUIREMENTS_FILE,
    ensure_processed_dir,
)
from complianceiq.ingestion.chunker import chunk_documents
from complianceiq.ingestion.docx_loader import DOCXLoader
from complianceiq.ingestion.domain_inference import infer_domain
from complianceiq.ingestion.extractor import RequirementExtractor
from complianceiq.ingestion.pdf_loader import PDFLoader
from complianceiq.models import Chunk, Document, Requirement

logger = logging.getLogger(__name__)


# ── persistence ───────────────────────────────────────────────
def _write_jsonl(path: Path, records: Iterable) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            payload = r.model_dump(mode="json") if hasattr(r, "model_dump") else r
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    logger.info("Wrote %s", path)


def _read_chunks_jsonl(path: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            chunks.append(Chunk.model_validate_json(line))
    return chunks


# ── reporting ─────────────────────────────────────────────────
def _validate_and_report(documents: list[Document], chunks: list[Chunk]) -> None:
    print()
    print("=" * 60)
    print("WEEK 2 — INGESTION VALIDATION REPORT")
    print("=" * 60)

    if not documents:
        print("No documents loaded. Check data/ folder paths.")
        return

    by_doctype = Counter(d.metadata.doc_type for d in documents)
    by_domain  = Counter(d.metadata.domain.value for d in documents)
    by_block   = Counter(d.metadata.block_type for d in documents)
    by_file    = Counter(d.metadata.file_name for d in documents)

    print(f"Documents loaded   : {len(documents)}")
    print(f"  regulatory       : {by_doctype.get('regulatory', 0)}")
    print(f"  policy           : {by_doctype.get('policy', 0)}")
    print(f"  source files     : {len(by_file)}")
    print(f"Block types        : {dict(by_block)}")
    print(f"Domains            : {dict(by_domain)}")

    if chunks:
        lengths = [len(c.text) for c in chunks]
        print(f"\nChunks total       : {len(chunks)}")
        print(f"  avg length       : {sum(lengths) // len(lengths)} chars")
        print(f"  min / max        : {min(lengths)} / {max(lengths)} chars")

    print("\nFiles processed:")
    for name, count in sorted(by_file.items()):
        print(f"  {name:<60} {count:>4} blocks")


# ── main entry ────────────────────────────────────────────────
def run_ingestion(extract: bool = False, limit: int | None = None) -> dict:
    """Run the Week 2 pipeline. Returns a summary dict.

    Args:
        extract: If True, runs the LLM extractor on all chunks.
        limit:   If set, caps the number of chunks sent to the LLM.
    """
    ensure_processed_dir()

    print("=" * 60)
    print("STEP 1 & 2: Loading & categorizing documents")
    print("=" * 60)
    print(f"PROJECT_ROOT   : {PROJECT_ROOT}")
    print(f"REGULATORY_DIR : {REGULATORY_DIR}")
    print(f"POLICIES_DIR   : {POLICIES_DIR}")

    pdf_loader  = PDFLoader(infer_domain)
    docx_loader = DOCXLoader(infer_domain)

    regulatory_docs = pdf_loader.load_all_pdfs(REGULATORY_DIR)
    policy_docs     = docx_loader.load_all_docx(POLICIES_DIR)
    documents       = regulatory_docs + policy_docs

    if not documents:
        raise RuntimeError(
            "No documents loaded. Check that data/regulatory/ and data/policies/ exist "
            "and contain .pdf / .docx files."
        )

    if pdf_loader.scanned_files:
        print("\nWARNING — PDFs with no extractable text (likely scanned):")
        for f in pdf_loader.scanned_files:
            print(f"  {f}")

    if pdf_loader.failed_files or docx_loader.failed_files:
        print("\nWARNING — files that failed to load:")
        for f, err in pdf_loader.failed_files + docx_loader.failed_files:
            print(f"  {f}: {err}")

    print()
    print("=" * 60)
    print("STEP 3: Chunking documents")
    print("=" * 60)
    chunks = chunk_documents(documents)

    print()
    print("=" * 60)
    print("STEP 4: Persisting")
    print("=" * 60)
    _write_jsonl(DOCUMENTS_FILE, documents)
    _write_jsonl(CHUNKS_FILE, chunks)

    _validate_and_report(documents, chunks)

    summary: dict = {
        "documents": len(documents),
        "chunks": len(chunks),
        "scanned_pdfs": len(pdf_loader.scanned_files),
        "failed_files": len(pdf_loader.failed_files) + len(docx_loader.failed_files),
        "documents_file": str(DOCUMENTS_FILE),
        "chunks_file": str(CHUNKS_FILE),
    }

    if extract:
        print()
        print("=" * 60)
        print("STEP 5: Extracting structured requirements (LLM)")
        print("=" * 60)
        extractor = RequirementExtractor()
        requirements = extractor.extract_from_chunks(chunks, limit=limit)
        _write_jsonl(REQUIREMENTS_FILE, requirements)

        by_severity = Counter(r.severity.value for r in requirements)
        by_domain   = Counter(r.domain.value for r in requirements)
        print(f"\nRequirements extracted : {len(requirements)}")
        print(f"  by severity          : {dict(by_severity)}")
        print(f"  by domain            : {dict(by_domain)}")
        print(f"  saved to             : {REQUIREMENTS_FILE}")

        summary.update({
            "requirements": len(requirements),
            "requirements_file": str(REQUIREMENTS_FILE),
        })

    print("\nWeek 2 ingestion — COMPLETE")
    return summary


def extract_only(limit: int | None = None) -> dict:
    """Run extraction against an existing chunks.jsonl (no re-parsing)."""
    if not CHUNKS_FILE.exists():
        raise FileNotFoundError(
            f"{CHUNKS_FILE} not found. Run `python main.py ingest` first."
        )
    chunks = _read_chunks_jsonl(CHUNKS_FILE)
    print(f"Loaded {len(chunks)} chunks from {CHUNKS_FILE}")

    extractor = RequirementExtractor()
    requirements = extractor.extract_from_chunks(chunks, limit=limit)
    _write_jsonl(REQUIREMENTS_FILE, requirements)
    return {
        "chunks": len(chunks),
        "requirements": len(requirements),
        "requirements_file": str(REQUIREMENTS_FILE),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run_ingestion()
