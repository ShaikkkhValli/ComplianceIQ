"""Week 3 vector store: ChromaDB + OpenAI embeddings."""

from complianceiq.vectorstore.embeddings import get_embedding_function
from complianceiq.vectorstore.indexer import build_index
from complianceiq.vectorstore.store import ChromaStore, SearchHit

__all__ = [
    "ChromaStore",
    "SearchHit",
    "build_index",
    "get_embedding_function",
]
