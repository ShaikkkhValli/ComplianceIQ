import os
import sys
import json

# ── Fix import paths ──────────────────────────────────────────
# Add src to path so imports resolve correctly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ingestion.pdfLoader import PDFLoader
from ingestion.docxLoader import DOCXLoader

from PyPDF2 import PdfReader
from docx import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter

# ── Set correct absolute paths ────────────────────────────────
BASE_DIR        = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
REGULATORY_DIR  = os.path.join(BASE_DIR, "data", "regulatory")
POLICIES_DIR    = os.path.join(BASE_DIR, "data", "policies")
OUTPUT_FILE     = os.path.join(BASE_DIR, "data", "loaded_documents.json")

print(f"BASE_DIR       : {BASE_DIR}")
print(f"REGULATORY_DIR : {REGULATORY_DIR}")
print(f"POLICIES_DIR   : {POLICIES_DIR}")
print(f"Regulatory dir exists : {os.path.exists(REGULATORY_DIR)}")
print(f"Policies dir exists   : {os.path.exists(POLICIES_DIR)}")


# ── Domain inference ──────────────────────────────────────────
def infer_domain(file_path: str) -> str:
    path_lower = file_path.lower()
    domain_keywords = {
        "governance"    : "corporate_governance",
        "risk"          : "risk_management",
        "cyber"         : "information_security",
        "claims"        : "claims_management",
        "reinsurance"   : "reinsurance",
        "audit"         : "internal_audit",
        "fraud"         : "fraud_prevention",
        "underwriting"  : "underwriting",
        "grievance"     : "claims_management",
        "investment"    : "investment_management",
        "sales"         : "sales_distribution",
        "information"   : "information_security",
        "marketing"     : "sales_distribution"
    }
    for keyword, domain in domain_keywords.items():
        if keyword in path_lower:
            return domain
    return "general"





# ── STEP 3: Chunk documents ───────────────────────────────────
def chunk_documents(documents: list) -> list:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size    = 500,
        chunk_overlap = 100,
        separators    = ["\n\n", "\n", ".", " "]
    )

    chunked_docs = []

    for doc in documents:
        chunks = splitter.split_text(doc["text"])
        for i, chunk in enumerate(chunks):
            if chunk.strip():
                chunked_docs.append({
                    "text": chunk.strip(),
                    "metadata": {
                        **doc["metadata"],
                        "chunk_index"  : i,
                        "total_chunks" : len(chunks)
                    }
                })

    return chunked_docs


# ── STEP 4: Validate output ───────────────────────────────────
def validate(chunked: list):
    reg_chunks = [c for c in chunked if c["metadata"]["doc_type"] == "regulatory"]
    pol_chunks = [c for c in chunked if c["metadata"]["doc_type"] == "policy"]
    domains    = set(c["metadata"]["domain"] for c in chunked)
    lengths    = [len(c["text"]) for c in chunked]

    print("\n" + "=" * 50)
    print("VALIDATION REPORT")
    print("=" * 50)
    print(f"Regulatory chunks : {len(reg_chunks)}")
    print(f"Policy chunks     : {len(pol_chunks)}")
    print(f"Total chunks      : {len(chunked)}")
    print(f"Domains detected  : {domains}")
    print(f"Avg chunk length  : {sum(lengths) // len(lengths)} chars")
    print(f"Min chunk length  : {min(lengths)} chars")
    print(f"Max chunk length  : {max(lengths)} chars")

    # Show one sample from each type
    print("\n--- Sample Regulatory Chunk ---")
    if reg_chunks:
        s = reg_chunks[0]
        print(f"  File   : {s['metadata']['file_name']}")
        print(f"  Domain : {s['metadata']['domain']}")
        print(f"  Text   : {s['text'][:200]}...")

    print("\n--- Sample Policy Chunk ---")
    if pol_chunks:
        s = pol_chunks[0]
        print(f"  File   : {s['metadata']['file_name']}")
        print(f"  Domain : {s['metadata']['domain']}")
        print(f"  Text   : {s['text'][:200]}...")


# ── MAIN ──────────────────────────────────────────────────────
if __name__ == "__main__":

    print("\n" + "=" * 50)
    print("STEP 1 & 2: Loading Documents")
    print("=" * 50)

    pdf_loader = PDFLoader(infer_domain)
    docx_loader = DOCXLoader(infer_domain)

    regulatory_docs = pdf_loader.load_all_pdfs(REGULATORY_DIR)
    policy_docs     = docx_loader.load_all_docx(POLICIES_DIR)
    all_docs        = regulatory_docs + policy_docs

    if not all_docs:
        print("\nERROR: No documents loaded. Check your folder paths above.")
        sys.exit(1)

    print("\n" + "=" * 50)
    print("STEP 3: Chunking Documents")
    print("=" * 50)
    chunked = chunk_documents(all_docs)
    print(f"Chunking complete — {len(chunked)} chunks created")

    print("\n" + "=" * 50)
    print("STEP 4: Saving & Validating")
    print("=" * 50)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(chunked, f, indent=2)
    print(f"Saved to: {OUTPUT_FILE}")

    validate(chunked)

    print("\nWeek 1 document loading — COMPLETE")