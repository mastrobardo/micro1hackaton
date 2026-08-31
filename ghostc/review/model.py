"""Streamlit-free glue between `candidates.jsonl`, the `DecisionStore`, and the
implied `privacy.yaml` change. `app.py` is a thin UI over this; the tests drive
it directly.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from ghostc.review.store import DecisionStore, surface_key

# kind -> a sensible default alias prefix / strategy for an accepted proposal,
# mirroring ghostc.compile._KIND_PREFIX / _KIND_STRATEGY.
_KIND_PREFIX = {"vendor": "vendor", "client": "client", "internal_service": "service",
                "region": "region", "person": "person", "infra": "host", "secret": "secret"}
_KIND_STRATEGY = {"secret": "remove"}


def load_candidates(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _key_for(cand: dict) -> str:
    return cand.get("entity_id") or surface_key(cand["surface"])


def review_rows(candidates: list[dict], store: DecisionStore) -> list[dict]:
    """Each candidate joined with its latest human decision (or ``None``).
    Configured entities and `ignore` candidates are dropped — the queue is the
    unconfigured, non-ignored proposals, plus anything already decided."""
    latest = store.latest()
    rows = []
    for c in candidates:
        if c.get("entity_id") is not None or c.get("action") == "ignore":
            continue
        k = _key_for(c)
        d = latest.get(k)
        rows.append({
            "key": k,
            "surface": c["surface"],
            "kind": c.get("kind"),
            "level": c.get("level"),
            "score": c.get("score"),
            "evidence": c.get("evidence"),
            "occurrences": len(c.get("occurrences", [])),
            "proposed_action": c.get("action"),
            "aliases": c.get("aliases", []),
            "decision": d["reviewer_action"] if d else None,
            "decided_level": d["level"] if d else None,
            "approved_by": d["approved_by"] if d else None,
            "note": d["note"] if d else "",
        })
    return rows


def apply_decision(store: DecisionStore, candidate: dict, reviewer_action: str, *,
                   level: str | None = None, entity_id: str | None = None,
                   ghost: str | None = None, approved_by: str | None = None,
                   note: str = "", audit=None) -> dict:
    """Record one reviewer decision about *candidate* (a `candidates.jsonl` dict)."""
    eid = entity_id or candidate.get("entity_id")
    if reviewer_action == "accept" and not eid:
        eid = "rev_" + surface_key(candidate["surface"])[7:19]
    return store.record(
        surface=candidate["surface"],
        reviewer_action=reviewer_action,
        key=candidate.get("entity_id") or surface_key(candidate["surface"]),
        entity_id=eid if reviewer_action in ("accept", "escalate") else None,
        proposed_action=candidate.get("action", "review"),
        proposed_level=candidate.get("level"),
        level=level,
        ghost=ghost,
        approved_by=approved_by,
        note=note,
        occurrences=len(candidate.get("occurrences", [])),
        audit=audit,
    )


def entity_from_decision(rec: dict, cand: dict | None, taken_ghosts: set[str]) -> dict:
    """Turn an ``accept``/``escalate`` decision into a `privacy.yaml` entity dict
    (``source: human``). *cand* is the matching `candidates.jsonl` row if present
    (for its aliases / occurrence spellings)."""
    kind = (cand or {}).get("kind") or "vendor"
    strategy = _KIND_STRATEGY.get(kind, "semantic_alias")
    ghost = rec.get("ghost") or ""
    if strategy != "remove" and not ghost:
        prefix = _KIND_PREFIX.get(kind, "vendor")
        i = 0
        while f"{prefix}-{chr(ord('a') + i)}" in taken_ghosts:
            i += 1
        ghost = f"{prefix}-{chr(ord('a') + i)}"
    ent = {
        "id": rec["entity_id"],
        "real": rec["surface"],
        "kind": kind,
        "level": rec.get("level") or (cand or {}).get("level") or "confidential",
        "strategy": strategy,
        "ghost": ghost,
        "source": "human",
        "note": f"accepted in review by {rec.get('approved_by') or 'reviewer'}"
                + (f" — {rec['note']}" if rec.get("note") else ""),
    }
    if rec.get("approved_by"):
        ent["approved_by"] = rec["approved_by"]
    match = []
    for a in dict.fromkeys([*(cand or {}).get("aliases", []),
                            *[o["surface"] for o in (cand or {}).get("occurrences", [])]]):
        if a and a != rec["surface"]:
            m_kind = "identifier" if (" " not in a and a.replace("_", "").replace("-", "").isalnum()) else "literal"
            match.append({"kind": m_kind, "value": a})
    if match:
        ent["match"] = match[:24]
    return ent


def config_delta(store: DecisionStore, cfg: dict,
                 candidates: list[dict] | None = None) -> dict:
    """What `ghostc compile --decisions` would change in *cfg*:
    ``add`` (new `source: human` entities) and ``clear`` (restricted ids a
    decision now approves)."""
    by_id = {e["id"]: e for e in cfg.get("entities", [])}
    by_key = {_key_for(c): c for c in (candidates or [])}
    taken = {e.get("ghost", "") for e in cfg.get("entities", [])}
    add, clear = [], []
    for rec in store.accepted():
        eid = rec["entity_id"]
        if eid and eid in by_id:
            e = by_id[eid]
            if e.get("level") == "restricted" and not e.get("approved_by") and rec["approved_by"]:
                clear.append(eid)
            continue
        ent = entity_from_decision(rec, by_key.get(rec["key"]), taken)
        taken.add(ent.get("ghost", ""))
        add.append(ent)
    return {"add": add, "clear": sorted(set(clear))}


def delta_yaml(delta: dict) -> str:
    if not delta["add"] and not delta["clear"]:
        return "# no change — no accepted decisions yet"
    out = []
    if delta["add"]:
        out.append("# add to privacy.yaml `entities:`")
        out.append(yaml.safe_dump(delta["add"], sort_keys=False).rstrip())
    if delta["clear"]:
        out.append("\n# add `approved_by:` to these existing restricted entities: "
                   + ", ".join(delta["clear"]))
    return "\n".join(out)
