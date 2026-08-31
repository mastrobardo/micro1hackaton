"""``ghostc discover`` — scan a real repo, score sensitive-entity candidates,
propose the unconfigured ones.

Output:

* a ranked table on stdout (surface → score → evidence → action → entity),
* ``workspace/private/candidates.jsonl`` — one :class:`~ghostc.detect.candidate.Candidate`
  per line (boundary-internal; may name real values),
* ``discover.candidate_scored`` / ``discover.entity_proposed`` audit events
  (surfaces hashed, never cleartext),
* precision / recall vs ``tests/expected/discover-groundtruth.json`` when present.

``discover`` never edits the repo and never mints a mapping entry — a proposed
``restricted`` entity still needs ``approved_by`` in ``privacy.yaml`` before
``compile`` will touch it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from ghostc.audit import AuditLog, hash_real, new_operation_id
from ghostc.config import load_config
from ghostc.detect.scan import ScanResult, scan_repo
from ghostc.detect.settings import detection_settings

_GROUNDTRUTH = Path(__file__).resolve().parents[1] / "tests" / "expected" / \
    "discover-groundtruth.json"


@dataclass
class DiscoverResult:
    scan: ScanResult
    candidates_path: Path
    operation_id: str
    metrics: dict
    decisions: dict | None = None       # {latest, summary} when --decisions was given

    @property
    def proposals(self):
        return [c for c in self.scan.candidates
                if c.entity_id is None and c.action != "ignore"]

    def summary(self) -> str:
        s = self.scan
        lines = [
            f"operation:      {self.operation_id}",
            f"files scanned:  {s.files_scanned}",
            f"candidates:     {len(s.candidates)}  "
            f"(auto {len(s.by_action('auto'))}  review {len(s.by_action('review'))}  "
            f"ignore {len(s.by_action('ignore'))})",
            f"semantic:       {'sentence-transformers' if s.used_embeddings else 'n-gram fallback'}",
            "",
            s.table(),
            "",
            f"proposed entities (not in privacy.yaml): {len(self.proposals)}",
        ]
        latest = (self.decisions or {}).get("latest", {})
        for c in self.proposals:
            from ghostc.review.store import surface_key
            d = latest.get(c.entity_id or surface_key(c.surface))
            tag = f"  -> reviewer: {d['reviewer_action']}" + (
                f" ({d['approved_by']})" if d and d.get("approved_by") else "") if d else ""
            lines.append(f"  {c.surface[:40]:40}  {c.score:4.2f}  {c.kind}/{c.level}  "
                         f"x{len(c.occurrences)}  [{c.action}]{tag}")
        if self.decisions:
            sm = self.decisions["summary"]
            lines.append("")
            if sm["n_decisions"]:
                lines.append(f"review decisions: {sm['n_decisions']}  "
                             f"scorer-vs-human agreement: {sm['agreement_rate']:.0%}  "
                             f"escalations: {sm['escalations']}  overrides: {sm['overrides']}")
            else:
                lines.append("review decisions: 0")
        rc = self.metrics.get("recall_configured")
        if rc is not None:
            lines += ["", f"recall (configured entities re-found from code): {rc:.0%}"]
            if self.metrics.get("missed_configured"):
                lines.append(f"  missed: {', '.join(self.metrics['missed_configured'])}")
        if self.metrics.get("precision_violations"):
            lines.append(f"  PRECISION LEAK — proposed known-public tokens: "
                         f"{', '.join(self.metrics['precision_violations'])}")
        lines += ["", f"candidates written: {self.candidates_path}"]
        return "\n".join(lines)


def discover_repo(repo: str, config_path: str = "privacy.yaml",
                  out: str = "workspace/private/candidates.jsonl",
                  audit_path: str = "workspace/private/audit.jsonl",
                  threshold: float | None = None,
                  decisions_path: str | None = None) -> DiscoverResult:
    repo_p = Path(repo)
    if not repo_p.is_dir():
        raise SystemExit(f"repo not found: {repo}")

    cfg = load_config(config_path)
    settings = detection_settings(cfg)
    if threshold is not None:
        settings = replace(settings, review_threshold=threshold)

    op = new_operation_id()
    audit = AuditLog(audit_path, op)
    audit.emit("run.start", "discovery",
               details={"repo": str(repo_p), "config": config_path})

    res = scan_repo(str(repo_p), settings=settings, cfg=cfg)

    out_p = Path(out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with out_p.open("w", encoding="utf-8") as fh:
        for c in res.candidates:
            fh.write(json.dumps(c.to_dict(), sort_keys=True) + "\n")

    for c in res.candidates:
        subject = {"real_sha256": hash_real(c.surface)}
        if c.entity_id:
            subject["entity_id"] = c.entity_id
        audit.emit("discover.candidate_scored", "discovery", level=c.level,
                   subject=subject, decision=c.action,
                   details={"score": c.score, "evidence": c.evidence,
                            "signals": [s.name for s in c.signals],
                            "occurrences": len(c.occurrences),
                            "configured": c.entity_id is not None})
        if c.entity_id is None and c.action != "ignore":
            audit.emit("discover.entity_proposed", "discovery", level=c.level,
                       subject={"real_sha256": hash_real(c.surface)},
                       details={"kind": c.kind, "score": c.score,
                                "aliases": len(c.aliases),
                                "occurrences": len(c.occurrences),
                                "needs_approval": c.level == "restricted"})

    metrics = _metrics(res)
    audit.emit("run.end", "discovery",
               details={k: v for k, v in metrics.items()
                        if k not in ("proposed", "configured_found")})

    decisions = None
    if decisions_path and Path(decisions_path).exists():
        from ghostc.review.store import DecisionStore
        store = DecisionStore(decisions_path)
        decisions = {"latest": store.latest(), "summary": store.summarize()}

    return DiscoverResult(res, out_p, op, metrics, decisions)


def _metrics(res: ScanResult) -> dict:
    gt = None
    if _GROUNDTRUTH.exists():
        gt = json.loads(_GROUNDTRUTH.read_text(encoding="utf-8"))
    m = res.metrics({"occurrences": {k: 1 for k in gt.get("configured_expected", [])},
                     "absent_by_design": []} if gt else None)
    if not gt:
        return m
    surfaces = {c.surface.lower() for c in res.candidates if c.action != "ignore"}
    surfaces |= {a.lower() for c in res.candidates if c.action != "ignore"
                 for a in c.aliases}
    m["precision_violations"] = sorted(
        tok for tok in gt.get("precision_denylist", [])
        if tok.lower() in surfaces)
    proposals = [c for c in res.candidates
                 if c.entity_id is None and c.action != "ignore"]
    hits = []
    for name, spec in gt.get("proposals_expected", {}).items():
        stems = set(spec.get("stems", [name]))
        min_score = spec.get("min_score", 0.5)
        ok = any(
            c.score >= min_score and (
                stems & {seg for s in [c.surface, *c.aliases]
                         for seg in s.lower().replace("/", " ").replace(".", " ")
                         .replace("-", " ").replace("_", " ").split()})
            for c in proposals)
        hits.append((name, ok))
    m["proposals_expected"] = {n: ok for n, ok in hits}
    m["proposals_recall"] = round(sum(ok for _n, ok in hits) / len(hits), 3) if hits else None
    return m
