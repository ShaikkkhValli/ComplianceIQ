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
        # Chroma calls this with input=list[str]; older versions used keyword 'texts'.
        if not input:
            return []

        all_embeddings: list[list[float]] = []
        for i in range(0, len(input), self.BATCH_SIZE):
            batch = input[i:i + self.BATCH_SIZE]
            response = self.client.embeddings.create(input=batch, model=self.model)
            all_embeddings.extend(item.embedding for item in response.data)
        return all_embeddings

    def name(self) -> str:
        return f"openai-{self.model}"


def get_embedding_function() -> OpenAIEmbeddingFunction:
    """Return a Chroma-compatible OpenAI embedding function pinned to the spec model."""
    return OpenAIEmbeddingFunction()
