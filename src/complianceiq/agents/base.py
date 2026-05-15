"""Common base for Week 4 agents.

Each agent shares the LLM client and a lazy reference to the vector store.
Subclasses build their own LCEL chains via `make_chain(schema)`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from complianceiq.config import LLM_MODEL, LLM_TEMPERATURE, require_openai_key
from complianceiq.models import Requirement
from complianceiq.observability import tracing
from complianceiq.utils.cache import cached_llm_call
from complianceiq.utils.retry import with_retries
from complianceiq.vectorstore.store import ChromaStore

logger = logging.getLogger(__name__)


def load_requirements(path: Path) -> list[Requirement]:
    """Read requirements.jsonl into a list of Pydantic objects."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python main.py ingest --extract` first."
        )
    out: list[Requirement] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(Requirement.model_validate_json(line))
            except Exception as e:
                logger.warning("Skipping malformed line %d in %s: %s", line_no, path, e)
    return out


def write_jsonl(path: Path, records: Iterable) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            payload = r.model_dump(mode="json") if hasattr(r, "model_dump") else r
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    logger.info("Wrote %s", path)


class BaseAgent:
    """Shared scaffolding: LLM, vector store, chain factory."""

    def __init__(
        self,
        model: str = LLM_MODEL,
        temperature: float = LLM_TEMPERATURE,
        store: ChromaStore | None = None,
        run_id: str | None = None,
    ) -> None:
        require_openai_key()
        self.model_name = model
        self.llm = ChatOpenAI(model=model, temperature=temperature)
        self._store = store
        self.run_id = run_id  # session id propagated into Langfuse traces

    @property
    def store(self) -> ChromaStore:
        if self._store is None:
            self._store = ChromaStore.load()
        return self._store

    def make_chain(
        self,
        system_prompt: str,
        user_template: str,
        schema,
        agent_name: str | None = None,
        model: str | None = None,
    ):
        """Build a `prompt | llm.with_structured_output(schema)` chain.

        If `model` is provided it overrides the agent's default model for this
        single chain — used by tier-up routing in the Gap Detector.

        Tracing: when Langfuse is enabled, the chain is pre-configured with the
        callback handler and metadata so every `chain.invoke()` is traced.
        """
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", user_template),
        ])
        llm = self.llm if model is None or model == self.model_name else ChatOpenAI(
            model=model, temperature=LLM_TEMPERATURE,
        )
        chain = prompt | llm.with_structured_output(schema)

        handler = tracing.get_handler()
        config: dict = {}
        if handler is not None:
            config["callbacks"] = [handler]
        tags = ["compliance"]
        metadata: dict = {"model": model or self.model_name}
        if agent_name:
            tags.append(agent_name)
            metadata["agent"] = agent_name
            metadata["trace_name"] = agent_name
        if self.run_id:
            metadata["session_id"] = self.run_id
        config["tags"] = tags
        config["metadata"] = metadata

        return chain.with_config(config)

    def invoke_with_resilience(
        self,
        chain,
        input_payload: dict,
        *,
        agent_name: str,
        diagnostic: dict | None = None,
        cacheable: bool = True,
    ):
        """Invoke an LCEL chain with retries + optional response caching.

        Caching keys on (model, prompt-text, schema-name); duplicate
        requirement chunks within the same run hit the cache instead of
        the LLM.
        """
        diag = {"agent": agent_name, **(diagnostic or {})}

        @with_retries(diagnostic=diag)
        def _invoke():
            return chain.invoke(input_payload)

        if not cacheable:
            return _invoke()

        # Render the prompt deterministically for the cache key
        prompt_text = json.dumps(input_payload, sort_keys=True, default=str)
        schema_name = (
            chain.last.steps[-1].__class__.__name__
            if hasattr(chain, "last") else type(chain).__name__
        )
        return cached_llm_call(
            model=self.model_name,
            prompt=prompt_text,
            schema=schema_name,
            invoke=_invoke,
        )
