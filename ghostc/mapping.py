"""Mapping store — the boundary-internal real<->ghost record.

Holds real values in cleartext because the reverse patch compiler needs them.
Must never cross the privacy boundary. Once an entry is `frozen`, its `ghost`
value is stable forever (roadmap principle 4: stable mappings).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ghostc.audit import hash_real


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MappingStore:
    def __init__(self, path: str | Path, mapping_version: int = 1):
        self.path = Path(path)
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = {
                "mapping_version": mapping_version,
                "created": _now(),
                "updated": _now(),
                "entries": [],
            }

    # -- lookup ---------------------------------------------------------------
    def by_entity_id(self, entity_id: str) -> dict | None:
        return next((e for e in self.data["entries"] if e["entity_id"] == entity_id), None)

    def by_ghost(self, ghost: str) -> dict | None:
        return next((e for e in self.data["entries"] if e["ghost"] == ghost), None)

    # -- mutation ----------------------------------------------------------
    def upsert(self, *, entity_id: str, real: str, ghost: str, kind: str,
               level: str, strategy: str, freeze: bool = True,
               approved_by: str | None = None) -> dict:
        existing = self.by_entity_id(entity_id)
        if existing:
            if existing.get("frozen") and existing["ghost"] != ghost:
                raise ValueError(
                    f"{entity_id}: ghost identity is frozen as {existing['ghost']!r}, "
                    f"refusing to change to {ghost!r}"
                )
            existing.update(real=real, ghost=ghost, kind=kind, level=level, strategy=strategy)
            existing["real_sha256"] = hash_real(real)
            if approved_by:
                existing["approved_by"] = approved_by
            entry = existing
        else:
            entry = {
                "entity_id": entity_id,
                "real": real,
                "real_sha256": hash_real(real),
                "ghost": ghost,
                "kind": kind,
                "level": level,
                "strategy": strategy,
                "frozen": bool(freeze),
                "first_seen_run": _now(),
                "occurrences": [],
            }
            if approved_by:
                entry["approved_by"] = approved_by
            self.data["entries"].append(entry)
        return entry

    def save(self) -> None:
        self.data["updated"] = _now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
