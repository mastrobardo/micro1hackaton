"""Per-step agent trajectory sink (JSONL) — one line per tool call.

The metrics sink (``bridge/metrics.py``) records one row per *run*: the outcome,
the counts, the wall-clock. That is the right grain for a dashboard and the wrong
grain for hackathon deliverable 04, which asks to see **what the agent did and how
its tools responded** — the step-by-step path from the instructions to the result.

This module is that finer grain. ``scripts/make-trajectories.py`` renders it.

Boundary-neutral: **stdlib only**, so ``consultancy_agent`` may import it
(``consultancy_agent`` may import ``bridge`` only — ``tests/test_boundary.py``).

Path resolution, most specific first:

1. the ``path=`` argument to :func:`open_trajectory`;
2. ``$GHOSTC_TRAJECTORY_DIR``;
3. a ``trajectories/`` directory beside the metrics sink, so the hook's
   ``GHOSTC_METRICS_FILE`` export puts both in the same place.

**Never inside the repo under work.** The consultancy agent runs ``git add -A`` on
its checkout; a trajectory written inside it would be committed and pushed back
across the boundary. :func:`open_trajectory` raises rather than let that happen.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from bridge.metrics import metrics_path

SCHEMA = 1
_MAX_FIELD = 600          # truncate tool args / observations; this is a trace, not a mirror


def trajectory_dir(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Resolve the trajectory directory (does not touch the filesystem)."""
    if explicit:
        return Path(explicit)
    env = os.environ.get("GHOSTC_TRAJECTORY_DIR")
    if env:
        return Path(env)
    return metrics_path().parent / "trajectories"


def _clip(value: object) -> object:
    """Bound a field's size. Tool observations can be whole files."""
    if isinstance(value, str) and len(value) > _MAX_FIELD:
        return value[:_MAX_FIELD] + f"… [+{len(value) - _MAX_FIELD} chars]"
    if isinstance(value, dict):
        return {k: _clip(v) for k, v in value.items()}
    return value


class Trajectory:
    """Append-only JSONL writer for one agent run's steps."""

    def __init__(self, path: Path, meta: dict) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write({"kind": "meta", **meta})

    def _write(self, row: dict) -> None:
        entry = {"schema": SCHEMA, "ts": datetime.now(timezone.utc).isoformat(), **row}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True, default=str) + "\n")

    def step(self, n: int, *, tool: str, args: dict | None = None,
             observation: str = "", **extra: object) -> None:
        """One tool call and how the tool responded."""
        self._write({"kind": "step", "step": n, "tool": tool,
                     "args": _clip(args or {}), "observation": _clip(observation),
                     **{k: _clip(v) for k, v in extra.items()}})

    def note(self, n: int, text: str, **extra: object) -> None:
        """Feedback sent back to the model that was not a tool result — a nudge,
        a parse complaint. This is the row that shows what shaped the next step."""
        self._write({"kind": "note", "step": n, "text": _clip(text),
                     **{k: _clip(v) for k, v in extra.items()}})

    def end(self, **fields: object) -> None:
        self._write({"kind": "end", **{k: _clip(v) for k, v in fields.items()}})


def open_trajectory(name: str, meta: dict, *,
                    path: str | os.PathLike[str] | None = None,
                    forbid_inside: str | os.PathLike[str] | None = None) -> Trajectory:
    """Open the sink for a run. *name* becomes the filename stem.

    Pass *forbid_inside* (the repo the agent is editing) and this refuses to write
    anywhere under it — that file would be swept up by ``git add -A``.
    """
    target = trajectory_dir(path) / f"{_slug(name)}.jsonl"
    if forbid_inside:
        root = Path(forbid_inside).resolve()
        if root == target.resolve().parent or root in target.resolve().parents:
            raise ValueError(
                f"refusing to write a trajectory inside the working repo ({root}) — "
                "it would be committed and pushed. Set $GHOSTC_TRAJECTORY_DIR."
            )
    return Trajectory(target, meta)


def _slug(name: str) -> str:
    keep = [c if (c.isalnum() or c in "-_") else "-" for c in name]
    return "".join(keep).strip("-") or "run"
