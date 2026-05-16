# ComplianceIQ — Detailed Live Demo Script (4:30 - 9:25)

Read every "**Say:**" line aloud. Italic stage directions are silent.

---

## A. Multi-agent pipeline live (4:30 - 6:25)

*ALT-TAB to Terminal 1.*

**Say:** "Let me show this running on real data. I've already ingested the
22 documents and embedded everything into ChromaDB off-camera. Now I'll
kick off the multi-agent workflow — five requirements, eight concurrent
workers — so we can watch it complete in about a minute."

*Type and press Enter:*
```
python main.py orchestrate --concurrency 8 --limit 5
```

**Say:** "This is the ComplianceWorkflow class in
src/complianceiq/orchestration/workflow.py. It creates a UUID4 run-id,
instantiates the three agents, attaches the Langfuse callback handler,
and starts the pipeline."

*When `[Step 1/5] Regulation Monitor` appears:*

**Say:** "Step one — Regulation Monitor. It reads each regulatory file and
produces a structured summary: mandatory actions, evidence needs,
severity counts, all typed via Pydantic."

*When `[Step 2/5] Gap Detector` appears:*

**Say:** "Step two — Gap Detector. For every requirement, it pulls the
top-5 most semantically similar policy chunks from ChromaDB, hands them
to the LLM, and the LLM returns a structured GapAssessment with
coverage, severity, and a confidence score. Each completed gap is
appended to gaps.jsonl in real time, so a crash mid-run loses at most
one gap."

*Point at a row like `[1/5] ... — partially_covered (conf=0.85)`:*

**Say:** "Notice the confidence value next to each result. When the LLM's
confidence falls below the threshold, the gap gets a needs-review flag
— that's the input to the human-in-the-loop gate I'll show in a moment."

*When `[Step 3/5] Evidence Collector` appears:*

**Say:** "Step three bundles regulatory text plus citable policy excerpts
into evidence packets. This is the audit-ready evidence trail."

*When `[Step 4/5] Policy Analyzer` appears:*

**Say:** "Step four — Policy Analyzer rolls everything up per domain and
produces a CoverageAssessment."

*When `[Step 5/5] Scorer + Remediation` appears:*

**Say:** "Step five is pure-Python deterministic scoring — no LLM in the
headline metric. Severity weights three, two, one for high, medium, low,
multiplied by coverage values of one, point five, zero. Same gaps in
always produce the same score. An auditor can recompute by hand."

*When the WORKFLOW COMPLETE banner appears:*

**Say:** "Five requirements analysed end-to-end in about ninety seconds.
Notice the workflow result — counts of summaries, gaps, evidence
packets, the overall weighted score, the file paths to every JSONL
artefact, and whether the HITL gate was triggered."

---

## B. Deterministic score (6:25 - 6:55)

**Say:** "Let me show the actual compliance score that was just produced."

*Type and press Enter:*
```
type data\processed\compliance_score.json | more
```

*Point at `weighted_overall_score`:*

**Say:** "Here's the headline number — the weighted overall score for this
run. Below it, you can see the breakdown by domain: total requirements
analysed, fully / partially / not covered counts, unweighted coverage
score, severity-weighted score, and open gap counts by severity."

*Press Space to scroll.*

**Say:** "Because the formula lives in plain Python and uses fixed
constants, this JSON is reproducible byte-for-byte across runs — that's
why we can hand it to a regulator with a straight face."

---

## C. Gradio dashboard tour (6:55 - 8:00)

**Say:** "Now let's see the same data in the reviewer-facing dashboard."

*Type and press Enter:*
```
python main.py dashboard
```

*Browser auto-opens to http://localhost:7860.*

**Say:** "The dashboard reads the JSONL artefacts directly — no database,
no API layer in v1 — which keeps it simple to deploy and impossible for
the UI to drift from the source of truth."

*Click Overview tab.*

**Say:** "Overview gives the org-wide weighted coverage at the top, then
per-domain scores sorted by weakness, then the assessment history table
so reviewers can see trends across runs."

*Click Gaps tab.*

**Say:** "Gaps is filterable. Let me filter to high-severity items."

*Set Severity = high, click Refresh.*

**Say:** "Every high-severity gap, the regulation source, the mandatory
action, a snippet of the gap description, and how many policy excerpts
the LLM considered. This is what a compliance officer or internal
auditor actually wants to work with."

*Click Coverage tab.*

**Say:** "Coverage shows the per-domain rollup produced by the Policy
Analyzer. Weakest domains at the top — that's where remediation effort
should focus."

*Click Remediation tab.*

**Say:** "Remediation is the prioritised action list. Priority score is
severity-weighted, so high-severity uncovered requirements bubble to
the top."

