"""ChromaDB wrapper with two collections: chunks and requirements.

Persistent client at config.CHROMA_DIR. Collections are created on first use
with the OpenAI embedding function from embeddings.py.

Public API:
    ChromaStore.load()                          -> ChromaStore
    store.upsert_chunks(chunks)
    store.upsert_requirements(requirements)
    store.search_chunks(query, where, top_k)    -> list[SearchHit]
    store.search_requirements(query, where, top_k) -> list[SearchHit]
    store.counts()                              -> dict
    store.reset()                               -> None
"""

from __future__ import annotations

import hashlib
import logging
from enum import Enum
from typing import Iterable

import chromadb
from chromadb.config import Settings
from pydantic import BaseModel

from complianceiq.config import (
    CHROMA_DIR,
    CHUNKS_COLLECTION,
    REQUIREMENTS_COLLECTION,
    ensure_chroma_dir,
)
from complianceiq.models import Chunk, Requirement
from complianceiq.vectorstore.embeddings import get_embedding_function

logger = logging.getLogger(__name__)


# ── Result type ───────────────────────────────────────────────
class SearchHit(BaseModel):
    """One result from a vector search. Lower distance = closer match."""
    id: str
    text: str
    metadata: dict
    distance: float


# ── Helpers ───────────────────────────────────────────────────
def _clean_metadata(meta: dict) -> dict:
    """Chroma rejects None values and complex objects in metadata."""
    cleaned: dict = {}
    for k, v in meta.items():
        if v is None:
            continue
        if isinstance(v, Enum):
            v = v.value
        if isinstance(v, (str, int, float, bool)):
            cleaned[k] = v
        else:
            cleaned[k] = str(v)
    return cleaned


def _chunk_id(chunk: Chunk) -> str:
    """Deterministic, content-derived ID.

    Hash covers the FULL chunk text plus block_type and section so that:
    - text + table blocks on the same page get distinct IDs
    - genuinely identical paragraphs collapse to one ID (correct dedup)
    """
    m = chunk.metadata
    where = f"p{m.page_number}" if m.page_number is not None else (m.section or "root")
    safe_where = where.replace(" ", "_").replace("/", "_")[:80]
    payload = f"{m.block_type}|{m.section or ''}|{chunk.text}"
    suffix = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"{m.file_name}::{safe_where}::{suffix}"


def _chunk_metadata(chunk: Chunk) -> dict:
    m = chunk.metadata
    return _clean_metadata({
        "file_name": m.file_name,
        "source": m.source,
        "doc_type": m.doc_type,
        "domain": m.domain,
        "page_number": m.page_number,
        "section": m.section,
        "block_type": m.block_type,
        "chunk_index": m.chunk_index,
        "total_chunks": m.total_chunks,
    })


def _requirement_metadata(req: Requirement) -> dict:
    return _clean_metadata({
        "source_file": req.source_file,
        "page_or_section": req.page_or_section,
        "doc_type": req.doc_type,
        "domain": req.domain,
        "severity": req.severity,
        "extracted_by": req.extracted_by,
        # Truncated for filterability without bloating metadata.
        "mandatory_action": req.mandatory_action[:300],
    })


def _requirement_text_for_embedding(req: Requirement) -> str:
    """Concatenate the clause and the LLM's interpretation for richer embedding."""
    return f"{req.requirement_text}\n\n{req.mandatory_action}"


# ── Store ─────────────────────────────────────────────────────
class ChromaStore:
    """Two-collection wrapper around a persistent ChromaDB client."""

    def __init__(self) -> None:
        ensure_chroma_dir()
        self.client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        self.embed_fn = get_embedding_function()

        self.chunks = self.client.get_or_create_collection(
            name=CHUNKS_COLLECTION,
            embedding_function=self.embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
        self.requirements = self.client.get_or_create_collection(
            name=REQUIREMENTS_COLLECTION,
            embedding_function=self.embed_fn,
            metadata={"hnsw:space": "cosine"},
        )

    # ── factory ───────────────────────────────────────────────
    @classmethod
    def load(cls) -> "ChromaStore":
        return cls()

    # ── upserts ───────────────────────────────────────────────
    def upsert_chunks(self, chunks: Iterable[Chunk]) -> int:
        chunks = list(chunks)
        if not chunks:
            return 0

        # Defensive dedup: identical-content chunks share an ID by design;
        # Chroma rejects duplicate IDs in a single upsert call.
        unique: dict[str, Chunk] = {}
        for c in chunks:
            unique[_chunk_id(c)] = c
        dropped = len(chunks) - len(unique)
        if dropped:
            logger.info("Deduplicated %d chunks with identical content", dropped)

        ids       = list(unique.keys())
        documents = [c.text for c in unique.values()]
        metadatas = [_chunk_metadata(c) for c in unique.values()]
        self.chunks.upsert(ids=ids, documents=documents, metadatas=metadatas)
        logger.info("Upserted %d chunks", len(ids))
        return len(ids)

    def upsert_requirements(self, requirements: Iterable[Requirement]) -> int:
        reqs = list(requirements)
        if not reqs:
            return 0

        # Same defensive dedup for requirement_id collisions (rare but possible).
        unique: dict[str, Requirement] = {}
        for r in reqs:
            unique[r.requirement_id] = r
        dropped = len(reqs) - len(unique)
        if dropped:
            logger.info("Deduplicated %d requirements with identical IDs", dropped)

        ids       = list(unique.keys())
        documents = [_requirement_text_for_embedding(r) for r in unique.values()]
        metadatas = [_requirement_metadata(r) for r in unique.values()]
        self.requirements.upsert(ids=ids, documents=documents, metadatas=metadatas)
        logger.info("Upserted %d requirements", len(ids))
        return len(ids)

    # ── searches ──────────────────────────────────────────────
    def search_chunks(
        self,
        query: str,
        where: dict | None = None,
        top_k: int = 5,
    ) -> list[SearchHit]:
        return self._search(self.chunks, query, where, top_k)

    def search_requirements(
        self,
        query: str,
        where: dict | None = None,
        top_k: int = 5,
    ) -> list[SearchHit]:
        return self._search(self.requirements, query, where, top_k)

    @staticmethod
    def _search(collection, query: str, where, top_k: int) -> list[SearchHit]:
        kwargs = {"query_texts": [query], "n_results": top_k}
        if where:
            kwargs["where"] = where
        result = collection.query(**kwargs)

        ids       = result.get("ids", [[]])[0]
        docs      = result.get("documents", [[]])[0]
        metas     = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        hits: list[SearchHit] = []
        for i, doc, meta, dist in zip(ids, docs, metas, distances):
            hits.append(SearchHit(
                id=i,
                text=doc or "",
                metadata=meta or {},
                distance=float(dist) if dist is not None else 0.0,
            ))
        return hits

    # ── admin ─────────────────────────────────────────────────
    def counts(self) -> dict:
        return {
            CHUNKS_COLLECTION: self.chunks.count(),
            REQUIREMENTS_COLLECTION: self.requirements.count(),
        }

    def reset(self) -> None:
        """Drop and recreate both collections. Use with --rebuild."""
        for name in (CHUNKS_COLLECTION, REQUIREMENTS_COLLECTION):
            try:
                self.client.delete_collection(name)
                logger.info("Dropped collection: %s", name)
            except Exception as e:
                logger.debug("Could not drop %s: %s", name, e)
        # Recreate
        self.chunks = self.client.get_or_create_collection(
            name=CHUNKS_COLLECTION,
            embedding_function=self.embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
        self.requirements = self.client.get_or_create_collection(
            name=REQUIREMENTS_COLLECTION,
            embedding_function=self.embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
