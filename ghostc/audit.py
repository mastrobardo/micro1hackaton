"""Structured audit log — append-only JSONL, one event per pipeline step.

Never write a real sensitive value here. Use `real_sha256` (see `hash_real`).
The eval report is derived from this log, so it is both the product's observability
feature and the Improvement Changelog's evidence source.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "audit-event.schema.json"


def hash_real(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_operation_id() -> str:
    return f"op_{uuid.uuid4().hex[:12]}"


class AuditLog:
    def __init__(self, path: str | Path, operation_id: str | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.operation_id = operation_id or new_operation_id()

    def emit(self, event: str, component: str, *, actor: str = "system",
             subject: dict | None = None, level: str | None = None,
             decision: str | None = None, details: dict | None = None) -> dict:
        rec = {
            "operation_id": self.operation_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "component": component,
            "actor": actor,
        }
        if subject is not None:
            rec["subject"] = subject
        if level is not None:
            rec["level"] = level
        if decision is not None:
            rec["decision"] = decision
        if details is not None:
            rec["details"] = details
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
        return rec