*Click Search tab, type `incident reporting within 24 hours`, click Search.*

**Say:** "Search runs a semantic query against ChromaDB. Useful for ad-hoc
compliance questions — for example, an auditor asking 'what do our
policies say about incident reporting timelines?'"

*Click Reports tab. Do NOT click Generate.*

**Say:** "Reports has a one-click DOCX regeneration button — we'll see
the report itself in a second."

*Click Upload tab.*

**Say:** "And new for this version — the Upload tab. A non-technical
compliance officer can drop a new policy DOCX or a new regulatory PDF
straight here, and a follow-up orchestrate run will incorporate it.
Below the upload form is the HITL queue panel."

*Scroll down to the HITL panel.*

**Say:** "If the most recent run triggered the human-in-the-loop gate —
because the weighted score dropped below the threshold or any gap was
flagged as low-confidence — the panel shows the reason, the score, the
affected requirement IDs, and the run ID. That's how a reviewer knows
to step in before the remediation plan gets published downstream."

---

## D. Audit-ready DOCX report (8:00 - 8:30)

*ALT-TAB to Word, with `compliance_assessment_report.docx` open.*

**Say:** "Now the audit-ready DOCX report. This is what gets handed to
the regulator or the internal audit committee."

*Scroll to executive summary section.*

**Say:** "Executive summary — overall weighted score, total requirements,
count of high-priority open gaps."

*Scroll to per-domain table.*

**Say:** "Per-domain scoring table, sorted from weakest to strongest,
with the severity-weighted formula visible to anyone who wants to
recompute."

*Scroll to top gaps section.*

**Say:** "Top gaps with severity, coverage, and the verbatim regulatory
clause they fail."

*Scroll to remediation plan.*

**Say:** "And finally the prioritised remediation plan, with concrete
remediation steps and the evidence each gap would need."

---

## E. FastAPI surface (8:30 - 9:00)

*ALT-TAB to Terminal 2.*

**Say:** "Now the FastAPI layer — the same workflow exposed over HTTP."

*Type and press Enter:*
```
python main.py api
```

*Switch to browser tab http://localhost:8000/docs.*

**Say:** "This is the auto-generated OpenAPI surface. GET /score returns
the latest ComplianceScore."

*Expand GET /score, click Try it out, click Execute.*

**Say:** "Same JSON we just looked at on the command line, now consumable
by any HTTP client — Postman, curl, another microservice."

*Expand GET /gaps. Set severity=high, needs_review=true. Click Execute.*

**Say:** "GET /gaps takes filters for domain, severity, and the
needs-review boolean. So the HITL queue is also reachable as a one-line
REST call — another system, a Slack notifier, a ticket creator, can
poll this and route flagged gaps to humans automatically."

*Scroll down to POST /assess without expanding.*

**Say:** "POST /assess kicks off a full orchestration in the background,
returns a run-id immediately, and the client can poll /score or
/history to detect completion. Below that, POST /upload/policy and
POST /upload/regulation accept file uploads for new corpus additions."

---

## F. Trend tracking + observability (9:00 - 9:25)

*ALT-TAB back to Terminal 1.*

**Say:** "Last thing — trend tracking."

*Type and press Enter:*
```
python main.py history --compare
```

**Say:** "Every assessment run writes an immutable snapshot to
assessment_history.jsonl. The compare flag shows the delta against the
previous run, so the team can see whether yesterday's policy update
actually moved the needle, and by how much per domain."

**Say:** "And throughout everything you've just seen, every LLM call has
been streamed to Langfuse with full trace hierarchies — prompt,
response, tokens, latency, cost — tagged with the run-id, the agent
name, and the deterministic compliance score as a custom Langfuse score.
That means prompt versions can be A/B compared in the Langfuse
dashboard."

*ALT-TAB back to PowerPoint for slide 8 (Headline numbers).*

---

## Failure recovery cheatsheet

| Failure | Say |
|---|---|
| orchestrate is slow (>2 min) | "Let me let this finish off-camera — the result is the same compliance_score.json I'll show next." Then `Get-Content data\processed\compliance_score.json` from the pre-warmed run. |
| Dashboard won't load | "I'll use the API instead — same data, different surface." Move to FastAPI segment earlier. |
| Swagger UI fails | "Endpoints are working — let me hit one directly." `Invoke-RestMethod http://localhost:8000/score` |
| Word won't open the DOCX | "Let me show the markdown version instead." `notepad reports\compliance_assessment_report.md` |
| OpenAI rate-limit message | "We just hit the rate limit — the retry-with-backoff in src/complianceiq/utils/retry.py will handle that. Let me move on." Continue to next segment. |
