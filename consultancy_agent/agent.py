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
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from bridge.env import load_env
from bridge.llm import StubLLM, configure_langsmith, get_llm
from bridge.metrics import record_run
from bridge.trace import traceable

_MAX_STEPS = 40
_MAX_OBS_CHARS = 4000
# `done:true` is refused while tests/build are not both green; after this many
# refusals we accept the partial result rather than burn the whole step budget.
_MAX_DONE_NUDGES = 3
# only the TASK/AC header + this many trailing exchanges are sent each turn, so a
# long run does not grow the prompt without bound.
_TRANSCRIPT_TAIL = 30

# The consultancy commits as its own actor — a different person from the client's
# `ghostc-client` handoff commit, so `git log` on the task branch shows two parties.
# Override per engagement with CONSULTANCY_GIT_NAME / CONSULTANCY_GIT_EMAIL.
_DEFAULT_GIT_NAME = "Consultancy Dev"
_DEFAULT_GIT_EMAIL = "dev@consultancy.example"

_SYSTEM = """You are an autonomous coding agent working inside a single git checkout.
Implement the change described in TASK.md **in full**. Work only inside the repo.

Method — follow in order:
  1. list_files on "." and the directories it names to learn the layout.
  2. Enumerate the acceptance criteria (AC1, AC2, ...) from TASK.md. You must
     satisfy EVERY one — a partial implementation is a failure.
  3. read_file the existing files the task points at (the sibling client / service
     / config / test it tells you to mirror) BEFORE writing, so new code matches
     the surrounding style and shape.
  4. write_file each change. Keep writes minimal and idiomatic.
  5. run_tests, then run_build. If either fails, read the output, fix the code,
     and re-run. Repeat until both pass.
  6. Only when every AC is done AND run_tests AND run_build have both passed on
     this checkout, reply {"done": true, "summary": "<what you changed, AC by AC>"}.

Each turn, reply with exactly ONE json object and nothing else — no prose, no
markdown fences:
  {"tool": "list_files", "args": {"dir": "."}}
  {"tool": "read_file", "args": {"path": "src/config.js"}}
  {"tool": "write_file", "args": {"path": "src/x.js", "content": "..."}}
  {"tool": "run_tests", "args": {}}
  {"tool": "run_build", "args": {}}
  {"done": true, "summary": "<what you changed>"}

You have a generous step budget. Do not stop early, do not leave an AC unfinished,
and do not claim done before the tests and build have actually passed."""


@dataclass
class RunResult:
    branch: str
    commit: str
    files_changed: int
    backend: str
    steps: int = 0
    summary: str = ""
    ghost_tests: dict | None = None   # {ok, pass, fail, tests} from `node --test`
    ghost_build: dict | None = None   # {ok} from the build script


def _acceptance_criteria(task: str) -> str:
    """The '## Acceptance criteria' block of TASK.md, verbatim (up to the next '## ')."""
    out: list[str] = []
    capture = False
    for ln in task.splitlines():
        s = ln.strip().lower()
        if s.startswith("## ") and "acceptance" in s:
            capture = True
            continue
        if capture and ln.strip().startswith("## "):
            break
        if capture:
            out.append(ln)
    return "\n".join(out).strip()


