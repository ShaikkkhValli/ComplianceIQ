"""Token-aware chunking with metadata propagation."""

from __future__ import annotations

import logging
from typing import Iterable

try:
    # langchain >= 0.2 split text splitters into a separate package
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:  # pragma: no cover — fallback for older langchain
    from langchain.text_splitter import RecursiveCharacterTextSplitter

from complianceiq.config import CHUNK_OVERLAP, CHUNK_SIZE, MIN_CHUNK_CHARS
from complianceiq.models import Chunk, ChunkMetadata, Document

logger = logging.getLogger(__name__)


def _build_splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )


def chunk_documents(documents: Iterable[Document]) -> list[Chunk]:
    """Split each Document into one or more Chunks, dropping empties and shorts."""
    splitter = _build_splitter()
    chunks: list[Chunk] = []

    for doc in documents:
        pieces = [p.strip() for p in splitter.split_text(doc.text) if p and p.strip()]
        pieces = [p for p in pieces if len(p) >= MIN_CHUNK_CHARS]

        total = len(pieces)
        for i, piece in enumerate(pieces):
            chunk_meta = ChunkMetadata(
                **doc.metadata.model_dump(),
                chunk_index=i,
                total_chunks=total,
            )
            chunks.append(Chunk(text=piece, metadata=chunk_meta))

    logger.info("Chunking complete: %d chunks produced from %d documents",
                len(chunks), sum(1 for _ in documents) if isinstance(documents, list) else -1)
    return chunks
