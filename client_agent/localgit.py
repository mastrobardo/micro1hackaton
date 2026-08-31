"""Plain ``git`` against the real demo repos.

The reduced, hook-triggered flow (``client-agent start``) does its handoff on the
**actual** ghost repo plus a bare "origin" beside it — not a synthesized forge.
Everything you can inspect afterwards is a normal branch on a normal repo:

    ../ghostc-demo/
      ghost.git/           bare origin (git-server stand-in) + post-receive hook
      ghost/               the company ghost repo (``ghostc compile`` output)
      ghost-consultancy/   the consultancy's own persistent clone of ghost.git

``ghost/`` and ``ghost-consultancy/`` commit under **different git identities**, so
``git log`` on the task branch shows two actors: the client opens the task, the
external dev implements it.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

# handoff commits (the sanitized TASK.md) — the company side
CLIENT_IDENT = ["-c", "user.name=ghostc-client", "-c", "user.email=client@ghostc.local"]


def git(cwd: str | Path, *args: str, ident: list[str] | None = None,
        check: bool = True) -> str:
    """Run ``git -C <cwd> [ident] <args>``. Returns stripped stdout; raises on failure.

    ``GIT_*`` is stripped from the environment so a caller invoked from inside a
    hook (which exports ``GIT_DIR`` etc.) does not derail the command.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    cmd = ["git", "-C", str(cwd), *(ident or []), *args]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if check and r.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed in {cwd}:\n{(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def default_branch(repo: Path) -> str:
    head = git(repo, "rev-parse", "--abbrev-ref", "HEAD", check=False)
    return head or "main"


def _install_post_receive(bare: Path, consultancy_repo: Path, *,
                          hook_backend: str, python: str, metrics_file: str = "") -> None:
    hook = Path(bare) / "hooks" / "post-receive"
    hook.parent.mkdir(parents=True, exist_ok=True)
    # Export GHOSTC_METRICS_FILE so the consultancy agent (spawned by _hook) appends
    # its own run row to the SAME sink as the client — see bridge/metrics.py.
    metrics_line = (f'GHOSTC_METRICS_FILE="{metrics_file}"; export GHOSTC_METRICS_FILE\n'
                    if metrics_file else "")
    hook.write_text(
        "#!/bin/sh\n"
        '[ -n "$GHOSTC_NO_HOOK" ] && exit 0\n'
        f"{metrics_line}"
        f'exec "{python}" -m consultancy_agent._hook '
        f'"{hook_backend}" "{Path(consultancy_repo).resolve()}"\n',
        encoding="utf-8")
    hook.chmod(0o755)


def ensure_ghost_origin(ghost_repo: Path, consultancy_repo: Path, *,
                        hook_backend: str, python: str, metrics_file: str = "") -> Path:
    """Idempotent local "git server" setup. Returns the bare-origin path.

    * a bare ``<ghost_repo>.git`` beside the ghost repo, wired as its ``origin``;
    * a ``post-receive`` hook on it that runs the consultancy agent;
    * a persistent consultancy clone at *consultancy_repo* (``fetch`` if it exists).
    """
    ghost_repo = Path(ghost_repo).resolve()
    consultancy_repo = Path(consultancy_repo).resolve()
    if not (ghost_repo / ".git").is_dir():
        raise SystemExit(f"{ghost_repo} is not a git repo — run `ghostc compile` first")

    if "origin" in git(ghost_repo, "remote").split():
        bare = Path(git(ghost_repo, "remote", "get-url", "origin"))
    else:
        bare = ghost_repo.parent / f"{ghost_repo.name}.git"
        if not bare.exists():
            bare.mkdir(parents=True)
            git(bare.parent, "init", "--bare", "-q", "-b", "main", bare.name)
        git(ghost_repo, "remote", "add", "origin", str(bare))
        git(ghost_repo, "push", "-q", "-u", "origin", default_branch(ghost_repo))

    _install_post_receive(bare, consultancy_repo, hook_backend=hook_backend,
                          python=python, metrics_file=metrics_file)

    if (consultancy_repo / ".git").is_dir():
        git(consultancy_repo, "fetch", "-q", "origin")
    else:
        consultancy_repo.parent.mkdir(parents=True, exist_ok=True)
        git(consultancy_repo.parent, "clone", "-q", str(bare), consultancy_repo.name)
    return bare
