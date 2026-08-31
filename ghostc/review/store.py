"""`DecisionStore` — the reviewer's decisions as an append-only JSONL log.

One record per decision *event*. The **latest** record for a key wins; earlier
records are kept as history (an audit trail / revision log). A key is a
configured entity id, or ``sha256:<hex>`` of the candidate surface for an
unconfigured proposal.

This file is **boundary-internal** (it holds cleartext surfaces, like
`mapping.json`) and must never cross into the ghost. The audit log it emits to
stays hash-only.

Record shape (all keys always present so the JSONL is a clean table)::

    {
      "ts": "2026-08-31T12:00:00+00:00",
      "op_id": "op_ab12cd34ef56",
      "key": "vendor_meridian" | "sha256:9f…",
      "surface": "Meridian",
      "proposed_action": "review",        # the scorer's call: auto | review | ignore
      "proposed_level": "confidential",
      "reviewer_action": "accept",        # accept | ignore | escalate
      "level": "confidential",            # the reviewer's level (accept/escalate)
      "entity_id": "vendor_meridian",     # accept: the id to create / clear
      "ghost": "vendor-e",                # optional alias hint (accept)
      "approved_by": "alice",             # required to CLEAR a restricted entity
      "note": "known reseller",
      "occurrences": 17
    }
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ghostc.audit import AuditLog, hash_real, new_operation_id

REVIEWER_ACTIONS = ("accept", "ignore", "escalate")
_FIELDS = ("ts", "op_id", "key", "surface", "proposed_action", "proposed_level",
           "reviewer_action", "level", "entity_id", "ghost", "approved_by",
           "note", "occurrences")


def surface_key(surface: str) -> str:
    return "sha256:" + hash_real(surface)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DecisionStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.records: list[dict] = []
        if self.path.exists():
            self.records = [json.loads(ln) for ln in
                            self.path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    # -- write ------------------------------------------------------------
    def record(self, *, surface: str, reviewer_action: str,
               key: str | None = None, entity_id: str | None = None,
               proposed_action: str = "review", proposed_level: str | None = None,
               level: str | None = None, ghost: str | None = None,
               approved_by: str | None = None, note: str = "",
               occurrences: int = 0, op_id: str | None = None,
               audit: AuditLog | None = None) -> dict:
        if reviewer_action not in REVIEWER_ACTIONS:
            raise ValueError(f"reviewer_action must be one of {REVIEWER_ACTIONS}")
        rec = {
            "ts": _now(),
            "op_id": op_id or (audit.operation_id if audit else new_operation_id()),
            "key": key or entity_id or surface_key(surface),
            "surface": surface,
            "proposed_action": proposed_action,
            "proposed_level": proposed_level,
            "reviewer_action": reviewer_action,
            "level": level or ("restricted" if reviewer_action == "escalate"
                               else proposed_level),
            "entity_id": entity_id,
            "ghost": ghost,
            "approved_by": approved_by or None,
            "note": note or "",
            "occurrences": int(occurrences),
        }
        self.records.append(rec)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({k: rec[k] for k in _FIELDS}, sort_keys=True) + "\n")
        if audit is not None:
            audit.emit("review.decision_recorded", "review", actor=approved_by or "reviewer",
                       level=rec["level"], decision=reviewer_action,
                       subject={"real_sha256": hash_real(surface),
                                **({"entity_id": entity_id} if entity_id else {})},
                       details={"proposed_action": proposed_action,
                                "occurrences": rec["occurrences"],
                                "has_approver": bool(rec["approved_by"])})
        return rec

    # -- read -----------------------------------------------------------
    def latest(self) -> dict[str, dict]:
        """key -> newest record (records are appended in time order)."""
        out: dict[str, dict] = {}
        for r in self.records:
            out[r["key"]] = r
        return out

    def history(self, key: str) -> list[dict]:
        return [r for r in self.records if r["key"] == key]

    def accepted(self) -> list[dict]:
        """Latest decision per key where the reviewer wants the entity compiled."""
        return [r for r in self.latest().values()
                if r["reviewer_action"] in ("accept", "escalate")]

    def ignored_keys(self) -> set[str]:
        return {k for k, r in self.latest().items() if r["reviewer_action"] == "ignore"}

    def cleared_restricted(self) -> set[str]:
        """entity ids whose latest decision is an ``accept`` carrying an approver —
        the human clearance `ghostc compile` needs to stop blocking."""
        return {r["entity_id"] for r in self.latest().values()
                if r["entity_id"] and r["reviewer_action"] == "accept"
                and r["approved_by"]}

    def summarize(self) -> dict:
        """Scorer-vs-human agreement over every key with a decision.

        Agreement = the scorer flagged it (``auto``/``review``) and the human kept
        it (``accept``/``escalate``), OR the scorer said ``ignore`` and so did the
        human. A disagreement is the scorer and the human pulling opposite ways.
        """
        rows = list(self.latest().values())
        agree = 0
        by_action: dict[str, dict[str, int]] = {}
        for r in rows:
            scorer_keep = r["proposed_action"] in ("auto", "review")
            human_keep = r["reviewer_action"] in ("accept", "escalate")
            ok = scorer_keep == human_keep
            agree += ok
            slot = by_action.setdefault(r["proposed_action"] or "none",
                                        {"n": 0, "agree": 0})
            slot["n"] += 1
            slot["agree"] += ok
        n = len(rows)
        return {
            "n_decisions": n,
            "n_agree": agree,
            "agreement_rate": round(agree / n, 3) if n else None,
            "by_proposed_action": by_action,
            "escalations": sum(1 for r in rows if r["reviewer_action"] == "escalate"),
            "overrides": sum(1 for r in rows
                             if (r["proposed_action"] in ("auto", "review"))
                             != (r["reviewer_action"] in ("accept", "escalate"))),
        }
