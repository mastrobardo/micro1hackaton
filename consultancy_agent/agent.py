"""The consultancy coding agent — the external side of the handoff.

Runs OUTSIDE the company trust boundary. Its whole world is a checkout of the
**ghost** repo on a feature branch whose root holds ``TASK.md``. It never sees the
mapping store, the real repo, or any client credential.

**The boundary is enforced by infrastructure, not by a self-check.** In real life
an external coding agent (Codex, Copilot, Claude) does not audit its own sandbox —
so this module deliberately carries no runtime "am I isolated?" guard. Isolation
comes from:

* git auth scoped to the ghost remote only (it cannot fetch the real repo);
* a separate process / container that is simply never handed a mapping path or a
  ``CLIENT_*`` credential (Phase E gives it only the ``CONSULTANCY_*`` env vars);
* the static import boundary — this package may not import ``ghostc`` /
  ``client_agent`` (``tests/test_boundary.py``).

**Trigger.** Started by a git hook, not an in-process call: the client pushes a
ghost feature branch with ``TASK.md`` committed at the root; a ``post-receive``
hook on the ghost bare repo (``bridge.forge.install_consultancy_hook``) runs
``consultancy-agent start`` against that branch. It implements ``TASK.md``,
commits **on the same branch**, and pushes — **no PR**.

Two backends, selected by :func:`bridge.llm.get_llm`:

* ``--backend claude`` / ``auto`` with ``CONSULTANCY_ANTHROPIC_API_KEY`` (or bare
  ``ANTHROPIC_API_KEY``) set — a hand-rolled loop over the checkout: Claude emits
  one JSON action per turn (``list_files`` / ``read_file`` / ``write_file`` /
  ``run_tests`` / ``run_build``), we run it and feed the observation back. Traces
  land in the ``ghostc-consultancy`` LangSmith project.
* ``--backend stub`` / no key — a deterministic scripted fallback, so the graph
  tests and an offline demo run reproducibly.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from bridge.env import load_env
from bridge.llm import StubLLM, configure_langsmith, get_llm
from bridge.metrics import record_run
from bridge.trace import traceable

_MAX_STEPS = 24
_MAX_OBS_CHARS = 4000

# The consultancy commits as its own actor — a different person from the client's
# `ghostc-client` handoff commit, so `git log` on the task branch shows two parties.
# Override per engagement with CONSULTANCY_GIT_NAME / CONSULTANCY_GIT_EMAIL.
_DEFAULT_GIT_NAME = "Consultancy Dev"
_DEFAULT_GIT_EMAIL = "dev@consultancy.example"

_SYSTEM = """You are an autonomous coding agent working inside a single git checkout.
You are implementing the change described in TASK.md. Work only inside the repo.

Each turn, reply with ONE json object and nothing else:
  {"tool": "list_files", "args": {"dir": "."}}
  {"tool": "read_file", "args": {"path": "src/config.js"}}
  {"tool": "write_file", "args": {"path": "src/x.js", "content": "..."}}
  {"tool": "run_tests", "args": {}}
  {"tool": "run_build", "args": {}}
  {"done": true, "summary": "<what you changed>"}

