"""Verification gate — fail closed before the ghost crosses to an external agent.

Three checks:

* **leak_scan**   — no real sensitive value (from the mapping store, plus every
                    seed spelling in ``privacy.yaml``) occurs in the ghost tree.
* **mapping_leak** — no mapping-shaped file (real values / ``real_sha256``) is
                    present anywhere under the ghost.
* **build**       — ``yarn lint`` passes. Best-effort: ``skipped`` when the
                    toolchain/deps are absent, unless ``require_build`` is set.

``ok`` is true only when no check failed.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ghostc.scanning import anchored_scan, iter_text_files, looks_like_mapping


@dataclass
class LeakHit:
    file: str
    line: int
    entity_id: str
    spelling: str


@dataclass
class Check:
    name: str
    status: str                       # "pass" | "fail" | "skipped"
    detail: str = ""
    leaks: list[LeakHit] = field(default_factory=list)
    files: list[str] = field(default_factory=list)


@dataclass
class VerifyResult:
    ghost: Path
    checks: list[Check]

    @property
    def ok(self) -> bool:
        return all(c.status != "fail" for c in self.checks)

    @property
    def reasons(self) -> list[str]:
        return [f"{c.name}: {c.detail}" for c in self.checks if c.status == "fail"]

    def summary(self) -> str:
        head = f"{'PASS' if self.ok else 'BLOCK'}  {self.ghost}"
        lines = [head]
        for c in self.checks:
            mark = {"pass": "ok  ", "fail": "FAIL", "skipped": "skip"}[c.status]
            lines.append(f"  [{mark}] {c.name}" + (f" — {c.detail}" if c.detail else ""))
            for h in c.leaks[:20]:
                lines.append(f"         {h.file}:{h.line}  {h.entity_id} ({h.spelling!r})")
            for f in c.files[:20]:
                lines.append(f"         {f}")
        return "\n".join(lines)


def _entity_spellings(entity: dict) -> list[str]:
    out = [entity["real"]]
    for m in entity.get("match", []):
        if m.get("kind") in ("literal", "identifier"):
            out.append(m["value"])
    return [s for s in out if s]


def _needle_owners(mapping_path: Path, config_path: Path | None) -> dict[str, str]:
    """spelling -> entity_id, from the mapping store and (if present) privacy.yaml."""
    import json

    owners: dict[str, str] = {}
    doc = json.loads(mapping_path.read_text(encoding="utf-8"))
    for e in doc.get("entries", []):
        if e.get("real"):
            owners.setdefault(e["real"], e["entity_id"])
    if config_path and Path(config_path).exists():
        from ghostc.config import load_config

        for e in load_config(config_path).get("entities", []):
            for s in _entity_spellings(e):
                owners.setdefault(s, e["id"])
    return owners


def _leak_scan(ghost: Path, owners: dict[str, str]) -> Check:
    hits: list[LeakHit] = []
    for rel, text in iter_text_files(ghost):
        for h in anchored_scan(text, owners):
            hits.append(LeakHit(rel, text.count("\n", 0, h.start) + 1,
                                owners[h.text], h.text))
    if hits:
        n = len({(h.file, h.entity_id) for h in hits})
        return Check("leak_scan", "fail",
                     f"{len(hits)} real value occurrence(s) across {n} (file, entity) pair(s)",
                     leaks=hits)
    return Check("leak_scan", "pass", "no real value present in the ghost tree")


def _mapping_leak_scan(ghost: Path) -> Check:
    found = [rel for rel, text in iter_text_files(ghost) if looks_like_mapping(text)]
    if found:
        return Check("mapping_leak", "fail",
                     f"{len(found)} mapping-shaped file(s) inside the ghost", files=found)
    return Check("mapping_leak", "pass", "no mapping store material in the ghost tree")


def _build_gate(ghost: Path, require_build: bool) -> Check:
    if not shutil.which("yarn") or not (ghost / "node_modules").is_dir():
        status = "fail" if require_build else "skipped"
        return Check("build", status, "yarn / node_modules unavailable (yarn lint not run)")
    proc = subprocess.run(["yarn", "lint"], cwd=ghost, capture_output=True, text=True)
    if proc.returncode == 0:
        return Check("build", "pass", "yarn lint clean")
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-8:]
    return Check("build", "fail", "yarn lint failed:\n         " + "\n         ".join(tail))


def verify_ghost(ghost: str | Path, mapping_path: str | Path, *,
                 config_path: str | Path | None = "privacy.yaml",
                 require_build: bool = False) -> VerifyResult:
    ghost = Path(ghost)
    if not ghost.is_dir():
        return VerifyResult(ghost, [Check("input", "fail", f"ghost repo not found: {ghost}")])
    mapping_path = Path(mapping_path)
    if not mapping_path.exists():
        return VerifyResult(ghost, [Check("input", "fail",
                                          f"mapping store not found: {mapping_path}")])
    try:
        owners = _needle_owners(mapping_path, Path(config_path) if config_path else None)
        checks = [
            _leak_scan(ghost, owners),
            _mapping_leak_scan(ghost),
            _build_gate(ghost, require_build),
        ]
    except Exception as exc:  # fail closed on any verifier error
        return VerifyResult(ghost, [Check("verify", "fail", f"verifier error: {exc!r}")])
    return VerifyResult(ghost, checks)
