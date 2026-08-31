"""``post-receive`` hook runner on the ghost bare origin (``../ghostc-demo/ghost.git``).

Installed by :func:`client_agent.localgit.ensure_ghost_origin`. Git runs this in
the bare repo with the pushed ref lines (``<old> <new> <ref>``) on stdin. For every
``refs/heads/ghostc/task/<id>`` update it runs ``consultancy-agent start`` against
the persistent consultancy checkout.

Invocation: ``python -m consultancy_agent._hook <backend> <consultancy_repo>``. The
command line carries **no** mapping-store or client-repo path — the boundary is on
this wire. ``GHOSTC_NO_HOOK=1`` is set for the child so the consultancy's own
push-back does not re-trigger the hook.

Boundary: no imports from ``bridge`` / ``ghostc`` / ``client_agent`` — stdlib only.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_TASK_PREFIX = "refs/heads/ghostc/task/"


def main() -> int:
    backend = sys.argv[1] if len(sys.argv) > 1 else "stub"
    repo = Path(sys.argv[2] if len(sys.argv) > 2 else "../ghost-consultancy").resolve()

    # Git exports GIT_DIR / GIT_QUARANTINE_PATH / ... into the hook environment;
    # they would derail the child agent's own git calls.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GHOSTC_NO_HOOK"] = "1"

    rc = 0
    for line in sys.stdin.read().splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        _old, _new, ref = parts
        if not ref.startswith(_TASK_PREFIX):
            continue
        branch = ref[len("refs/heads/"):]
        proc = subprocess.run(
            [sys.executable, "-m", "consultancy_agent", "start",
             "--repo", str(repo), "--branch", branch, "--backend", backend],
            env=env, capture_output=True, text=True)
        out = f"exit={proc.returncode}\n{proc.stdout}{proc.stderr}"
        # A post-receive hook's stderr is swallowed by a successful `git push`, so
        # this file beside the checkout is how the client sees what happened.
        (repo.parent / f"{branch.replace('/', '_')}.consultancy.log").write_text(
            out, encoding="utf-8")
        sys.stderr.write(proc.stdout + proc.stderr)
        rc = rc or proc.returncode
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
