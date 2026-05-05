"""Smoke test: imports + basic Pydantic validation. No LLM, no network."""

import json


def test_all_modules_import():
    """Every package module should import cleanly."""
    import complianceiq
    import complianceiq.config
    import complianceiq.models
    import complianceiq.ingestion
    import complianceiq.ingestion.pdf_loader
    import complianceiq.ingestion.docx_loader
    import complianceiq.ingestion.chunker
    import complianceiq.ingestion.domain_inference
    import complianceiq.ingestion.extractor
    import complianceiq.ingestion.pipeline
    import complianceiq.vectorstore
    import complianceiq.vectorstore.embeddings  # may require OPENAI_API_KEY at use time
    import complianceiq.vectorstore.store
    import complianceiq.agents
    import complianceiq.agents.base
    import complianceiq.agents.gap_detector
    import complianceiq.agents.policy_analyzer
    import complianceiq.agents.regulation_monitor
    import complianceiq.orchestration
    import complianceiq.orchestration.evidence
    import complianceiq.orchestration.scoring
    import complianceiq.orchestration.workflow
    import complianceiq.graph
    import complianceiq.graph.builder
    import complianceiq.graph.analytics
    import complianceiq.observability
    import complianceiq.observability.tracing
    import complianceiq.observability.audit
    import complianceiq.observability.history
    import complianceiq.reporting
    import complianceiq.reporting.docx_report

    assert complianceiq.__version__


def test_pydantic_models_roundtrip():
    """Key models should serialize and deserialize losslessly."""
    from complianceiq.models import (
        CoverageQuality, Domain, Gap, PolicyMatch, Severity,
    )

    g = Gap(
        requirement_id="abc",
        regulation_source="reg.pdf",
        regulation_text="text",
        mandatory_action="action",
        domain=Domain.RISK_MANAGEMENT,
        coverage=CoverageQuality.PARTIALLY_COVERED,
        matching_policies=[
            PolicyMatch(policy_file="pol.docx", location="p.1", excerpt="x", distance=0.3),
        ],
        gap_description="missing thing",
        severity=Severity.HIGH,
        remediation_priority=Severity.HIGH,
        remediation_steps=["do this"],
        evidence_needed=["board minutes"],
        analyzed_by="test",
    )

    raw = g.model_dump_json()
    parsed = Gap.model_validate_json(raw)
    assert parsed.requirement_id == "abc"
    assert parsed.coverage == CoverageQuality.PARTIALLY_COVERED
    assert parsed.matching_policies[0].policy_file == "pol.docx"


def test_audit_event_serializes():
    from complianceiq.models import AuditEvent
    e = AuditEvent(
        event_id="e1", timestamp="2026-01-01T00:00:00+00:00",
        run_id="r1", event_type="test_event", actor="system",
    )
    j = json.loads(e.model_dump_json())
    assert j["event_type"] == "test_event"
    assert j["payload"] == {}
