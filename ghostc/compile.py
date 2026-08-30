"""Privacy Compiler — real repo -> privacy-safe ghost repo.

Deterministic. Node-scoped edits only (see :mod:`ghostc.parsers`). Never copies
``.git``. Writes the ghost tree, updates the boundary-internal mapping store,
emits a ghost spec, and one audit event per step.
"""
from __future__ import annotations

import fnmatch
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ghostc.audit import AuditLog, hash_real, new_operation_id
from ghostc.config import load_config
from ghostc.mapping import MappingStore
from ghostc.matching import build_matchers, transform_text
from ghostc.parsers import scoped
from ghostc.parsers import treesitter as ts

_ALWAYS_SKIP_DIRS = {".git"}


@dataclass
class EntityRoll:
    entity_id: str
    kind: str
    level: str
    strategy: str
    ghost: str
    real: str
    occurrences: list[dict] = field(default_factory=list)   # {file, line}
    reused: bool = False


@dataclass
class CompileResult:
    operation_id: str
    out: Path
    dry_run: bool
    files_scanned: int = 0
    files_changed: int = 0
    files_renamed: int = 0
    hits: int = 0
    entities: dict[str, EntityRoll] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"operation:      {self.operation_id}",
            f"ghost repo:     {self.out}{'  (dry-run, not written)' if self.dry_run else ''}",
            f"files scanned:  {self.files_scanned}",
            f"files changed:  {self.files_changed}",
            f"files renamed:  {self.files_renamed}",
            f"entities:       {len(self.entities)}   occurrences: {self.hits}",
        ]
        for r in sorted(self.entities.values(), key=lambda r: r.entity_id):
            tag = "reuse" if r.reused else "new  "
            lines.append(f"  [{tag}] {r.entity_id:24} {r.level:12} {r.ghost or '<removed>':16} "
                         f"x{len(r.occurrences)}")
        return "\n".join(lines)


class _NullAudit:
    operation_id = "dry-run"

    def emit(self, *a, **k):   # noqa: D401,ANN001
        return {}


def _excluded(rel: str, patterns: list[str]) -> bool:
    parts = rel.split("/")
    if _ALWAYS_SKIP_DIRS.intersection(parts):
        return True
    for pat in patterns:
        if fnmatch.fnmatch(rel, pat):
            return True
        core = pat.strip("*/")
        if "/" not in core and (core in parts or fnmatch.fnmatch(parts[-1], core)):
            return True
    return False


def _rename_path(rel: str, matchers) -> tuple[str, list]:
    out_parts, hits = [], []
    for part in rel.split("/"):
        new_part, part_hits = transform_text(part, "filename", matchers)
        out_parts.append(new_part)
        for h in part_hits:
            h.line = 0
        hits.extend(part_hits)
    return "/".join(out_parts), hits


