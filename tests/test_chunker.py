"""Chunker tests."""

from complianceiq.ingestion.chunker import chunk_documents
from complianceiq.models import Document, DocumentMetadata, Domain


def _doc(text: str) -> Document:
    return Document(
        text=text,
        metadata=DocumentMetadata(
            source="test.pdf",
            file_name="test.pdf",
            doc_type="regulatory",
            domain=Domain.GENERAL,
            page_number=1,
            block_type="paragraph",
        ),
    )


def test_empty_docs_produce_no_chunks():
    assert chunk_documents([]) == []


def test_short_doc_is_dropped():
    # MIN_CHUNK_CHARS default is 60 — text below that is filtered.
    assert chunk_documents([_doc("too short")]) == []


def test_long_doc_chunks_with_metadata():
    text = "Section A. " + ("Lorem ipsum dolor sit amet. " * 80)
    chunks = chunk_documents([_doc(text)])
    assert len(chunks) >= 1
    for c in chunks:
        assert c.metadata.file_name == "test.pdf"
        assert c.metadata.total_chunks == len(chunks)
        assert 0 <= c.metadata.chunk_index < len(chunks)
        assert len(c.text) >= 1
