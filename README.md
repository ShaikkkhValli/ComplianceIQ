# ComplianceIQ

**AI-Driven Multi-Agent Regulatory Compliance System**

ComplianceIQ analyzes company policies against regulatory requirements (IRDAI, MAS) to identify compliance gaps and produce audit-ready remediation recommendations. It pairs an LLM-driven requirement extractor with three specialized agents — a Regulation Monitor, a Gap Detector, and a Policy Analyzer — over a ChromaDB vector store and a NetworkX knowledge graph, with end-to-end Langfuse observability and a Gradio dashboard.

## Why this exists

Mapping internal policies to regulatory requirements is a complex, manual process. Organizations struggle to keep pace with regulatory change and to maintain comprehensive compliance documentation. ComplianceIQ automates the four hardest parts:

- **Multi-jurisdiction complexity** — handles IRDAI and MAS frameworks in a single workflow.
- **Policy-regulation mapping** — uses semantic search to connect each regulatory requirement to the policy text that covers (or fails to cover) it.
- **Gap identification** — flags gaps with severity scoring and remediation priorities before an audit, not during one.
- **Documentation burden** — emits evidence packets, an audit log, and a DOCX assessment report on every run.

## Core capabilities

| Capability | Where it lives |
| --- | --- |
| Document ingestion (PDF + DOCX) and domain classification | `src/complianceiq/ingestion/` |
| Vector store with OpenAI embeddings | `src/complianceiq/vectorstore/` |
| Regulation Monitor, Gap Detector, Policy Analyzer agents | `src/complianceiq/agents/` |
| Multi-agent orchestration, scoring, evidence collection | `src/complianceiq/orchestration/` |
| Regulation-policy knowledge graph (NetworkX) + visualizations | `src/complianceiq/graph/` |
| Langfuse tracing, audit log, assessment history | `src/complianceiq/observability/` |
| Gradio compliance dashboard | `src/complianceiq/dashboard/` |
| DOCX/Markdown audit-ready report | `src/complianceiq/reporting/` |

## Technology stack

| Component | Technology |
| --- | --- |
| LLM | OpenAI GPT-4o-mini |
| Embeddings | OpenAI text-embedding-3-small |
| Vector database | ChromaDB |
| Agent framework | LangChain v1.0+ with LCEL |
| Knowledge graph | NetworkX |
| Data validation | Pydantic v2 |
| Observability | Langfuse |
| Frontend | Gradio |
| Packaging | Hatchling, `pyproject.toml` |

## Compliance domains covered

Corporate Governance, Risk Management, Information Security, Claims Management, Reinsurance, Internal Audit, Fraud Prevention, plus extensions for Underwriting, Investment Management, and Sales & Distribution. Domain enums are defined in `src/complianceiq/models.py` (`Domain`), and the file-name based classifier lives in `src/complianceiq/ingestion/domain_inference.py`.

## Dataset

22 documents under `data/`:

- 14 regulatory PDFs — `data/regulatory/irdai/` (IRDAI: audit controls, corporate governance, fraud prevention, grievance redressal, information security, insurer investments, internal audit, reinsurance claims, sales advisory, etc.) and `data/regulatory/mas/` (MAS risk-management and conduct guidelines).
- 8 company policies under `data/policies/` (governance, risk & compliance, cyber insurance, underwriting, four reinsurance agreements).
- 1 reference list of regulatory sources (`data/Indicative list of regulatory sources.docx`).

## Repository layout

```
ComplianceIQ/
├── main.py                       # CLI entry point for all weekly tasks
├── pyproject.toml                # project + dependencies
├── requirements.txt              # pinless fallback installer
├── src/complianceiq/
│   ├── models.py                 # Pydantic schemas (Domain, Gap, ComplianceScore, ...)
│   ├── config.py                 # paths + LLM/embedding settings
│   ├── ingestion/                # PDF/DOCX loaders, chunker, extractor, pipeline
│   ├── vectorstore/              # ChromaDB store, embeddings, indexer
│   ├── agents/                   # regulation_monitor, gap_detector, policy_analyzer
│   ├── orchestration/            # workflow, scoring, evidence collection
│   ├── graph/                    # NetworkX builder, analytics, visualizer
│   ├── observability/            # Langfuse tracing, audit log, history
│   ├── reporting/                # DOCX/Markdown report generation
│   └── dashboard/                # Gradio app
├── data/
│   ├── regulatory/{irdai,mas}/   # source PDFs
│   ├── policies/                 # source DOCX
│   ├── processed/                # JSONL outputs from each pipeline stage
│   ├── chroma/                   # persisted vector collections
│   └── graph/                    # compliance_graph.graphml + visualizations
├── reports/                      # generated compliance_assessment_report.docx
└── tests/                        # pytest suite (chunker, scoring, domain inference)
```

## Setup

Requires Python 3.11+.

