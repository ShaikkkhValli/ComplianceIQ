import os
from PyPDF2 import PdfReader


class PDFLoader:
    """Loads all PDF files from a directory and extracts page-wise text."""

    def __init__(self, domain_inferer):
        """
        domain_inferer: function to infer domain from file path
        Example: infer_domain
        """
        self.infer_domain = domain_inferer

    def load_all_pdfs(self, directory: str) -> list:
        all_docs = []
        pdf_files = []

        print(f"\nScanning for PDFs in: {directory}")

        # Scan all PDF files
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(".pdf"):
                    pdf_files.append(os.path.join(root, file))

        print(f"Found {len(pdf_files)} PDF files")

        # Read each PDF
        for full_path in pdf_files:
            print(f"\nReading: {os.path.basename(full_path)}")

            try:
                reader = PdfReader(full_path)
                print(f"Pages found: {len(reader.pages)}")

                pages_loaded = 0

                for page_num, page in enumerate(reader.pages):
                    text = page.extract_text()

                    # Skip empty pages
                    if not text or not text.strip():
                        print(f"Page {page_num + 1}: EMPTY — skipped")
                        continue

                    all_docs.append({
                        "text": text.strip(),
                        "metadata": {
                            "source": full_path,
                            "file_name": os.path.basename(full_path),
                            "page_number": page_num + 1,
                            "doc_type": "regulatory",
                            "domain": self.infer_domain(full_path)
                        }
                    })

                    pages_loaded += 1

                print(f"Pages loaded successfully: {pages_loaded}")

            except Exception as e:
                print(f"ERROR loading {os.path.basename(full_path)}: {e}")

        print(f"\nTotal PDF pages loaded: {len(all_docs)}")

        return all_docs