def compile_repo(repo: str, config_path: str = "privacy.yaml",
                 out: str = "workspace/ghost",
                 mapping_path: str = "workspace/mapping.json",
                 audit_path: str = "workspace/audit.jsonl",
                 dry_run: bool = False) -> CompileResult:
    repo_p = Path(repo)
    if not repo_p.is_dir():
        raise SystemExit(f"repo not found: {repo}")
    out_p = Path(out)
    cfg = load_config(config_path)
    exclusions = cfg.get("exclusions", [])
    matchers = build_matchers(cfg)
    ent_meta = {e["id"]: e for e in cfg.get("entities", [])}

    op = new_operation_id()
    audit = _NullAudit() if dry_run else AuditLog(audit_path, op)
    result = CompileResult(operation_id=op, out=out_p, dry_run=dry_run)

    store = None if dry_run else MappingStore(mapping_path, cfg.get("mapping_version", 1))
    preexisting = set()
    if store is not None:
        preexisting = {e["entity_id"] for e in store.data["entries"]}

    audit.emit("run.start", "compiler", details={"repo": str(repo_p), "out": str(out_p),
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

        file_hits = []
        if binary:
            new_text = None
        else:
            lang = ts.language_for(rel)
            if lang:
                new_text, file_hits = ts.compile_source(text, matchers, lang)
            elif scoped.handles(rel):
                new_text, file_hits = scoped.compile_source(text, matchers)
            else:
                new_text = text

        new_rel, path_hits = _rename_path(rel, matchers)
        renamed = new_rel != rel
        if renamed:
            result.files_renamed += 1

        for h in (*file_hits, *path_hits):
            roll = result.entities.get(h.entity_id)
            meta = ent_meta[h.entity_id]
            if roll is None:
                roll = EntityRoll(h.entity_id, meta["kind"], meta["level"],
                                  meta["strategy"], meta.get("ghost", ""), meta["real"])
                result.entities[h.entity_id] = roll
                audit.emit("compile.entity_detected", "compiler", level=meta["level"],
                           subject={"entity_id": h.entity_id,
                                    "real_sha256": hash_real(meta["real"])})
            occ = {"file": new_rel, "line": h.line} if h.line else {"file": new_rel, "line": 1}
            roll.occurrences.append(occ)
            result.hits += 1

        changed = (not binary) and new_text != text
        if changed:
            result.files_changed += 1
        audit.emit("compile.file_scanned", "compiler",
                   subject={"file": new_rel},
                   details={"changed": bool(changed), "renamed": renamed,
                            "occurrences": len(file_hits) + len(path_hits)})
        if changed:
            audit.emit("compile.transformed", "compiler", subject={"file": new_rel},
                       details={"occurrences": len(file_hits)})

        if not dry_run:
            dst = out_p / new_rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if binary:
                dst.write_bytes(src.read_bytes())
            else:
                dst.write_text(new_text, encoding="utf-8")

    # -- mapping store ------------------------------------------------------
    if store is not None:
        for roll in result.entities.values():
            reused = roll.entity_id in preexisting
            roll.reused = reused
            store.upsert(entity_id=roll.entity_id, real=roll.real, ghost=roll.ghost,
                         kind=roll.kind, level=roll.level, strategy=roll.strategy)
            entry = store.by_entity_id(roll.entity_id)
            entry["occurrences"] = _dedup_occ(roll.occurrences)
            audit.emit("compile.mapping_reused" if reused else "compile.mapping_created",
                       "compiler", level=roll.level,
                       subject={"entity_id": roll.entity_id,
                                "mapping_version": store.data["mapping_version"]})
        store.save()

    if not dry_run:
        _write_ghost_spec(out_p, result, op)
        _git_baseline(out_p)

    audit.emit("run.end", "compiler",
               details={"files_scanned": result.files_scanned,
                        "files_changed": result.files_changed,
                        "files_renamed": result.files_renamed,
                        "entities": len(result.entities), "occurrences": result.hits})
    return result


def _dedup_occ(occ: list[dict]) -> list[dict]:
    seen, out = set(), []
    for o in sorted(occ, key=lambda o: (o["file"], o["line"])):
        key = (o["file"], o["line"])
        if key in seen:
            continue
        seen.add(key)
        out.append(o)
    return out


def _write_ghost_spec(out_p: Path, result: CompileResult, op: str) -> None:
    rows = "\n".join(
        f"| `{r.entity_id}` | {r.kind} | {r.level} | `{r.ghost or '<removed>'}` | {len(r.occurrences)} |"
        for r in sorted(result.entities.values(), key=lambda r: (r.level, r.entity_id))
    )
    spec = f"""# Ghost spec

Generated by `ghostc compile` (operation `{op}`). Safe to share with the external
coding agent. Contains **no real values** — only the aliases it will see.

| entity | kind | level | ghost alias | occurrences |
|--------|------|-------|-------------|-------------|
{rows}

Files scanned: {result.files_scanned} · changed: {result.files_changed} · renamed: {result.files_renamed}
"""
    (out_p.parent / "ghost-spec.md").write_text(spec, encoding="utf-8")


def _git_baseline(out_p: Path) -> None:
    env = {"GIT_AUTHOR_NAME": "ghostc", "GIT_AUTHOR_EMAIL": "ghost@local",
           "GIT_COMMITTER_NAME": "ghostc", "GIT_COMMITTER_EMAIL": "ghost@local"}
    import os
    run_env = {**os.environ, **env}
    for args in (["init", "-q"], ["add", "-A"],
                 ["commit", "-q", "-m", "ghost baseline (ghostc compile)"]):
        subprocess.run(["git", *args], cwd=out_p, env=run_env,
                       check=False, capture_output=True)


def _rmtree(path: Path) -> None:
    import shutil
    shutil.rmtree(path)