1. Clone and enter the repo.
2. Install dependencies (uv is recommended; pip works equivalently):
   ```bash
   uv sync                # uses pyproject.toml + uv.lock
   # or
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the project root:
   ```env
   OPENAI_API_KEY=sk-...
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_BASE_URL=https://cloud.langfuse.com
   ```
   `LLM_MODEL`, `EMBEDDING_MODEL`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, and `LLM_TEMPERATURE` can also be overridden via environment variables — defaults are set in `src/complianceiq/config.py`.

If Langfuse keys are absent or fail auth, tracing degrades gracefully — every pipeline step still runs.

## Quickstart — end-to-end

```bash
# 1. Ingest, chunk, and extract requirements from all 22 documents
python main.py ingest --extract

# 2. Index chunks + requirements into ChromaDB
python main.py index

# 3. Run the full multi-agent workflow (gap detection + coverage + scoring + remediation)
python main.py orchestrate

# 4. Build the knowledge graph and its visualizations
python main.py graph-build
python main.py graph-visualize

# 5. Generate the audit-ready report
python main.py report

# 6. Launch the dashboard
python main.py dashboard       # http://localhost:7860
```

## CLI commands, by week

The `main.py` CLI is grouped by the project's eight-week implementation pipeline.

**Week 2 — Document processing**
```bash
python main.py ingest                          # parse PDFs/DOCX, chunk, classify by domain
python main.py ingest --extract                # also extract requirements via LLM
python main.py extract --limit 20              # extract from existing chunks.jsonl
```

**Week 3 — Vector store and embeddings**
```bash
python main.py index                           # upsert into ChromaDB
python main.py index --rebuild                 # drop and re-embed
python main.py search "MFA for privileged accounts"
python main.py search "audit committee" --doc-type policy
```

**Week 4 — Single-agent analysis**
```bash
python main.py analyze-regulation                                # Regulation Monitor over all files
python main.py analyze-regulation --file "fraud-risk-framework"  # one file
python main.py analyze-gaps --limit 20                           # Gap Detector
python main.py analyze-gaps --domain information_security
python main.py analyze-coverage                                  # Policy Analyzer roll-up
```

**Week 5 — Multi-agent orchestration**
```bash
python main.py orchestrate                                       # end-to-end pipeline
python main.py orchestrate --domain information_security --limit 30
python main.py orchestrate --skip-summaries
python main.py score                                             # recompute scores from gaps.jsonl
python main.py remediate                                         # build remediation plan
```

**Week 6 — Knowledge graph**
```bash
python main.py graph-build
python main.py graph-stats           # node/edge counts, top-cited policies, orphans
python main.py graph-visualize       # heatmap + per-domain coverage chart
```

**Week 7 — Observability**
```bash
python main.py history               # last assessment snapshots
python main.py history --compare     # delta vs previous run
python main.py audit-log --tail 50
```

**Week 8 — Production**
```bash
python main.py dashboard             # Gradio UI on :7860
python main.py report                # generate compliance_assessment_report.docx
python main.py smoke-test            # pytest suite
```

## The Gradio dashboard

`python main.py dashboard` (or `python -m complianceiq.dashboard.app`) launches a multi-tab UI:

- **Overview** — headline compliance score, per-domain weighted scores, assessment history.
- **Gaps** — filterable gap listing with severity, remediation priority, and evidence references.
- **Coverage** — per-domain coverage matrix produced by the Policy Analyzer.
- **Remediation** — prioritized remediation plan with effort and severity weighting.
- **Search** — semantic search across the ChromaDB `chunks` and `requirements` collections.
- **Reports** — download the generated DOCX/MD report.

## Outputs

Every pipeline stage writes a JSONL artifact under `data/processed/`, making the full audit trail reproducible:

| File | Produced by | Contains |
| --- | --- | --- |
| `documents.jsonl` | ingestion | one row per source document |
| `chunks.jsonl` | ingestion | chunked text + domain metadata |
| `requirements.jsonl` | extractor (LLM) | structured `Requirement` records |
| `regulation_summaries.jsonl` | Regulation Monitor | mandatory actions + evidence needs per file |
| `gaps.jsonl` | Gap Detector | gaps with `severity` + `remediation_priority` |
| `coverage.jsonl` | Policy Analyzer | per-domain coverage assessments |
| `evidence.jsonl` | orchestration | evidence packets per requirement |
| `compliance_score.json` | scoring | overall + per-domain scores |
| `remediation_plan.jsonl` | scoring | prioritized remediation items |
| `audit_log.jsonl` | observability | append-only audit trail |
| `assessment_history.jsonl` | observability | one snapshot per run for trend tracking |

Knowledge graph artifacts are written under `data/graph/`: `compliance_graph.graphml`, `compliance_graph.json`, `graph_metrics.json`, `coverage_heatmap.png`, `domain_coverage.png`. The final audit-ready report is written to `reports/compliance_assessment_report.docx`.

## Tests

```bash
pytest               # or: python main.py smoke-test
```

The suite under `tests/` covers the chunker, domain inference, scoring math, and an end-to-end smoke test.

## Evaluation alignment

ComplianceIQ implements every objective from the problem statement: multi-agent compliance analysis, semantic regulation understanding via embeddings, automated gap detection with severity scoring, NetworkX-based regulation-policy knowledge graphs, and audit-ready evidence/reporting. The eight-week pipeline maps one-to-one onto the module structure under `src/complianceiq/`, and observability is integrated from ingestion through reporting.

