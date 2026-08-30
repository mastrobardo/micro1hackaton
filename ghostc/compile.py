"""Privacy Compiler — real repo -> privacy-safe ghost repo.

Deterministic. Node-scoped edits only (see :mod:`ghostc.parsers`). Never copies
``.git``. Writes the ghost tree, updates the boundary-internal mapping store,
emits a ghost spec, and one audit event per step.
"""
from __future__ import annotations

import copy
import fnmatch
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ghostc.audit import AuditLog, hash_real, new_operation_id
from ghostc.config import load_config
from ghostc.mapping import MappingStore
from ghostc.matching import build_matchers, transform_text
from ghostc.parsers import scoped
from ghostc.parsers import treesitter as ts

_KIND_STRATEGY = {
    "secret": "remove", "client": "synthetic_id", "person": "synthetic_id",
    "infra_identifier": "synthetic_id", "domain": "synthetic_endpoint",
}
_KIND_PREFIX = {
    "vendor": "vendor", "client": "client", "internal_service": "service",
    "infra_identifier": "id", "domain": "host", "secret": "secret", "person": "person",
}

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
    kept_specifiers: list[dict] = field(default_factory=list)  # {file,line,specifier,entity_id,source}

    def summary(self) -> str:
        lines = [
            f"operation:      {self.operation_id}",
            f"ghost repo:     {self.out}{'  (dry-run, not written)' if self.dry_run else ''}",
            f"files scanned:  {self.files_scanned}",
            f"files changed:  {self.files_changed}",
            f"files renamed:  {self.files_renamed}",
            f"entities:       {len(self.entities)}   occurrences: {self.hits}",
        ]
        if self.kept_specifiers:
            lines.append(f"import specifiers kept (not aliased — reveal a dependency): "
                         f"{len(self.kept_specifiers)}")
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
                 mapping_path: str = "workspace/private/mapping.json",
                 audit_path: str = "workspace/private/audit.jsonl",
                 spec_path: str = "workspace/ghost-spec.md",
                 candidates_path: str = "workspace/private/candidates.jsonl",
                 detect: bool = True,
                 dry_run: bool = False) -> CompileResult:
    repo_p = Path(repo)
    if not repo_p.is_dir():
        raise SystemExit(f"repo not found: {repo}")
    out_p = Path(out)
    _assert_outside_ghost(out_p, mapping=mapping_path, audit=audit_path, spec=spec_path,
                          candidates=candidates_path)
    cfg = load_config(config_path)
    exclusions = cfg.get("exclusions", [])

    scan = None
    if detect:
        from ghostc.detect.scan import scan_repo
        from ghostc.detect.settings import detection_settings

        det = detection_settings(cfg)
        scan = scan_repo(str(repo_p), cfg=cfg, settings=det)
        cfg, minted, blocked = _augment_with_auto_candidates(cfg, scan, det)
        if blocked:
            raise SystemExit(
                "BLOCKED: ghostc discover auto-proposed restricted entity(ies) "
                f"{', '.join(blocked)} (detection.auto_alias). Add them to "
                "privacy.yaml with `approved_by:` before compiling.")

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

    if scan is not None:
        if not dry_run:
            _write_candidates(Path(candidates_path), scan)
        for c in scan.candidates:
            if c.action != "review":
                continue
            subject = {"real_sha256": hash_real(c.surface)}
            if c.entity_id:
                subject["entity_id"] = c.entity_id
            audit.emit("compile.candidate_review", "compiler", level=c.level,
                       subject=subject, decision="review",
                       details={"score": c.score, "evidence": c.evidence,
                                "configured": c.entity_id is not None,
                                "occurrences": len(c.occurrences)})

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
                new_text, file_hits = scoped.compile_source(text, matchers, rel)
            else:
                new_text = text

        new_rel, path_hits = _rename_path(rel, matchers)
        renamed = new_rel != rel
        if renamed:
            result.files_renamed += 1

        for h in (*file_hits, *path_hits):
            meta = ent_meta[h.entity_id]
            if getattr(h, "kept", False):
                rec = {"file": new_rel, "line": h.line or 1, "specifier": h.real,
                       "entity_id": h.entity_id, "source": meta.get("source", "seed")}
                result.kept_specifiers.append(rec)
                audit.emit("compile.import_specifier_kept", "compiler", level=meta["level"],
                           subject={"entity_id": h.entity_id, "file": new_rel,
                                    "line": h.line or 1},
                           details={"source": rec["source"]})
                continue
            roll = result.entities.get(h.entity_id)
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

    seed_kept = sorted({k["specifier"] for k in result.kept_specifiers
                        if k["source"] == "seed"})
    if seed_kept:
        import sys
        print("WARNING: kept import specifier(s) contain a SEED entity name and were "
              "NOT aliased (a renamed dependency does not resolve in the ghost): "
              + ", ".join(seed_kept)
              + "\n  `ghostc verify` will BLOCK this ghost. Set `rewrite_imports: true` "
              "on the entity, or add the file to `exclusions`.", file=sys.stderr)

    if not dry_run:
        _write_ghost_spec(Path(spec_path), result, op)
        _assert_ghost_tree_is_clean(out_p, mapping=mapping_path, audit=audit_path,
                                    spec=spec_path, candidates=candidates_path)
        _git_baseline(out_p)

    audit.emit("run.end", "compiler",
               details={"files_scanned": result.files_scanned,
                        "files_changed": result.files_changed,
                        "files_renamed": result.files_renamed,
                        "entities": len(result.entities), "occurrences": result.hits})
    return result


_TOKENISH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@-]*$")


