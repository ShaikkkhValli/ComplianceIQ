"""FastAPI application exposing the ComplianceIQ workflow over HTTP.

Endpoints
---------
    GET  /healthz                    Liveness probe (returns 200 if Python is up).
    GET  /readyz                     Readiness probe (checks Chroma + .env).
    GET  /score                      Latest ComplianceScore (reads compliance_score.json).
    GET  /gaps                       List of Gaps (filterable by domain / severity / needs_review).
    GET  /coverage                   Per-domain CoverageAssessment list.
    GET  /remediation                Prioritized RemediationPlan items.
    GET  /history                    Assessment history snapshots.
    GET  /report/docx                Download the latest DOCX assessment report.
    POST /assess                     Run a fresh orchestration. Body: AssessRequest.
    POST /upload/policy              Upload a new policy DOCX into data/policies/.
    POST /upload/regulation          Upload a new regulatory PDF into data/regulatory/{regulator}/.

Background runs
---------------
POST /assess returns 202 with a run_id and runs the workflow in a background
task so the HTTP call doesn't block for 30 minutes. Clients poll /score or
/history to detect completion.
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Annotated, Any, Optional

logger = logging.getLogger(__name__)

# FastAPI is imported lazily inside create_app() so the rest of the project
# remains importable even when fastapi is not installed (e.g. minimal CI).


def create_app():  # noqa: C901 - the route definitions inflate complexity but are simple
    try:
        from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import FileResponse, JSONResponse
        from pydantic import BaseModel
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "FastAPI is not installed. Install with: pip install 'fastapi[standard]'"
        ) from e

    from complianceiq.config import (
        COVERAGE_FILE,
        EVIDENCE_FILE,
        GAPS_FILE,
        HISTORY_FILE,
        HITL_REQUIRED_FILE,
        POLICIES_DIR,
        REGULATORY_DIR,
        REMEDIATION_FILE,
        REPORT_DOCX_FILE,
        SCORE_FILE,
    )
    from complianceiq.models import (
        AssessmentSnapshot,
        ComplianceScore,
        CoverageAssessment,
        Gap,
        RemediationItem,
        Severity,
    )

    app = FastAPI(
        title="ComplianceIQ API",
        version="1.0.0",
        description=(
            "REST API for the AI-driven multi-agent regulatory compliance system. "
            "Wraps the same ComplianceWorkflow used by the CLI and Gradio dashboard."
        ),
    )

    # CORS open by default so the dashboard (or any frontend) can talk to the API.
    # In production, narrow allow_origins to your dashboard host.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── request/response schemas ──────────────────────────────────────
    class AssessRequest(BaseModel):
        domain: str | None = None
        limit: int | None = None
        skip_summaries: bool = False
        require_approval: bool = False
        gap_top_k: int = 5

    class AssessAccepted(BaseModel):
        run_id: str
        message: str = "Assessment started in the background."
        poll: list[str] = ["/score", "/history", "/gaps"]

    class HealthOut(BaseModel):
        status: str = "ok"

    class ReadyOut(BaseModel):
        ready: bool
        chroma_present: bool
        score_present: bool
        hitl_required: bool

    # ── helpers ───────────────────────────────────────────────────────
    def _read_jsonl(path: Path, model) -> list:
        out: list = []
        if not path.exists():
            return out
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(model.model_validate_json(line))
                except Exception as e:
                    logger.warning("Skipping malformed line in %s: %s", path, e)
        return out

    # ── liveness / readiness ──────────────────────────────────────────
    @app.get("/healthz", response_model=HealthOut, tags=["meta"])
    def healthz() -> HealthOut:
        return HealthOut()

    @app.get("/readyz", response_model=ReadyOut, tags=["meta"])
    def readyz() -> ReadyOut:
        from complianceiq.config import CHROMA_DIR
        return ReadyOut(
            ready=CHROMA_DIR.exists() and SCORE_FILE.exists(),
            chroma_present=CHROMA_DIR.exists(),
            score_present=SCORE_FILE.exists(),
            hitl_required=HITL_REQUIRED_FILE.exists(),
        )

    # ── reads ─────────────────────────────────────────────────────────
    @app.get("/score", response_model=ComplianceScore, tags=["read"])
    def get_score() -> ComplianceScore:
        if not SCORE_FILE.exists():
            raise HTTPException(404, "No compliance_score.json yet — run POST /assess first.")
        return ComplianceScore.model_validate_json(SCORE_FILE.read_text(encoding="utf-8"))

    @app.get("/gaps", response_model=list[Gap], tags=["read"])
    def list_gaps(
        domain: Optional[str] = Query(None, description="Filter by Domain enum value."),
        severity: Optional[str] = Query(None, description="Filter by Severity enum value."),
        needs_review: Optional[bool] = Query(None, description="Filter HITL-flagged gaps only."),
        limit: int = Query(500, ge=1, le=10000),
    ) -> list[Gap]:
        gaps: list[Gap] = _read_jsonl(GAPS_FILE, Gap)
        if domain:
            gaps = [g for g in gaps if g.domain.value == domain]
        if severity:
            gaps = [g for g in gaps if g.severity.value == severity]
        if needs_review is not None:
            gaps = [g for g in gaps if g.needs_review == needs_review]
        return gaps[:limit]

    @app.get("/coverage", response_model=list[CoverageAssessment], tags=["read"])
    def list_coverage() -> list[CoverageAssessment]:
        return _read_jsonl(COVERAGE_FILE, CoverageAssessment)

    @app.get("/remediation", response_model=list[RemediationItem], tags=["read"])
    def list_remediation(top_n: int = Query(50, ge=1, le=10000)) -> list[RemediationItem]:
        return _read_jsonl(REMEDIATION_FILE, RemediationItem)[:top_n]

    @app.get("/history", response_model=list[AssessmentSnapshot], tags=["read"])
    def list_history() -> list[AssessmentSnapshot]:
        return _read_jsonl(HISTORY_FILE, AssessmentSnapshot)

    @app.get("/report/docx", tags=["read"])
    def download_report():
        if not REPORT_DOCX_FILE.exists():
            raise HTTPException(404, "Report not generated yet — run `python main.py report`.")
        return FileResponse(
            path=REPORT_DOCX_FILE,
            filename=REPORT_DOCX_FILE.name,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    # ── HITL inspection ───────────────────────────────────────────────
    @app.get("/hitl", tags=["meta"])
    def hitl_status():
        if not HITL_REQUIRED_FILE.exists():
            return JSONResponse({"hitl_required": False})
        try:
            payload = json.loads(HITL_REQUIRED_FILE.read_text(encoding="utf-8"))
        except Exception:
            payload = {"raw": HITL_REQUIRED_FILE.read_text(encoding="utf-8")}
        return JSONResponse({"hitl_required": True, **payload})

    # ── writes ────────────────────────────────────────────────────────
    @app.post("/assess", response_model=AssessAccepted, status_code=202, tags=["write"])
    def post_assess(req: AssessRequest, background_tasks: BackgroundTasks) -> AssessAccepted:
        from complianceiq.models import Domain
        from complianceiq.orchestration.workflow import ComplianceWorkflow

        domain_enum = Domain(req.domain) if req.domain else None
        wf = ComplianceWorkflow(gap_top_k=req.gap_top_k)
        run_id = wf.run_id

        def _run():
            try:
                wf.run(domain=domain_enum, limit=req.limit,
                       skip_summaries=req.skip_summaries,
                       require_approval=req.require_approval)
            except Exception:
                logger.exception("Background assessment failed for run_id=%s", run_id)

        background_tasks.add_task(_run)
        return AssessAccepted(run_id=run_id)

    @app.post("/upload/policy", tags=["write"])
    async def upload_policy(file: Annotated[UploadFile, File()]) -> dict[str, Any]:
        if not file.filename or not file.filename.lower().endswith(".docx"):
            raise HTTPException(400, "Policy uploads must be .docx")
        POLICIES_DIR.mkdir(parents=True, exist_ok=True)
        target = POLICIES_DIR / Path(file.filename).name
        with target.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        return {"saved_to": str(target), "next_step": "POST /assess to incorporate the new policy."}

    @app.post("/upload/regulation", tags=["write"])
    async def upload_regulation(
        file: Annotated[UploadFile, File()],
        regulator: Annotated[str, Query(description="Regulator subfolder name, e.g. 'irdai' or 'mas'.")] = "irdai",
    ) -> dict[str, Any]:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "Regulatory uploads must be .pdf")
        target_dir = REGULATORY_DIR / regulator.lower()
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / Path(file.filename).name
        with target.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        return {"saved_to": str(target),
                "next_step": "POST /assess to ingest, index, and assess the new regulation."}

    return app


# Expose a module-level `app` for `uvicorn complianceiq.api.app:app`.
# Lazy-build to avoid importing FastAPI at module import time.
_app = None
def __getattr__(name):  # type: ignore[no-redef]
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)
