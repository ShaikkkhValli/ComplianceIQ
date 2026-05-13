"""Embedding function wrapper.

Single source of truth for the embedding model used everywhere in the system.
The spec mandates OpenAI text-embedding-3-small.

We do NOT use chromadb.utils.embedding_functions.OpenAIEmbeddingFunction —
in chromadb 0.4.x it still calls the removed openai<1.0 API
(`openai.Embedding.create`). Instead we wrap the modern openai>=1.0 client
into a Chroma-compatible embedding function (callable on list[str]).
"""

from __future__ import annotations

from openai import OpenAI

from complianceiq.config import EMBEDDING_MODEL, require_openai_key


class OpenAIEmbeddingFunction:
    """Chroma-compatible embedding function using openai>=1.0."""

    BATCH_SIZE = 100  # well within the 2048 input limit; safer for retries

    def __init__(self, api_key: str | None = None, model: str = EMBEDDING_MODEL):
        self.client = OpenAI(api_key=api_key or require_openai_key())
        self.model = model

    def __call__(self, input):
        """Legacy callable interface. Chroma calls this with input=list[str]."""
        return self._embed_batch(input)

    # ── modern interface (Chroma 0.4.20+) ─────────────────────
    def embed_documents(self, documents):
        """Used during upsert. documents: list[str] -> list[list[float]]."""
        return self._embed_batch(documents)

    def embed_query(self, input):
        """Used during query by Chroma 0.4.20+.

        Chroma's Rust bindings expect this to ALWAYS return list[list[float]]
        (one embedding per input query), even when input is a single string.
        Returning a single embedding causes the Rust layer to iterate over
        floats expecting sequences.
        """
        if isinstance(input, str):
            return self._embed_batch([input])
        if isinstance(input, list):
            return self._embed_batch(input)
        return self._embed_batch([str(input)])

    # ── shared core ───────────────────────────────────────────
    def _embed_batch(self, items):
        if not items:
            return []
        all_embeddings: list[list[float]] = []
        for i in range(0, len(items), self.BATCH_SIZE):
            batch = items[i:i + self.BATCH_SIZE]
            response = self.client.embeddings.create(input=batch, model=self.model)
            all_embeddings.extend(item.embedding for item in response.data)
        return all_embeddings

    def name(self) -> str:
        return f"openai-{self.model}"


def get_embedding_function() -> OpenAIEmbeddingFunction:
    """Return a Chroma-compatible OpenAI embedding function pinned to the spec model."""
    return OpenAIEmbeddingFunction()