def _write_candidates(path: Path, scan) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for c in scan.candidates:
            fh.write(json.dumps(c.to_dict(), sort_keys=True) + "\n")


def _next_alias(taken: set[str], prefix: str) -> str:
    for i in range(26):
        cand = f"{prefix}-{chr(ord('a') + i)}"
        if cand not in taken:
            return cand
    n = 1
    while f"{prefix}-{n}" in taken:
        n += 1
    return f"{prefix}-{n}"


def _augment_with_auto_candidates(cfg: dict, scan, settings
                                  ) -> tuple[dict, list[dict], list[str]]:
    """With ``detection.auto_alias`` on, turn every unconfigured ``auto`` candidate
    into a synthetic ``source: discovered`` entity so the normal matcher pipeline
    neutralises it. Restricted proposals are reported as *blocked* (human gate)."""
    if not settings.auto_alias:
        return cfg, [], []
    cfg = copy.deepcopy(cfg)
    taken = {e.get("ghost", "") for e in cfg.get("entities", [])}
    ids = {e["id"] for e in cfg.get("entities", [])}
    minted: list[dict] = []
    blocked: list[str] = []

    for c in scan.candidates:
        if c.entity_id is not None or c.action != "auto":
            continue
        kind = c.kind or "vendor"
        strategy = _KIND_STRATEGY.get(kind, "semantic_alias")
        ghost = "" if strategy == "remove" else _next_alias(taken, _KIND_PREFIX.get(kind, "vendor"))
        taken.add(ghost)
        base = "disc_" + re.sub(r"[^a-z0-9]+", "_", c.surface.lower()).strip("_")[:28]
        eid = base
        n = 2
        while eid in ids:
            eid = f"{base}_{n}"
            n += 1
        ids.add(eid)

        match = []
        for a in dict.fromkeys([*c.aliases, *[o.surface for o in c.occurrences]]):
            if a == c.surface or not a:
                continue
            m_kind = "identifier" if _TOKENISH.match(a) and " " not in a else "literal"
            match.append({"kind": m_kind, "value": a})
        ent = {
            "id": eid, "real": c.surface, "kind": kind,
            "level": c.level or "confidential", "strategy": strategy,
            "ghost": ghost, "source": "discovered",
            "note": f"auto-proposed by ghostc discover (score {c.score:.2f})",
        }
        if match:
            ent["match"] = match[:24]
        cfg["entities"].append(ent)
        minted.append(ent)
        if ent["level"] == "restricted" and not ent.get("approved_by"):
            blocked.append(eid)
    return cfg, minted, blocked


def _dedup_occ(occ: list[dict]) -> list[dict]:
    seen, out = set(), []
    for o in sorted(occ, key=lambda o: (o["file"], o["line"])):
        key = (o["file"], o["line"])
        if key in seen:
            continue
        seen.add(key)
        out.append(o)
    return out


def _boundary_internal(out_p: Path, **named: str) -> list[str]:
    """Names of artifact paths that resolve to somewhere inside the ghost repo."""
    root = out_p.resolve()
    return [name for name, p in named.items() if Path(p).resolve().is_relative_to(root)]


def _assert_outside_ghost(out_p: Path, **named: str) -> None:
    bad = _boundary_internal(out_p, **named)
    if bad:
        raise SystemExit(
            f"refusing to run: {', '.join(bad)} path(s) resolve inside the ghost repo "
            f"({out_p}). The ghost tree must mirror the real repo and nothing else — "
            "keep the mapping/audit under workspace/private/ and the spec a sibling of the ghost."
        )


def _assert_ghost_tree_is_clean(out_p: Path, **named: str) -> None:
    """Post-write guard: none of our generated artifacts landed inside the ghost tree."""
    root = out_p.resolve()
    leaked = sorted(
        str(Path(p).resolve().relative_to(root))
        for p in named.values()
        if Path(p).resolve().is_relative_to(root) and Path(p).exists()
    )
    if leaked:
        raise SystemExit(f"boundary violation: generated metadata inside the ghost repo: {leaked}")


def _write_ghost_spec(spec_p: Path, result: CompileResult, op: str) -> None:
    rows = "\n".join(
        f"| `{r.entity_id}` | {r.kind} | {r.level} | `{r.ghost or '<removed>'}` | {len(r.occurrences)} |"
        for r in sorted(result.entities.values(), key=lambda r: (r.level, r.entity_id))
    )
    spec = f"""# Ghost spec

Generated by `ghostc compile` (operation `{op}`). Safe to share with the external
coding agent. Reveals **no `real → ghost` mapping** — only the aliases it will see
(plus, if any, the un-aliased dependency names already present in the ghost source).

| entity | kind | level | ghost alias | occurrences |
|--------|------|-------|-------------|-------------|
{rows}

Files scanned: {result.files_scanned} · changed: {result.files_changed} · renamed: {result.files_renamed}
"""
    if result.kept_specifiers:
        by_spec: dict[str, int] = {}
        for k in result.kept_specifiers:
            by_spec[k["specifier"]] = by_spec.get(k["specifier"], 0) + 1
        rows2 = "\n".join(f"| `{s}` | {n} |" for s, n in sorted(by_spec.items()))
        spec += f"""
## Dependency names left un-aliased

These `import` / `require` specifiers matched a sensitive entity but were **kept**
verbatim — a renamed package does not resolve in the ghost environment. They reveal
a third-party dependency relationship; a human reviewer decides whether that is
acceptable for this ghost.

| specifier | occurrences |
|-----------|-------------|
{rows2}
"""
    spec_p.parent.mkdir(parents=True, exist_ok=True)
    spec_p.write_text(spec, encoding="utf-8")


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
