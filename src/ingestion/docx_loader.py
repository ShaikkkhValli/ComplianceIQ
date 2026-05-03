from docx import Document
import os

# ── STEP 2: Load DOCX ─────────────────────────────────────────
class DOCXLoader:
    def __init__(self, domain_inferer):
        self.infer_domain = domain_inferer


    def load_all_docx(self, directory: str) -> list:
        all_docs = []
        docx_files = []

        print(f"\nScanning for DOCX in: {directory}")

        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(".docx"):
                    docx_files.append(os.path.join(root, file))

        print(f"Found {len(docx_files)} DOCX files")

        for full_path in docx_files:
            print(f"\n  Reading: {os.path.basename(full_path)}")
            try:
                doc = Document(full_path)
                current_section = ""
                paras_loaded = 0

                for para in doc.paragraphs:
                    text = para.text.strip()
                    if not text:
                        continue

                    if para.style.name.startswith("Heading"):
                        current_section = text
                        continue

                    all_docs.append({
                        "text": text,
                        "metadata": {
                            "source"      : full_path,
                            "file_name"   : os.path.basename(full_path),
                            "section"     : current_section,
                            "doc_type"    : "policy",
                            "domain"      : self.infer_domain(full_path)
                        }
                    })
                    paras_loaded += 1

                print(f"    Paragraphs loaded: {paras_loaded}")

            except Exception as e:
                print(f"    ERROR loading {os.path.basename(full_path)}: {e}")

        print(f"\nTotal DOCX paragraphs loaded: {len(all_docs)}")
        return all_docs