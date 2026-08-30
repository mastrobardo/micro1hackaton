"""Baseline redaction path — the fair comparator for ``ghostc eval``.

Dumb keyword redaction: for every configured entity, replace each real spelling
(``real`` plus every ``match[].value`` of kind ``literal`` / ``identifier``) with
the canonical kebab ghost alias, or ``REDACTED`` for ``strategy: remove``. Plain
case-sensitive global string replace, longest spelling first. **No AST, no casing
engine, no compound-token splice, no graph, no mapping store** — the baseline is
deliberately not reversible; that is part of the point.

``compile`` beats this by exactly the spellings a keyword replace cannot see —
casing variants (``SKYROUTE_API_KEY``, ``bookingCore``, ``BOOKING_CORE_URL``),
compound tokens, prose re-casing. That gap, measured by ``ghostc eval``, is the
improvement the changelog records.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ghostc.audit import AuditLog, new_operation_id
from ghostc.compile import (
    _NullAudit,
    _boundary_internal,
    _excluded,
    _git_baseline,
    _rmtree,
)
from ghostc.config import load_config

_REMOVED = "REDACTED"


@dataclass
class BaselineResult:
    operation_id: str
    out: Path
    dry_run: bool
    files_scanned: int = 0
    files_changed: int = 0
    files_renamed: int = 0
    replacements: int = 0
    by_entity: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"operation:      {self.operation_id}",
            f"baseline repo:  {self.out}"
            + ("  (dry-run, not written)" if self.dry_run else ""),
            f"files scanned:  {self.files_scanned}",
            f"files changed:  {self.files_changed}",
            f"files renamed:  {self.files_renamed}",
            f"replacements:   {self.replacements}",
        ]
        for eid, n in sorted(self.by_entity.items()):
            lines.append(f"  {eid:24} x{n}")
        return "\n".join(lines)


def _entity_spellings(entity: dict) -> list[str]:
    out = [entity["real"]]
    for m in entity.get("match", []):
        if m.get("kind") in ("literal", "identifier"):
            out.append(m["value"])
    return [s for s in dict.fromkeys(out) if s]


def _replacement_table(cfg: dict) -> list[tuple[str, str, str]]:
    """(needle, replacement, entity_id), longest needle first.

    Longest-first so ``Northwind Airlines`` wins over ``Northwind``. Python's sort
    is stable, so equal-length needles keep config order — deterministic.
    """
    rows: list[tuple[str, str, str]] = []
    for e in cfg.get("entities", []):
        repl = _REMOVED if e["strategy"] == "remove" else e.get("ghost", "")
        for s in _entity_spellings(e):
            rows.append((s, repl, e["id"]))
    rows.sort(key=lambda r: -len(r[0]))
    return rows


def _redact(text: str, table: list[tuple[str, str, str]]) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    for needle, repl, eid in table:
        if not needle:
            continue
        n = text.count(needle)
        if n:
            text = text.replace(needle, repl)
            counts[eid] = counts.get(eid, 0) + n
    return text, counts


def _rename(rel: str, table: list[tuple[str, str, str]]) -> str:
    return "/".join(_redact(part, table)[0] for part in rel.split("/"))


def baseline_repo(repo: str, config_path: str = "privacy.yaml",
                  out: str = "workspace/baseline-ghost",
                  spec_path: str = "workspace/baseline-spec.md",
                  audit_path: str = "workspace/private/audit.jsonl",
                  dry_run: bool = False) -> BaselineResult:
    repo_p = Path(repo)
    if not repo_p.is_dir():
        raise SystemExit(f"repo not found: {repo}")
    out_p = Path(out)
    bad = _boundary_internal(out_p, spec=spec_path, audit=audit_path)
    if bad:
        raise SystemExit(
            f"refusing to run: {', '.join(bad)} path(s) resolve inside the baseline repo "
            f"({out_p}). Keep the audit under workspace/private/ and the spec a sibling."
        )

    cfg = load_config(config_path)
    exclusions = cfg.get("exclusions", [])
    table = _replacement_table(cfg)

    op = new_operation_id()
    audit = _NullAudit() if dry_run else AuditLog(audit_path, op)
    result = BaselineResult(operation_id=op, out=out_p, dry_run=dry_run)

    audit.emit("run.start", "baseline",
               details={"repo": str(repo_p), "out": str(out_p),
                        "config": config_path, "dry_run": dry_run})

    if not dry_run:
        if out_p.exists():
            _rmtree(out_p)
        out_p.mkdir(parents=True)

    for src in sorted(p for p in repo_p.rglob("*") if p.is_file()):
        rel = src.relative_to(repo_p).as_posix()
        if _excluded(rel, exclusions):
            continue
        result.files_scanned += 1

        try:
            text = src.read_text(encoding="utf-8")
            binary = False
        except UnicodeDecodeError:
            text, binary = "", True

        if binary:
            new_text = None
        else:
            new_text, counts = _redact(text, table)
            for eid, n in counts.items():
                result.by_entity[eid] = result.by_entity.get(eid, 0) + n
                result.replacements += n

        new_rel = _rename(rel, table)
        renamed = new_rel != rel
        if renamed:
            result.files_renamed += 1
        changed = (not binary) and new_text != text
        if changed:
            result.files_changed += 1

        audit.emit("baseline.file_scanned", "baseline", subject={"file": new_rel},
                   details={"changed": bool(changed), "renamed": renamed})

        if not dry_run:
            dst = out_p / new_rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if binary:
                dst.write_bytes(src.read_bytes())
            else:
                dst.write_text(new_text, encoding="utf-8")

    if not dry_run:
        _write_baseline_spec(Path(spec_path), result, op)
        _git_baseline(out_p)

    audit.emit("run.end", "baseline",
               details={"files_scanned": result.files_scanned,
                        "files_changed": result.files_changed,
                        "files_renamed": result.files_renamed,
                        "replacements": result.replacements})
    return result


def _write_baseline_spec(spec_p: Path, result: BaselineResult, op: str) -> None:
    rows = "\n".join(f"| `{eid}` | {n} |"
                     for eid, n in sorted(result.by_entity.items())) or "| _(none)_ | 0 |"
    spec = f"""# Baseline spec (keyword redaction)

Generated by `ghostc baseline` (operation `{op}`). **Not** a privacy-safe ghost —
this is the fair comparator for `ghostc eval`. Keyword `sed`-style redaction only:
casing variants and compound tokens leak straight through.

| entity | keyword replacements |
|--------|----------------------|
{rows}

Files scanned: {result.files_scanned} · changed: {result.files_changed} · renamed: {result.files_renamed}
"""
    spec_p.parent.mkdir(parents=True, exist_ok=True)
    spec_p.write_text(spec, encoding="utf-8")
