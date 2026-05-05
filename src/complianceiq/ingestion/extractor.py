"""LLM-based requirement extractor.

Each chunk is fed to an LCEL chain that returns 0 or more structured
Requirements. Boilerplate / TOC / definitions chunks naturally yield empty
batches and are skipped.
"""

from __future__ import annotations

import logging
from typing import Iterable

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from complianceiq.config import LLM_MODEL, LLM_TEMPERATURE, require_openai_key
from complianceiq.models import (
    Chunk,
    Domain,
    Requirement,
    RequirementBatch,
)

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """\
You are a senior regulatory compliance analyst for insurance companies.
Your job is to read a single text excerpt from either a regulatory document
(IRDAI / MAS) or an internal company policy and extract any compliance
requirements it contains.

A REQUIREMENT is a clause that imposes an obligation, prohibition, or expected
control. Examples:
- "Insurers shall implement multi-factor authentication for all privileged accounts."
- "The Board must constitute a Risk Management Committee."
- "Vendors handling customer data must report breaches within 24 hours."

NOT requirements (skip these):
- Definitions, glossary entries
- Background / preamble / scope text without an obligation
- Table-of-contents fragments
- Pure narrative or rationale

Rules:
1. Return an empty list if the excerpt contains no requirements.
2. Quote the requirement text verbatim from the excerpt; do not paraphrase.
3. `mandatory_action` is your one-sentence summary of WHAT must be done.
4. `evidence_needed` lists the documentation/logs/artifacts that would prove
   compliance (e.g. ["board minutes", "MFA enforcement logs", "annual audit report"]).
   Empty list if not implied.
5. `severity`:
   - high   : breach causes regulatory penalty, financial loss, or material harm.
   - medium : non-compliance produces audit findings or reputational risk.
   - low    : best-practice or advisory.
6. `suggested_domain`: only set if the excerpt clearly belongs to a domain
   different from the hint provided. Otherwise leave null.
"""

_USER_PROMPT = """\
Source file : {file_name}
Doc type    : {doc_type}
Domain hint : {domain}
Location    : {location}

Excerpt:
\"\"\"
{text}
\"\"\"

Extract all compliance requirements from the excerpt above as a JSON object
matching the schema. If none, return {{"requirements": []}}.
"""


class RequirementExtractor:
    """Wraps an LCEL chain that returns RequirementBatch per chunk."""

    def __init__(
        self,
        model: str = LLM_MODEL,
        temperature: float = LLM_TEMPERATURE,
        run_id: str | None = None,
    ) -> None:
        require_openai_key()
        from complianceiq.observability import tracing
        self.model_name = model
        self.run_id = run_id
        self.llm = ChatOpenAI(model=model, temperature=temperature)
        self.structured_llm = self.llm.with_structured_output(RequirementBatch)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", _SYSTEM_PROMPT),
            ("user", _USER_PROMPT),
        ])
        chain = self.prompt | self.structured_llm

        # Attach Langfuse callbacks + tags if tracing is enabled.
        handler = tracing.get_handler()
        config: dict = {"tags": ["compliance", "requirement_extractor"]}
        if handler is not None:
            config["callbacks"] = [handler]
        metadata: dict = {"agent": "requirement_extractor", "model": model,
                          "trace_name": "requirement_extractor"}
        if run_id:
            metadata["session_id"] = run_id
        config["metadata"] = metadata
        self.chain = chain.with_config(config)

    # ── public API ────────────────────────────────────────────
    def extract_from_chunk(self, chunk: Chunk) -> list[Requirement]:
        """Run the LLM on a single chunk and return enriched Requirements."""
        meta = chunk.metadata
        location = (
            f"page {meta.page_number}" if meta.page_number is not None
            else (meta.section or "unknown")
        )
        try:
            batch: RequirementBatch = self.chain.invoke({
                "file_name": meta.file_name,
                "doc_type": meta.doc_type,
                "domain": meta.domain.value if isinstance(meta.domain, Domain) else meta.domain,
                "location": location,
                "text": chunk.text,
            })
        except Exception as e:
            logger.warning("Extraction failed for %s [%s chunk %d]: %s",
                           meta.file_name, location, meta.chunk_index, e)
            return []

        return [
            Requirement.from_raw(r, meta, extracted_by=self.model_name)
            for r in batch.requirements
        ]

    def extract_from_chunks(
        self,
        chunks: Iterable[Chunk],
        limit: int | None = None,
    ) -> list[Requirement]:
        """Process chunks sequentially. Use `limit` for cost-controlled runs."""
        results: list[Requirement] = []
        processed = 0
        for chunk in chunks:
            if limit is not None and processed >= limit:
                logger.info("Reached extraction limit of %d chunks; stopping.", limit)
                break
            processed += 1
            extracted = self.extract_from_chunk(chunk)
            if extracted:
                logger.info("[%d] %s — %d requirement(s)",
                            processed, chunk.metadata.file_name, len(extracted))
            results.extend(extracted)

        logger.info("Extraction done: %d requirements from %d chunks",
                    len(results), processed)
        return results
