"""Document ingestion: load → categorize → chunk → extract requirements."""

from complianceiq.ingestion.chunker import chunk_documents
from complianceiq.ingestion.docx_loader import DOCXLoader
from complianceiq.ingestion.domain_inference import infer_domain
from complianceiq.ingestion.extractor import RequirementExtractor
from complianceiq.ingestion.pdf_loader import PDFLoader

__all__ = [
    "chunk_documents",
    "DOCXLoader",
    "infer_domain",
    "PDFLoader",
    "RequirementExtractor",
]