Finish (done:true) once the acceptance criteria are met and tests + build pass, or
if you cannot make further progress. Keep writes minimal and idiomatic to the
surrounding code."""


@dataclass
class RunResult:
    branch: str
    commit: str
    files_changed: int
    backend: str
    steps: int = 0
    summary: str = ""


def _git(cwd: Path, *args: str) -> str:
    name = os.environ.get("CONSULTANCY_GIT_NAME", _DEFAULT_GIT_NAME)
    email = os.environ.get("CONSULTANCY_GIT_EMAIL", _DEFAULT_GIT_EMAIL)
    # strip GIT_* (a hook exports GIT_DIR etc.); pin the consultancy identity.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    cmd = ["git", "-C", str(cwd), "-c", f"user.name={name}",
           "-c", f"user.email={email}", *args]
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if res.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed in {cwd}:\n{(res.stderr or res.stdout).strip()}")
    return res.stdout


# --------------------------------------------------------------------------- tools
def _safe(root: Path, rel: str) -> Path:
    p = (root / rel).resolve()
    if root.resolve() not in p.parents and p != root.resolve():
        raise ValueError(f"path escapes the checkout: {rel}")
    return p


def _npm(root: Path, *args: str) -> str:
    res = subprocess.run(["npm", *args], cwd=root, capture_output=True, text=True)
    tail = (res.stdout + res.stderr).strip()[-_MAX_OBS_CHARS:]
    return f"exit={res.returncode}\n{tail}"


def _run_tool(root: Path, name: str, args: dict, changed: set[str]) -> str:
    if name == "list_files":
        base = _safe(root, args.get("dir", "."))
        if not base.exists():
            return f"(no such dir: {args.get('dir', '.')})"
        return "\n".join(sorted(
            str(p.relative_to(root)) + ("/" if p.is_dir() else "")
            for p in base.iterdir() if p.name != ".git"))
    if name == "read_file":
        p = _safe(root, args["path"])
        return p.read_text(encoding="utf-8")[:_MAX_OBS_CHARS] if p.is_file() else "(missing)"
    if name == "write_file":
        p = _safe(root, args["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(args.get("content", ""), encoding="utf-8")
        changed.add(str(p.relative_to(root)))
        return f"wrote {args['path']} ({len(args.get('content', ''))} bytes)"
    if name == "run_tests":
        return _npm(root, "test")
    if name == "run_build":
        return _npm(root, "run", "build")
    return f"(unknown tool: {name})"


_TRANSIENT = ("overloaded", "rate limit", "rate_limit", "timeout", "timed out",
              "connection", "502", "503", "529", "internal server error")


def _complete(llm, transcript: list[str], *, attempts: int = 4):
    """`llm.complete` with a short backoff on transient API errors (the SDK already
    retries internally; this is the outer guard so one hiccup doesn't kill the run)."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return llm.complete(system=_SYSTEM, user="\n\n".join(transcript), max_tokens=4096)
        except Exception as exc:  # noqa: BLE001 - anthropic errors, not importable here
            last = exc
            if not any(t in str(exc).lower() for t in _TRANSIENT):
                raise
            time.sleep(2 * (i + 1))
    raise last  # type: ignore[misc]


def _agent_loop(llm, root: Path, task: str) -> tuple[set[str], int, str]:
    changed: set[str] = set()
    transcript = [f"TASK.md:\n{task}\n"]
    summary = ""
    for step in range(1, _MAX_STEPS + 1):
        try:
            reply = _complete(llm, transcript)
        except Exception as exc:  # noqa: BLE001 - give up cleanly, keep partial work
            return changed, step, f"stopped after {step - 1} step(s): LLM error: {exc}"
        try:
            action = json.loads(reply.text[reply.text.index("{"):reply.text.rindex("}") + 1])
        except (ValueError, json.JSONDecodeError):
            transcript.append(f"[obs] could not parse your reply as json; retry")
            continue
        if action.get("done"):
            summary = str(action.get("summary", ""))
            return changed, step, summary
        tool, targs = action.get("tool", ""), action.get("args", {}) or {}
        try:
            obs = _run_tool(root, tool, targs, changed)
        except Exception as exc:  # noqa: BLE001 - surface tool errors back to the model
            obs = f"[error] {exc}"
        transcript.append(f"[action] {json.dumps(action)[:400]}\n[obs]\n{obs[:_MAX_OBS_CHARS]}")
    return changed, _MAX_STEPS, summary or "(step budget exhausted)"


# ----------------------------------------------------------------- scripted stub
def _scripted_impl(root: Path, task: str) -> set[str]:
    """Deterministic, offline stand-in for the Claude loop.

    It does not try to satisfy real acceptance criteria — it records the task and
    leaves one mechanical marker commit so the client graph can observe that the
    consultancy side ran and pushed on the feature branch.
    """
    notes = root / "IMPL_NOTES.md"
    head = [ln for ln in task.splitlines() if ln.strip()][:8]
    notes.write_text(
        "# Implementation notes (scripted fallback)\n\n"
        "Deterministic stand-in for the Claude tool-loop "
        "(`--backend stub` / no `CONSULTANCY_ANTHROPIC_API_KEY`).\n\n"
        "## Task digest\n\n" + "\n".join(head) + "\n", encoding="utf-8")
    return {"IMPL_NOTES.md"}


# ------------------------------------------------------------------------- entry
@traceable(run_type="chain", name="consultancy:agent")
def run(repo: str | Path, branch: str, *, backend: str = "auto",
        task_file: str = "TASK.md") -> RunResult:
    """Fetch *branch* from origin into the *repo* checkout, implement ``task_file``,
    commit as the consultancy identity, push back to origin.

    No PR — that path lives in the client's full ``run-task`` pipeline.
    """
    load_env()
    configure_langsmith(role="consultancy")          # -> project ghostc-consultancy
    llm = get_llm(backend, role="consultancy")       # -> CONSULTANCY_ANTHROPIC_API_KEY
    started = time.time()

    root = Path(repo)
    _git(root, "fetch", "-q", "origin")
    _git(root, "checkout", "-q", "-B", branch, f"origin/{branch}")
    task = (root / task_file).read_text(encoding="utf-8")

    if isinstance(llm, StubLLM):
        changed, steps, summary = _scripted_impl(root, task), 0, "scripted fallback"
    else:
        changed, steps, summary = _agent_loop(llm, root, task)

    _git(root, "add", "-A")
    status = _git(root, "status", "--porcelain")
    if not status.strip():                            # nothing to commit — still mark it
        (root / "IMPL_NOTES.md").write_text(
            f"# Implementation notes\n\n{summary or '(agent made no file changes)'}\n"
            f"\n_backend: {getattr(llm, 'model', backend)}, steps: {steps}_\n",
            encoding="utf-8")
        _git(root, "add", "-A")
    msg = f"impl: {branch}" if changed else f"impl (no-op): {branch} — {summary[:60]}"
    _git(root, "commit", "-q", "-m", msg)
    sha = _git(root, "rev-parse", "HEAD").strip()
    _git(root, "push", "-q", "origin", branch)        # GHOSTC_NO_HOOK is set by the hook

    result = RunResult(branch=branch, commit=sha, files_changed=len(changed),
                       backend=getattr(llm, "model", backend), steps=steps, summary=summary)
    # one metrics row per agent run — GHOSTC_METRICS_FILE is exported by the hook so
    # this lands in the same sink as the client's rows (bridge/metrics.py).
    record_run({"role": "consultancy", "command": "start", "flow": "develop",
                "task_branch": branch, "backend": result.backend, "steps": steps,
                "files_changed": len(changed), "outcome": "ok",
                "summary": summary[:200], "commit": sha,
                "wall_clock_s": round(time.time() - started, 3)})
    return result
