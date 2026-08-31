"""Append-only per-run metrics sink (JSONL) — one row per agent run.

Every agent run (``client-agent start``, ``client-agent open-real-pr``, the
consultancy agent under the post-receive hook) appends one JSON object here. A
dashboard / GitHub Action step consumes ``metrics/agent-runs.jsonl`` the way a CI
job consumes a test report or a coverage/sonar report — see ``metrics/README.md``.

Boundary-neutral: **stdlib only**, so both ``client_agent`` and
``consultancy_agent`` may import it (``consultancy_agent`` may import ``bridge``
only — ``tests/test_boundary.py``).

Path resolution, most specific first:

1. the ``path=`` argument to :func:`record_run`;
2. ``$GHOSTC_METRICS_FILE`` (the post-receive hook exports this so the consultancy
   writes into the same sink as the client);
3. ``metrics/agent-runs.jsonl`` relative to the process cwd.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
_DEFAULT = "metrics/agent-runs.jsonl"


def metrics_path(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Resolve the metrics-file path (does not touch the filesystem)."""
    return Path(explicit or os.environ.get("GHOSTC_METRICS_FILE") or _DEFAULT)


def record_run(row: dict, *, path: str | os.PathLike[str] | None = None) -> Path:
    """Append one run row as a single JSON line. Returns the file written.

    ``schema`` and ``ts`` (UTC ISO-8601) are added automatically; anything already
    in *row* wins. The write is a plain append — concurrent runs interleave whole
    lines, which is all a JSONL consumer needs.
    """
    p = metrics_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    entry = {"schema": SCHEMA, "ts": datetime.now(timezone.utc).isoformat(), **row}
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True, default=str) + "\n")
    return p
