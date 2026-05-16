# ComplianceIQ — Recording Cheat-Sheet

Print this or keep it on your second monitor. Every row tells you what to
show, what to say in one line, and what to type or click.

## Pre-recording (10 min before)

```powershell
cd D:\ComplianceIQ
.venv\Scripts\Activate.ps1
uv sync
python main.py smoke-test

# Pre-warm pipeline so the live --limit 5 run is fast
python main.py ingest --extract
python main.py index
python main.py orchestrate
python main.py graph-build
python main.py graph-visualize
python main.py report

# Delete only gaps.jsonl so live run has fresh work
Remove-Item D:\ComplianceIQ\data\processed\gaps.jsonl
```

Open all windows: PowerPoint (Alt+F5 for Presenter View), Terminal 1
(in `D:\ComplianceIQ`, venv active), Terminal 2 (in `D:\ComplianceIQ`,
venv active), Browser tabs for `localhost:7860` and `localhost:8000/docs`
(don't load yet), Word with `reports\compliance_assessment_report.docx`.

Start OBS Studio. Hit Record. Count 3-2-1. Advance to slide 1.

## Minute-by-minute timeline

| Time | Show | Say | Type / Click |
|---|---|---|---|
| 0:00 | Slide 1 | "Hi, this is the ComplianceIQ capstone demo." | — |
| 0:15 | Slide 1 | "AI-driven multi-agent system mapping IRDAI/MAS regs to internal policies." | — |
| 0:30 | Slide 1 | "End to end in under 30 minutes for less than ten cents." | Press → |
| 0:45 | Slide 2 | "Compliance teams spend weeks cross-referencing policies." | — |
| 1:00 | Slide 2 | "Multi-jurisdiction complexity, manual mapping, late gap discovery, doc burden." | — |
| 1:30 | Slide 2 | "ComplianceIQ replaces that with an observable AI pipeline." | Press → |
| 1:45 | Slide 3 | "Five layers: ingestion, vector store, agents, orchestration, interfaces." | — |
| 2:15 | Slide 3 | "Cross-cutting Langfuse observability + immutable audit log." | Press → |
| 2:45 | Slide 4 | "12-stage pipeline, each stage writes JSONL — independently runnable." | — |
| 3:15 | Slide 4 | "Re-runs are idempotent — Chroma uses deterministic IDs." | Press → |
| 3:30 | Slide 5 | "Three single-responsibility agents." | — |
| 4:00 | Slide 5 | "Every agent: prompt | llm.with_structured_output and a Pydantic schema." | Press → |
| 4:30 | Slide 6 | "Let me show it running." | ALT-TAB to Terminal 1 |
| 4:35 | Terminal 1 | "Five requirements, eight workers." | `python main.py orchestrate --concurrency 8 --limit 5` |
| 4:35–6:00 | (running) | "Regulation Monitor first... Gap Detector parallel... appended to JSONL." | Wait |
| 6:00 | Terminal 1 | "Score — pure Python, no LLM in the headline metric." | `type data\processed\compliance_score.json \| more` |
| 6:15 | (JSON visible) | "Severity weights times coverage. Auditors can recompute by hand." | Space to scroll |
| 6:30 | Terminal 1 | "Now the dashboard." | `python main.py dashboard` |
| 6:35 | Browser :7860 | "Overview shows org-wide score and per-domain breakdown." | Click **Overview** |
| 6:50 | Gaps tab | "Filterable by domain, severity, coverage." | Click **Gaps**, Severity=high, Refresh |
| 7:05 | Coverage tab | "Per-domain Coverage Assessment from Policy Analyzer." | Click **Coverage** |
| 7:15 | Remediation tab | "Prioritised action list, severity-weighted." | Click **Remediation** |
| 7:25 | Search tab | "Semantic search against ChromaDB." | Click **Search**, "incident reporting", Search |
| 7:40 | Reports tab | "One-click DOCX report regen." | Click **Reports** (don't click Generate) |
| 7:50 | Upload tab | "New: file upload + HITL review queue." | Click **Upload**, scroll to HITL panel |
| 8:00 | Word (report) | "Audit-ready DOCX — exec summary, scoring, gaps, evidence." | ALT-TAB to Word, scroll 2-3 sections |
| 8:25 | Terminal 2 | "Same workflow over HTTP." | ALT-TAB to Terminal 2; `python main.py api` |
| 8:35 | Browser :8000/docs | "FastAPI surface — GET /score." | `/docs` → expand `GET /score` → Execute |
| 8:50 | /docs | "Gaps filtered to high-severity and needs-review." | `GET /gaps`, severity=high, needs_review=true, Execute |
| 9:05 | Terminal 1 | "Every assessment writes a snapshot. Compare shows the delta." | ALT-TAB Terminal 1; `python main.py history --compare` |
| 9:20 | Terminal 1 | "Every LLM call is traced in Langfuse." | — |
| 9:30 | Slide 8 | "22 docs, 3 agents, ~700 calls, <$0.10, <30 min, 100% trace coverage." | ALT-TAB PowerPoint; press → |
| 9:50 | Slide 9 | "Layered, typed, observable. Three reach surfaces. Thank you." | — |
| 10:00 | Slide 9 | (silent 2 s) | **STOP RECORDING** |

## Hard rules

- Don't restart on a glitch — calmly say "let me try that again" and continue.
- Don't open `.env` on camera.
- Read at conversational pace — pause silently if you finish a row early.
- Pre-load both browser tabs BEFORE recording.

## Post

```powershell
# Re-encode for size if the OBS file is too big:
ffmpeg -i .\original.mkv -c:v libx264 -preset slow -crf 23 -c:a aac -b:a 128k D:\ComplianceIQ_demo.mp4

# Verify
Get-Item D:\ComplianceIQ_demo.mp4 | Select Name, Length, LastWriteTime
# Target: 100-200 MB for ~10 min at 1080p
```

Upload to Google Drive → "Anyone with the link → Viewer" → paste URL into IK submission form.
