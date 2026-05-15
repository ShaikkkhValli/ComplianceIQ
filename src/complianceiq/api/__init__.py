"""FastAPI layer for ComplianceIQ (rubric §12: Deployment & Scalability).

Exposes the workflow as REST endpoints so non-CLI clients can trigger
assessments, fetch the latest score, and download the audit-ready report.

Mounted as a single ASGI app via complianceiq.api.app.app — runnable with:
    uvicorn complianceiq.api.app:app --host 0.0.0.0 --port 8000

The CLI command `python main.py api` launches this directly.
"""

from complianceiq.api.app import app, create_app

__all__ = ["app", "create_app"]
