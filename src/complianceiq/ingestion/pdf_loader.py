"""PDF loader using pdfplumber.

Extracts page text and tables. Detects scanned (image-only) PDFs and
flags them so the caller can decide whether to OCR or skip.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable

import pdfplumber

from complianceiq.models import Document, DocumentMetadata, Domain

logger = logging.getLogger(__name__)

DomainInferer = Callable[[str], Domain]


class PDFLoader:
    """Loads regulatory PDFs into Document objects (one per page; tables separated)."""

    def __init__(self, domain_inferer: DomainInferer) -> None:
        self.infer_domain = domain_inferer
        self.failed_files: list[tuple[str, str]] = []
        self.scanned_files: list[str] = []

    @staticmethod
    def _is_pdf(name: str) -> bool:
        if name.startswith("~$") or name.startswith("."):
            return False
        return name.lower().endswith(".pdf")

    @staticmethod
    def _table_to_text(table):
        rows = []
        for row in table:
            cells = [(c or "").strip().replace("\n", " ") for c in row]
            if any(cells):
                rows.append(" | ".join(cells))
        return "\n".join(rows)

    def load_all_pdfs(self, directory):
        directory = Path(directory)
        if not directory.exists():
            logger.warning("PDF directory does not exist: %s", directory)
            return []

        pdf_files = sorted(
            p for p in directory.rglob("*") if p.is_file() and self._is_pdf(p.name)
        )
        logger.info("Found %d PDF files in %s", len(pdf_files), directory)

        documents = []
        for pdf_path in pdf_files:
            documents.extend(self._load_one(pdf_path))

        logger.info(
            "PDF loading complete: %d documents, %d failed, %d likely scanned",
            len(documents), len(self.failed_files), len(self.scanned_files),
        )
        return documents

    def _load_one(self, pdf_path):
        documents = []
        domain = self.infer_domain(str(pdf_path))

        try:
            with pdfplumber.open(pdf_path) as pdf:
                pages_with_text = 0
                for page_num, page in enumerate(pdf.pages, start=1):
                    text = (page.extract_text() or "").strip()

                    try:
                        tables = page.extract_tables() or []
                    except Exception as e:
                        logger.debug("Table extraction failed on %s p.%d: %s",
                                     pdf_path.name, page_num, e)
                        tables = []

                    if text:
                        pages_with_text += 1
                        documents.append(Document(
                            text=text,
                            metadata=DocumentMetadata(
                                source=str(pdf_path),
                                file_name=pdf_path.name,
                                doc_type="regulatory",
                                domain=domain,
                                page_number=page_num,
                                block_type="paragraph",
                            ),
                        ))

                    for t_idx, table in enumerate(tables):
                        table_text = self._table_to_text(table)
                        if not table_text:
                            continue
                        documents.append(Document(
                            text=table_text,
                            metadata=DocumentMetadata(
                                source=str(pdf_path),
                                file_name=pdf_path.name,
                                doc_type="regulatory",
                                domain=domain,
                                page_number=page_num,
                                section="table_" + str(t_idx + 1),
                                block_type="table",
                            ),
                        ))

                if pages_with_text == 0 and len(pdf.pages) > 0:
                    self.scanned_files.append(str(pdf_path))
                    logger.warning(
                        "No extractable text in %s - likely scanned. Consider OCR.",
                        pdf_path.name,
                    )

        except Exception as e:
            logger.exception("Failed to load PDF %s", pdf_path.name)
            self.failed_files.append((str(pdf_path), str(e)))

        return documents