def _parse_action(text: str) -> dict:
    """Tolerant: strips a ```json fence and any prose around the object."""
    t = text.strip()
    if t.startswith("```"):
        t = t[3:]
        if t[:4].lower() == "json":
            t = t[4:]
        t = t.split("```", 1)[0]
    t = t.strip()
    try:
        return json.loads(t)
    except (ValueError, json.JSONDecodeError):
        pass
    try:
        return json.loads(t[t.index("{"): t.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError(str(exc)) from exc


def _test_counts(obs: str) -> dict:
    """Parse the `node --test` TAP summary tail produced by :func:`_npm`."""
    def _n(key: str) -> int | None:
        m = re.search(rf"^# {key} (\d+)$", obs, re.M)
        return int(m.group(1)) if m else None

    return {"ok": obs.startswith("exit=0"), "pass": _n("pass"),
            "fail": _n("fail"), "tests": _n("tests")}


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
            return llm.complete(system=_SYSTEM, user="\n\n".join(transcript), max_tokens=8000)
        except Exception as exc:  # noqa: BLE001 - anthropic errors, not importable here
            last = exc
            if not any(t in str(exc).lower() for t in _TRANSIENT):
                raise
            time.sleep(2 * (i + 1))
    raise last  # type: ignore[misc]


def _agent_loop(llm, root: Path, task: str) -> tuple[set[str], int, str]:
    """Drive Claude through the checkout until every AC is met and tests + build are
    green, or the step / nudge budget runs out. Returns (changed, steps, summary).

    ``done:true`` is only honoured once ``run_tests`` and ``run_build`` have each
    returned ``exit=0`` since the last ``write_file`` — otherwise the model is
    nudged to keep going. After ``_MAX_DONE_NUDGES`` refusals the partial result
    is accepted so the run still commits something.
    """
    changed: set[str] = set()
    acs = _acceptance_criteria(task)
    header = [f"TASK.md:\n{task}\n"]
    if acs:
        header.append("[acceptance criteria — you must satisfy EVERY one]\n" + acs)
    exchanges: list[str] = []
    summary = ""
    tests_green = build_green = False
    done_nudges = 0

    for step in range(1, _MAX_STEPS + 1):
        status = (f"[status] step {step}/{_MAX_STEPS} · tests_green={tests_green} · "
                  f"build_green={build_green} · files_written={sorted(changed) or []}")
        prompt = header + exchanges[-_TRANSCRIPT_TAIL:] + [status]
        try:
            reply = _complete(llm, prompt)
        except Exception as exc:  # noqa: BLE001 - give up cleanly, keep partial work
            return changed, step, f"stopped after {step - 1} step(s): LLM error: {exc}"
        try:
            action = _parse_action(reply.text)
        except ValueError:
            exchanges.append("[obs] could not parse your reply — send exactly ONE json "
                             "object, no markdown fences, no prose")
            continue

        if action.get("done"):
            if tests_green and build_green:
                return changed, step, str(action.get("summary", ""))
            done_nudges += 1
            if done_nudges > _MAX_DONE_NUDGES:
                return changed, step, (str(action.get("summary", "")).strip()
                                       + " [accepted with tests/build NOT confirmed green]")
            missing = []
            if not tests_green:
                missing.append("run_tests has not returned exit=0 since your last write_file")
            if not build_green:
                missing.append("run_build has not returned exit=0 since your last write_file")
            exchanges.append("[obs] you are NOT done — " + "; ".join(missing)
                             + ". Run run_tests and run_build; if either fails, read the "
                             "output, fix the code, and re-run. Re-check every acceptance "
                             "criterion before saying done again.")
            continue

        tool, targs = action.get("tool", ""), action.get("args", {}) or {}
        try:
            obs = _run_tool(root, tool, targs, changed)
        except Exception as exc:  # noqa: BLE001 - surface tool errors back to the model
            obs = f"[error] {exc}"
        if tool == "write_file":
            tests_green = build_green = False       # code changed — must re-verify
        elif tool == "run_tests":
            tests_green = obs.startswith("exit=0")
        elif tool == "run_build":
            build_green = obs.startswith("exit=0")
        exchanges.append(f"[action] {json.dumps(action)[:400]}\n[obs]\n{obs[:_MAX_OBS_CHARS]}")

    return changed, _MAX_STEPS, summary or "(step budget exhausted)"


# ----------------------------------------------------------------- scripted stub
_SRC_PATH_RE = re.compile(r"`([\w./-]+\.(?:js|ts|mjs|cjs))`")
_CLASS_RE = re.compile(r"`?([A-Z]\w+)`?\s+class\b|class\s+`?([A-Z]\w+)`?")


def _scripted_impl(root: Path, task: str) -> set[str]:
    """Deterministic, offline stand-in for the Claude loop.

    Writes ``IMPL_NOTES.md`` **and** one small implementation file so the ghost
    task branch carries a real (if minimal) code change — enough for
    ``client-agent open-real-pr`` to reverse-compile onto the real repo on the
    fully offline path (`--consultancy-backend stub`). It does not try to satisfy
    the acceptance criteria; it just leaves a syntactically valid module where the
    task says one should go. Everything it emits is derived from the
    already-sanitized ``TASK.md``, so no real entity can enter here.
    """
    head = [ln for ln in task.splitlines() if ln.strip()][:8]
    (root / "IMPL_NOTES.md").write_text(
        "# Implementation notes (scripted fallback)\n\n"
        "Deterministic stand-in for the Claude tool-loop "
        "(`--backend stub` / no `CONSULTANCY_ANTHROPIC_API_KEY`).\n\n"
        "## Task digest\n\n" + "\n".join(head) + "\n", encoding="utf-8")
    changed = {"IMPL_NOTES.md"}

    # the first *new* source path the task names (AC "New `src/...`"), else a
    # generic module — never an existing file, so we always add a real change.
    cand = [m.group(1) for m in _SRC_PATH_RE.finditer(task)
            if m.group(1).startswith(("src/", "test/", "lib/"))]
    rel = next((p for p in cand if not (root / p).exists()), "src/ghostc_scripted_stub.js")
    cm = _CLASS_RE.search(task)
    name = (cm.group(1) or cm.group(2)) if cm else "GhostcScriptedStub"

    target = root / rel
    if not target.exists():                       # never clobber an existing file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "// ghostc scripted stub — deterministic offline stand-in for the\n"
            "// consultancy agent (`--consultancy-backend stub`). A live run\n"
            "// replaces this with a real implementation of TASK.md.\n"
            "'use strict';\n\n"
            f"class {name} {{\n"
            "  async fetch() {\n"
            f"    return {{ provider: {name!r}, fetchedAt: new Date(0).toISOString(), items: [] }};\n"
            "  }\n"
            "}\n\n"
            f"module.exports = {{ {name} }};\n", encoding="utf-8")
        changed.add(rel)
    return changed


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

    stub = isinstance(llm, StubLLM)
    if stub:
        changed, steps, summary = _scripted_impl(root, task), 0, "scripted fallback"
    else:
        changed, steps, summary = _agent_loop(llm, root, task)

    # C3: authoritative test + build status on the developed checkout, recorded
    # regardless of whether the loop finished clean or ran out of budget. The stub
    # path makes no real implementation, so there is nothing meaningful to measure.
    ghost_tests = ghost_build = None
    if not stub and (root / "package.json").is_file():
        ghost_tests = _test_counts(_npm(root, "test"))
        ghost_build = {"ok": _npm(root, "run", "build").startswith("exit=0")}

    _git(root, "add", "-A")
    status = _git(root, "status", "--porcelain")
    if not status.strip():                            # nothing to commit — still mark it
        checks = ""
        if ghost_tests is not None:
            checks = (f"\n_tests: {'pass' if ghost_tests['ok'] else 'FAIL'}"
                      f" ({ghost_tests.get('pass')}/{ghost_tests.get('tests')}), "
                      f"build: {'pass' if ghost_build['ok'] else 'FAIL'}_\n")
        (root / "IMPL_NOTES.md").write_text(
            f"# Implementation notes\n\n{summary or '(agent made no file changes)'}\n"
            f"\n_backend: {getattr(llm, 'model', backend)}, steps: {steps}_\n{checks}",
            encoding="utf-8")
        _git(root, "add", "-A")
    msg = f"impl: {branch}" if changed else f"impl (no-op): {branch} — {summary[:60]}"
    _git(root, "commit", "-q", "-m", msg)
    sha = _git(root, "rev-parse", "HEAD").strip()
    _git(root, "push", "-q", "origin", branch)        # GHOSTC_NO_HOOK is set by the hook

    result = RunResult(branch=branch, commit=sha, files_changed=len(changed),
                       backend=getattr(llm, "model", backend), steps=steps, summary=summary,
                       ghost_tests=ghost_tests, ghost_build=ghost_build)
    # one metrics row per agent run — GHOSTC_METRICS_FILE is exported by the hook so
    # this lands in the same sink as the client's rows (bridge/metrics.py).
    record_run({"role": "consultancy", "command": "start", "flow": "develop",
                "task_branch": branch, "backend": result.backend, "steps": steps,
                "files_changed": len(changed), "outcome": "ok",
                "summary": summary[:200], "commit": sha,
                "ghost_tests": ghost_tests, "ghost_build": ghost_build,
                "wall_clock_s": round(time.time() - started, 3)})
    return result
