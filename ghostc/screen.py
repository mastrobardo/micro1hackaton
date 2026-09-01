"""Outbound screen — score whatever is about to cross the privacy boundary.

``ghostc compile`` / ``ghostc compile-spec`` are **closed-world** redactors: they
substitute the entities named in ``privacy.yaml`` + ``mapping.json``, and their
fail-closed gate (:func:`ghostc.spec.compile_spec`) leak-scans for the real
spellings it already knows. A name nobody ever configured — a new client typed
into a ticket, an internal host pasted from a runbook — is invisible to both, and
crosses untouched.

This module is the second gate: it scores the *output* of the compiler for
**unknown** sensitive material. Screening the output rather than the input is the
point — everything the compiler handled is already gone, so every remaining
finding is by construction something the closed world did not cover.

Four evidence layers, all folded into the *same* noisy-OR scorer the detector
uses (:func:`ghostc.detect.candidate.combine_score` + :func:`~ghostc.detect.candidate.classify`):

1. **shapes** — :func:`ghostc.detect.shapes.shape_hits`: emails, internal hosts,
   scoped packages, prefixed secrets, JWTs, contract / tenant ids, RFC1918 IPs.
2. **corpus anchors** — surfaces the last ``ghostc discover`` proposed but nobody
   froze into the config. If the outbound text mentions one, the scorer has
   already flagged that name once and it is still not being substituted.
3. **adjudicator** — an *injected* callable (the client-side LLM, wired in
   ``client_agent/screen_llm.py``). ``ghostc/`` stays LLM-free and dependency-free:
   the model can only ever **accuse**, never redact, and never decide.
4. **decisions** — a reviewer ``ignore`` in ``decisions.jsonl`` suppresses a
   finding permanently; an ``accept`` keeps blocking, because an accepted entity
   belongs in ``privacy.yaml`` where the compiler can act on it.

None of these are *hard* signals (``_HARD_SIGNALS`` in
:mod:`ghostc.detect.candidate`), so :func:`~ghostc.detect.candidate.classify` can
never return ``auto`` here: a screen finding is only ever ``review`` or
``ignore``. The screener queues and blocks; it never transforms anything.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

from ghostc.audit import AuditLog, hash_real, new_operation_id
from ghostc.config import load_config
from ghostc.detect.candidate import Candidate, Occurrence, Signal, classify, combine_score
from ghostc.detect.settings import DetectionSettings, detection_settings
from ghostc.detect.shapes import shape_hits
from ghostc.scanning import anchored_scan

#: An adjudicator takes ``(ghost_text, real_text)`` and returns raw accusations,
#: ``[{"surface": str, "kind": str, "confidence": float, "why": str}, ...]``.
#: ``real_text`` is boundary-internal; an adjudicator that does not want it may
#: ignore it. Anything it returns is verified against *ghost_text* before it
#: scores, so the real half of its input can never smuggle a finding through.
Adjudicator = Callable[[str, "str | None"], Sequence[dict]]

MODES = ("block", "warn", "off")

W_ANCHOR = 0.75        # a name a previous `discover` proposed and nobody froze
W_LLM_CAP = 0.60       # an adjudicator at full confidence — alone: review, never auto

# Privacy level implied by a finding's kind. Mirrors ``_DEFAULT_LEVEL_BY_KIND`` in
# ``ghostc/detect/scan.py``; kept local so the screener stays import-light.
_LEVEL_BY_KIND = {
    "vendor": "internal", "client": "restricted", "internal_service": "confidential",
    "infra_identifier": "confidential", "domain": "confidential", "secret": "restricted",
    "person": "restricted",
}

# Which entity kind each structural shape stands for.
_KIND_BY_SHAPE = {
    "rfc1918_ip": "infra_identifier", "aws_account_id": "infra_identifier",
    "aws_access_key_id": "secret", "prefixed_secret": "secret",
    "named_secret": "secret", "jwt": "secret",
    "contract_id": "infra_identifier", "tenant_id": "infra_identifier",
    "internal_host": "domain", "scoped_npm_package": "vendor", "email": "person",
}


class ScreenError(ValueError):
    """Bad arguments (unknown mode, unusable adjudicator output in ``required``)."""


@dataclass
class ScreenResult:
    """What the screen found, and whether that stops the run.

    ``findings`` name **real values** — this object is boundary-internal, exactly
    like ``mapping.json`` and ``candidates.jsonl``. Only :meth:`metrics` and the
    audit events it emits are safe to publish.
    """

    findings: list[Candidate] = field(default_factory=list)
    mode: str = "block"
    source: str = "ghost_task"
    operation_id: str = ""
    llm: dict = field(default_factory=lambda: {"status": "off"})
    suppressed: int = 0
    settings: DetectionSettings | None = None

    @property
    def flagged(self) -> list[Candidate]:
        """Findings at or above ``review_threshold`` — the ones that gate."""
        return [c for c in self.findings if c.action != "ignore"]

    @property
    def blocked(self) -> bool:
        return self.mode == "block" and bool(self.flagged)

    @property
    def top_score(self) -> float:
        return round(max((c.score for c in self.findings), default=0.0), 4)

    @property
    def reason(self) -> str:
        if not self.blocked:
            return ""
        worst = max(self.flagged, key=lambda c: c.score)
        return (f"{len(self.flagged)} unscreened finding(s) in the outbound "
                f"{self.source}; strongest: {worst.evidence} @ {worst.score:.2f}")

    def metrics(self) -> dict:
        """Publishable summary — counts, scores and evidence labels, no surfaces."""
        return {
            "screen_source": self.source,
            "screen_mode": self.mode,
            "screen_findings": len(self.flagged),
            "screen_blocked": self.blocked,
            "screen_top_score": self.top_score,
            "screen_suppressed": self.suppressed,
            "screen_evidence": sorted({c.evidence for c in self.flagged}),
            "screen_llm": self.llm.get("status", "off"),
            "screen_llm_dropped": self.llm.get("dropped", 0),
        }

    def summary(self) -> str:
        head = "BLOCK" if self.blocked else ("FLAG" if self.flagged else "CLEAN")
        lines = [
            f"screen:      {head}  ({self.source}, mode={self.mode})",
            f"operation:   {self.operation_id}",
            f"findings:    {len(self.flagged)} flagged / {len(self.findings)} scored"
            + (f"  ({self.suppressed} suppressed by review decisions)"
               if self.suppressed else ""),
            f"adjudicator: {self.llm.get('status', 'off')}"
            + (f"  (model {self.llm['model']}, {self.llm.get('dropped', 0)} unanchored "
               f"claim(s) dropped)" if self.llm.get("model") else ""),
        ]
        if self.findings:
            lines += ["", f"  {'surface':38}  score  action  kind/level  evidence"]
            for c in self.findings:
                lines.append(
                    f"  {c.surface[:38]:38}  {c.score:5.2f}  {c.action:6}  "
                    f"{(c.kind or '?')}/{c.level or '?'}  {c.evidence}")
        if self.blocked:
            lines += ["", f"BLOCKED: {self.reason}",
                      "Add the entity to privacy.yaml, or clear it in the review board "
                      "(ghostc-review -> decisions.jsonl)."]
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# evidence layers                                                             #
# --------------------------------------------------------------------------- #

def _known_ghosts(cfg: dict, mapping_path: str | None) -> set[str]:
    """Every alias the compiler is *supposed* to have emitted.

    A ghost alias matching a shape (``@vendor-a/sdk``, ``ops@client-a.example``)
    is the compiler working, not a leak — suppress it.
    """
    out = {e["ghost"] for e in cfg.get("entities", []) if e.get("ghost")}
    if mapping_path and Path(mapping_path).exists():
        from ghostc.mapping import MappingStore

        out |= {entry["ghost"] for entry in MappingStore(mapping_path).data.get("entries", [])
                if entry.get("ghost")}
    return {g for g in out if g}


def _unfrozen_proposals(candidates_path: str | None) -> list[dict]:
    """Unconfigured, non-ignored candidates from the last ``ghostc discover``."""
    if not candidates_path or not Path(candidates_path).exists():
        return []
    out = []
    for line in Path(candidates_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("entity_id") is None and rec.get("action") != "ignore":
            out.append(rec)
    return out


def _shape_findings(text: str) -> dict[str, tuple[Signal, str, list[int]]]:
    found: dict[str, tuple[Signal, str, list[int]]] = {}
    for hit in shape_hits(text):
        kind = _KIND_BY_SHAPE.get(hit.kind, "vendor")
        sig = Signal("shape", hit.weight, hit.kind)
        prev = found.get(hit.text)
        if prev is None:
            found[hit.text] = (sig, kind, [hit.start])
        else:
            prev[2].append(hit.start)
    return found


def _anchor_findings(text: str, proposals: list[dict]
                     ) -> dict[str, tuple[Signal, str, str | None, list[int]]]:
    """Match every unfrozen proposal spelling (surface + aliases) against *text*."""
    owner: dict[str, dict] = {}
    for rec in proposals:
        for spelling in (rec.get("surface"), *(rec.get("aliases") or [])):
            if spelling:
                owner.setdefault(spelling, rec)
    found: dict[str, tuple[Signal, str, str | None, list[int]]] = {}
    for hit in anchored_scan(text, owner):
        rec = owner[hit.text]
        entry = found.get(hit.text)
        if entry is None:
            found[hit.text] = (
                Signal("anchor", W_ANCHOR, f"discover proposal @ {rec.get('score', 0):.2f}"),
                rec.get("kind") or "vendor", rec.get("level"), [hit.start])
        else:
            entry[3].append(hit.start)
    return found


def _llm_findings(text: str, claims: Iterable[dict]
                  ) -> tuple[dict[str, tuple[Signal, str, list[int]]], int]:
    """Anchor each accusation back into *text*; drop the ones that are not there.

    A model asked to compare a real document with a ghost one can name something
    that only exists in the real half (or in its imagination). Only surfaces that
    literally occur in the outbound text may score.
    """
    found: dict[str, tuple[Signal, str, list[int]]] = {}
    dropped = 0
    for claim in claims:
        surface = str(claim.get("surface") or "").strip()
        if not surface:
            dropped += 1
            continue
        hits = anchored_scan(text, [surface])
        if not hits:
            dropped += 1
            continue
        try:
            conf = min(1.0, max(0.0, float(claim.get("confidence", 1.0))))
        except (TypeError, ValueError):
            conf = 1.0
        kind = str(claim.get("kind") or "vendor")
        why = str(claim.get("why") or "")[:120]
        sig = Signal("llm", round(W_LLM_CAP * conf, 4), why or "adjudicator")
        prev = found.get(surface)
        if prev is None or sig.weight > prev[0].weight:
            found[surface] = (sig, kind, [h.start for h in hits])
    return found, dropped


# --------------------------------------------------------------------------- #
# the screen                                                                  #
# --------------------------------------------------------------------------- #

def screen_text(text: str, *, real_text: str | None = None,
                config_path: str = "privacy.yaml", cfg: dict | None = None,
                mapping_path: str | None = "workspace/private/mapping.json",
                candidates_path: str | None = "workspace/private/candidates.jsonl",
                decisions_path: str | None = None,
                audit_path: str | None = None, operation_id: str | None = None,
                settings: DetectionSettings | None = None,
                adjudicator: Adjudicator | None = None,
                mode: str = "block", source: str = "ghost_task") -> ScreenResult:
    """Score *text* — the bytes about to cross — for unknown sensitive material.

    *real_text* is the boundary-internal original; it is passed to *adjudicator*
    (so the model can diff the two) and is never scanned or written here.

    ``mode``: ``block`` (default — any finding ≥ ``review_threshold`` gates),
    ``warn`` (score and record, never gate), ``off`` (skip the pass entirely).
    """
    if mode not in MODES:
        raise ScreenError(f"mode must be one of {MODES}, got {mode!r}")

    op = operation_id or new_operation_id()
    audit = AuditLog(audit_path, op) if audit_path else None

    if mode == "off":
        result = ScreenResult(mode=mode, source=source, operation_id=op,
                              llm={"status": "off"}, settings=settings)
        if audit:
            audit.emit("screen.scanned", "screen", decision="skip",
                       details={"source": source, "mode": mode})
        return result

    cfg = cfg if cfg is not None else load_config(config_path)
    settings = settings or detection_settings(cfg)

    known = _known_ghosts(cfg, mapping_path)
    shapes = _shape_findings(text)
    anchors = _anchor_findings(text, _unfrozen_proposals(candidates_path))

    llm_info: dict = {"status": "off"}
    llm: dict[str, tuple[Signal, str, list[int]]] = {}
    if adjudicator is not None:
        try:
            claims = list(adjudicator(text, real_text) or [])
            llm, dropped = _llm_findings(text, claims)
            llm_info = {"status": "ran", "claims": len(claims),
                        "anchored": len(llm), "dropped": dropped}
        except Exception as exc:                       # noqa: BLE001 — best-effort layer
            llm_info = {"status": "error", "detail": f"{type(exc).__name__}: {exc}"[:200]}

    # -- merge the layers on the surface spelling --------------------------- #
    surfaces = set(shapes) | set(anchors) | set(llm)
    ignored = _ignored_keys(decisions_path)

    findings: list[Candidate] = []
    suppressed = 0
    for surface in sorted(surfaces):
        if surface in known:
            continue                                   # a ghost alias, working as intended
        signals: list[Signal] = []
        kinds: list[str] = []
        level: str | None = None
        offsets: list[int] = []
        detail = ""
        if surface in shapes:
            sig, kind, offs = shapes[surface]
            signals.append(sig)
            kinds.append(kind)
            offsets += offs
            detail = sig.detail
        if surface in anchors:
            sig, kind, lvl, offs = anchors[surface]
            signals.append(sig)
            kinds.append(kind)
            level = lvl or level
            offsets += offs
        if surface in llm:
            sig, kind, offs = llm[surface]
            signals.append(sig)
            kinds.append(kind)
            offsets += offs
        kind = kinds[0] if kinds else "vendor"
        level = level or _LEVEL_BY_KIND.get(kind)
        score = combine_score(signals)
        action = classify(score=score, level=level, resolved=False,
                          signals=signals, settings=settings)
        if action == "ignore" and _restricted_floor(level, signals):
            action = "review"
        cand = Candidate(
            surface=surface, entity_id=None, kind=kind, level=level, score=score,
            signals=signals, action=action,
            occurrences=[Occurrence(source, 1 + text.count("\n", 0, off), surface,
                                    detail or "screen")
                         for off in sorted(set(offsets))],
        )
        if action != "ignore" and _key(surface) in ignored:
            suppressed += 1
            continue
        findings.append(cand)

    findings.sort(key=lambda c: (-c.score, c.surface))
    result = ScreenResult(findings=findings, mode=mode, source=source, operation_id=op,
                          llm=llm_info, suppressed=suppressed, settings=settings)

    if audit:
        audit.emit("screen.scanned", "screen",
                   decision="block" if result.blocked else "pass",
                   details={"source": source, "mode": mode,
                            "scored": len(findings), "flagged": len(result.flagged),
                            "suppressed": suppressed, "top_score": result.top_score,
                            "adjudicator": llm_info.get("status"),
                            "adjudicator_dropped": llm_info.get("dropped", 0)})
        if result.blocked:
            audit.emit("screen.blocked", "screen", decision="block",
                       details={"source": source, "reason": result.reason,
                                "findings": [
                                    {"real_sha256": hash_real(c.surface),
                                     "score": c.score, "kind": c.kind,
                                     "level": c.level, "evidence": c.evidence,
                                     "occurrences": len(c.occurrences)}
                                    for c in result.flagged]})
    return result


def _restricted_floor(level: str | None, signals: list[Signal]) -> bool:
    """``restricted`` material never crosses unreviewed, whatever it scores.

    The shape weights in :mod:`ghostc.detect.shapes` are tuned for a *repo*, where
    an email address is usually a package author and scores below
    ``review_threshold``. In an outbound task document it is a person, and
    ``privacy.yaml`` already says ``restricted`` needs a human (``approved_by``).
    So a **structural** hit — a shape or a standing ``discover`` proposal — at a
    restricted level is queued even when the noisy-OR score is low.

    Deliberately not extended to the adjudicator: a shape match is a fact about
    the text, an LLM accusation is an opinion, and opinions get scored.
    """
    return level == "restricted" and any(s.name in ("shape", "anchor") for s in signals)


def _key(surface: str) -> str:
    from ghostc.review.store import surface_key

    return surface_key(surface)


def _ignored_keys(decisions_path: str | None) -> set[str]:
    """Surfaces a reviewer has already dismissed. An ``accept`` is deliberately
    *not* suppressed — an accepted entity belongs in ``privacy.yaml``, and until
    it is there the compiler cannot substitute it, so it must keep gating."""
    if not decisions_path or not Path(decisions_path).exists():
        return set()
    from ghostc.review.store import DecisionStore

    return DecisionStore(decisions_path).ignored_keys()


def write_findings(result: ScreenResult, path: str | Path) -> Path:
    """Append the findings to a boundary-internal JSONL the review board can read."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for c in result.findings:
            fh.write(json.dumps({**c.to_dict(), "op_id": result.operation_id,
                                 "source": result.source}, sort_keys=True) + "\n")
    return p
