"""The consultancy coding agent — Phase C (real Claude tool-loop) lands here.

Runs OUTSIDE the company trust boundary. Its whole world is a ghost repo checkout
plus ``TASK.md``. It must never see the mapping store, the real repo, or any
credential — so this module does not import ``ghostc`` (enforced by
``tests/test_boundary.py``) and :func:`assert_boundary_clean` actively refuses to
start if boundary-crossing artefacts are reachable from the work dir.

Phase C will add: a Claude tool-loop (``list_files`` / ``read_file`` /
``write_file`` / ``run_tests``) over the checkout via :mod:`bridge.llm`, then a
commit + ghost PR via :mod:`bridge.forge`. For now :func:`run_consultancy` in
:mod:`consultancy_agent.sim` is the deterministic stand-in.
"""
from __future__ import annotations

from pathlib import Path

# byte-signatures of a ghostc mapping store — sniffed WITHOUT importing ghostc
_MAPPING_MARKERS = ('"real_sha256"', '"mapping_version"', '"frozen"')


class BoundaryViolation(RuntimeError):
    """A boundary-crossing artefact was reachable from the consultancy work dir."""


def assert_boundary_clean(workdir: str | Path) -> None:
    """Refuse to run if a mapping-shaped file or a real-repo marker is reachable."""
    root = Path(workdir)
    offenders: list[str] = []
    for p in root.rglob("*"):
        if not p.is_file() or ".git" in p.parts:
            continue
        name = p.name.lower()
        if name in {"mapping.json", "privacy.yaml", "privacy.autoalias.yaml"}:
            offenders.append(p.relative_to(root).as_posix())
            continue
        try:
            head = p.read_text(encoding="utf-8", errors="ignore")[:4096]
        except OSError:
            continue
        if any(m in head for m in _MAPPING_MARKERS):
            offenders.append(p.relative_to(root).as_posix())
    if offenders:
        raise BoundaryViolation(
            "consultancy agent will not run — boundary-crossing files reachable: "
            + ", ".join(sorted(offenders)))


def run_consultancy(*args, **kwargs) -> str:  # pragma: no cover - Phase C
    raise NotImplementedError(
        "the real Claude consultancy agent lands in Phase C; "
        "use consultancy_agent.sim.run_consultancy for now")
