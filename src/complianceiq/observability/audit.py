"""Compliance audit logger.

Append-only JSONL log of compliance-relevant events. Designed to be the
regulator-grade trail of "who did what when". Never rewrites past entries.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from complianceiq.config import AUDIT_LOG_FILE
from complianceiq.models import AuditEvent

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditLogger:
    """Thread-unsafe but multi-process-safe-enough append-only logger.

    Each event is one JSON line; failures to write are logged but never
    raised so the workflow doesn't break on a logging hiccup.
    """

    def __init__(self, run_id: str | None = None,
                 path: Path = AUDIT_LOG_FILE) -> None:
        self.run_id = run_id or str(uuid.uuid4())
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ── public API ────────────────────────────────────────────
    def log(
        self,
        event_type: str,
        actor: str = "system",
        entity_type: str | None = None,
        entity_id: str | None = None,
        payload: dict | None = None,
    ) -> AuditEvent:
        evt = AuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=_now_iso(),
            run_id=self.run_id,
            event_type=event_type,
            actor=actor,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload or {},
        )
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(evt.model_dump(mode="json"), ensure_ascii=False))
                f.write("\n")
        except Exception as e:
            logger.warning("Audit write failed (%s): %s", event_type, e)
        return evt


def read_recent(path: Path = AUDIT_LOG_FILE, tail: int = 50) -> list[AuditEvent]:
    """Return the last `tail` audit events from the log."""
    if not path.exists():
        return []
    out: list[AuditEvent] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(AuditEvent.model_validate_json(line))
            except Exception:
                continue
    return out[-tail:]


def print_recent(tail: int = 30) -> None:
    events = read_recent(tail=tail)
    print()
    print("=" * 70)
    print(f"AUDIT LOG (last {len(events)} events)")
    print("=" * 70)
    if not events:
        print("(empty)")
        return
    for e in events:
        ent = f"{e.entity_type}:{e.entity_id}" if e.entity_id else "-"
        print(f"{e.timestamp}  run={e.run_id[:8]}  {e.event_type:<25} "
              f"actor={e.actor:<25} entity={ent}")
