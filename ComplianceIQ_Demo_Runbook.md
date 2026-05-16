# ComplianceIQ Demo — Click-by-Click Runbook

Use this as the second monitor while you record. Every line is exactly what to
type or click; brackets are what to point at on screen.

## Pre-recording checklist (do this 10 minutes before)

- [ ] Close Slack, Teams, Outlook, browser tabs that aren't the demo.
- [ ] Set Windows display scale to 150%; set the terminal font to a readable size (≥14pt).
- [ ] Confirm `.venv` is activated in the terminal you'll use.
- [ ] Run `uv sync` once so fastapi/uvicorn are installed.
- [ ] Run `python main.py smoke-test` — must exit 0.
- [ ] Open the slide deck (`ComplianceIQ_Demo_Slides.pptx`) in PowerPoint, F5 to start.
- [ ] Open the script (`ComplianceIQ_Demo_Script.docx`) on a second monitor.
- [ ] Start your screen recorder (OBS Studio recommended; otherwise `Win + G` Game Bar).
- [ ] Record audio from a wired headset mic, not the laptop's built-in.
- [ ] Hit Record, count down 3-2-1, then advance to Slide 1.

## Window layout

```
+-------------------------+   +-------------------------+
|                         |   |                         |
|   PowerPoint (slides)   |   |   Script (teleprompter) |
|                         |   |                         |
+-------------------------+   +-------------------------+
+-----------------------------------------------------+
|  Terminal 1 (orchestrate/CLI)  |  Terminal 2 (api)  |
+-----------------------------------------------------+
|  Browser: dashboard            |  Browser: /docs    |
+-----------------------------------------------------+
```

## Segment 1 — 0:00–4:30 (Slides only)

Just advance slides 1 → 5 in time with the script. No live action yet.

## Segment 2 — 4:30–6:30 (Live: orchestrate + score)

Switch to Terminal 1.

```powershell
# Make the run snappy and reproducible for the recording
python main.py orchestrate --concurrency 8 --limit 5
```

While it runs (about 60–90 seconds), narrate from the script. When it finishes:

```powershell
# Show the score JSON
type data\processed\compliance_score.json | more
```

Point at:
- `weighted_overall_score` field (top of JSON)
- `by_domain` array (scroll a bit)
- The "deterministic Python scoring" line in the script

## Segment 3 — 6:30–8:00 (Live: Gradio dashboard)

In Terminal 1:

```powershell
python main.py dashboard
```

Open http://localhost:7860 in your browser. Click through the tabs in order and
narrate one sentence per tab from the script:

1. Overview — point at the headline weighted score
2. Gaps — apply a filter (e.g. severity=high) to show interactivity
3. Coverage — point at the per-domain table
4. Remediation — point at top 3 priority items
5. Search — type "incident reporting" and hit Search
6. Reports — say "we'll generate from CLI for cost reasons"
7. **Upload** — show the file picker, then scroll down to the HITL queue panel

## Segment 4 — 8:00–8:45 (DOCX report + FastAPI)

Open `D:\ComplianceIQ\reports\compliance_assessment_report.docx` in Word.
Scroll through:
- Executive summary
- Per-domain score table
- Top gaps
- Remediation plan

Then in Terminal 2 (NEW terminal — leave dashboard running):

```powershell
.venv\Scripts\Activate.ps1
python main.py api
```

Open http://localhost:8000/docs in a new browser tab.
- Click `GET /score` → "Try it out" → "Execute" — point at the response
- Click `GET /gaps` → set `severity=high` and `needs_review=true` → "Execute"

## Segment 5 — 8:45–9:30 (History compare)

Back to Terminal 1 (Ctrl+C to stop dashboard if you need the same terminal,
or use Terminal 2 after stopping the API):

```powershell
python main.py history --compare
```

Read the printed delta. If only one snapshot exists, say "after one more run
the compare flag will show the delta — for now it shows the latest snapshot".

## Segment 6 — 9:30–10:00 (Closing slides)

Switch back to PowerPoint:
- Slide 8 (Headline numbers) — pause for 5 seconds on each metric
- Slide 9 (Recap) — read the bullets, then "Thank you"

Hit Stop on the recorder.

## Post-recording

```powershell
# Trim the head/tail in OBS or Clipchamp
# Export as MP4 (H.264), 1080p, ~5–8 Mbps. Target file < 200 MB.
# Save as: D:\ComplianceIQ_demo.mp4
```

Then upload to Google Drive, set sharing to "Anyone with the link → Viewer",
and paste the URL into the IK submission form.

## Common gotchas

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: dotenv` | You're using system Python, not the venv. `Activate.ps1` first. |
| `OPENAI_API_KEY missing` | Check `.env` exists and has the key; the venv must be activated to pick up `python-dotenv`. |
| `Port 7860 already in use` | `python main.py dashboard --port 7861` |
| `Port 8000 already in use` | `python main.py api --port 8001` |
| Long orchestrate run | Always pass `--limit 5` for the recording; full run is too slow on camera. |
| Dashboard shows "No compliance_score.json" | Run `orchestrate` first; it produces the JSON. |
