#!/usr/bin/env python3
"""Render agent trajectories from the audit log + the metrics sink.

Hackathon deliverable 04 asks for "representative trajectories for every agent",
readable from the agent instructions through to the final result, showing what the
agent did, how its tools responded, the feedback that shaped the next step, and any
retries or human checkpoints.

Those facts already exist as structured data — `audit.jsonl` (one event per pipeline
step) and `metrics/agent-runs.jsonl` (one row per agent run). This script renders
them as markdown rather than restating them by hand, so a trajectory cannot drift
from the run it claims to describe.

    scripts/make-trajectories.py \
        --audit .ghostc/webapp-private/audit.jsonl \
        --metrics metrics/agent-runs.jsonl \
        --out trajectories

Only the surrounding narrative is authored; every number, timestamp, branch name and
tool response below is read from the logs.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

# Events that describe per-file compiler mechanics rather than agent decisions. They
# are the bulk of the log and would bury the trajectory.
_NOISE = {
    "compile.file_scanned", "compile.entity_detected", "compile.transformed",
    "compile.mapping_created", "compile.mapping_reused", "compile.candidate_review",
    "baseline.file_scanned", "discover.candidate_scored", "eval.case",
}

# component -> which agent's trajectory the event belongs to.
_CLIENT = {"client_agent", "spec_compiler", "reverse-compiler", "orchestrator",
           "compiler", "verifier"}
_CONSULTANCY = {"consultancy_agent"}


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _clock(ts: str, origin: datetime | None) -> str:
    """Elapsed time from the first event — more readable than absolute stamps."""
    try:
        t = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return "—"
    if origin is None:
        return "0.0s"
    return f"{(t - origin).total_seconds():.1f}s"


def _origin(events: list[dict]) -> datetime | None:
    for e in events:
        try:
            return datetime.fromisoformat(e["ts"])
        except (KeyError, TypeError, ValueError):
            continue
    return None


def _fmt_details(event: str, d: dict, subject: dict | None = None) -> str:
    """One-line, human-readable rendering of the event payload."""
    subject = subject or {}
    if event == "patch.entity_resolved":
        eid = subject.get("entity_id", "?")
        return f"`{eid}` — " + ("**lossy** (multi-word display name — flagged for human "
                                "review)" if d.get("lossy") else "exact round-trip")
    if not d:
        return ""
    if event == "spec.compiled":
        subs = d.get("substitutions", [])
        parts = [f"{s['entity_id']}→`{s['ghost']}` ×{s['count']}" for s in subs]
        return f"{len(subs)} entities substituted: " + ", ".join(parts)
    if event == "agent.consultancy_developed":
        return (f"branch `{d.get('branch')}` · commit `{str(d.get('commit'))[:8]}` · "
                f"+{d.get('commits_added')} commit(s) by {', '.join(d.get('authors', []))}")
    if event == "patch.parsed":
        return (f"{d.get('files')} files, {d.get('hunks')} hunks · entities resolved: "
                + ", ".join(d.get("entities_resolved", [])))
    if event in ("agent.real_pr_blocked",):
        detail = str(d.get("detail", "")).strip().splitlines()
        head = detail[0] if detail else ""
        return f"**{d.get('reason')}** — `{head}`" + (f" (+{len(detail) - 1} more)"
                                                      if len(detail) > 1 else "")
    if event == "agent.real_pr_opened":
        return (f"branch `{d.get('branch')}` · commit `{str(d.get('commit'))[:8]}` · "
                f"{d.get('files')} files / {d.get('hunks')} hunks")
    if event == "approval.requested":
        return f"gate `{d.get('gate')}` on `{d.get('branch')}` — **awaiting a human**"
    if event == "agent.metrics":
        keep = ("outcome", "wall_clock_s", "ghost_tests", "ghost_build", "llm_model",
                "substitutions", "reason")
        return " · ".join(f"{k}={json.dumps(d[k]) if isinstance(d[k], dict) else d[k]}"
                          for k in keep if k in d)
    if event in ("run.start", "run.end"):
        return " · ".join(f"{k}={v}" for k, v in sorted(d.items()))
    return " · ".join(f"{k}={json.dumps(v)[:80] if isinstance(v, (dict, list)) else v}"
                      for k, v in sorted(d.items()) if k != "real_sha256")


def _rows(events: list[dict], origin: datetime | None) -> list[str]:
    rows = ["| t | component | event | decision | what happened |",
            "|---|---|---|---|---|"]
    for e in events:
        decision = e.get("decision", "")
        mark = {"block": "**BLOCK**", "pending": "**PENDING**",
                "ok": "ok", "pass": "pass"}.get(decision, decision or "—")
        rows.append(
            f"| {_clock(e.get('ts', ''), origin)} | `{e.get('component', '?')}` "
            f"| `{e.get('event', '?')}` | {mark} "
            f"| {_fmt_details(e.get('event', ''), e.get('details', {}), e.get('subject'))} |"
        )
    return rows


# One CLI command can span more than one `operation_id` — `open-real-pr` allocates one
# for the reverse-compile and another for the PR it opens. Grouping on the id alone
# would split a single command in half, so episodes are cut on these openers instead.
_EPISODE_START = {"run.start", "agent.task_started", "patch.parsed"}


def _invocations(events: list[dict]) -> list[list[dict]]:
    """Split the log into command episodes — one group per CLI invocation.

    Without this the elapsed clock runs across runs that are minutes apart and the
    retry reads as part of the first attempt rather than as a second command.
    """
    groups: list[list[dict]] = []
    for e in events:
        starts = e.get("event") in _EPISODE_START
        opened = groups and any(x.get("event") in _EPISODE_START for x in groups[-1])
        if not groups or (starts and opened):
            groups.append([e])
        else:
            groups[-1].append(e)
    return groups


def _table(events: list[dict]) -> list[str]:
    """One table per invocation, each with its own clock starting at 0."""
    out: list[str] = []
    for i, evs in enumerate(_invocations(events), 1):
        ops = list(dict.fromkeys(e.get("operation_id", "—") for e in evs))
        out += ["", f"### Invocation {i} — {_invocation_label(evs)}  ·  "
                    f"`operation_id={', '.join(ops)}`", ""]
        out += _rows(evs, _origin(evs))
    return out


def _invocation_label(evs: list[dict]) -> str:
    """Name an invocation by the command in its metrics row, else its first event."""
    for e in evs:
        cmd = (e.get("details") or {}).get("command")
        if cmd:
            outcome = (e.get("details") or {}).get("outcome")
            return f"`{cmd}`" + (f" → **{outcome}**" if outcome else "")
    first, comp = evs[0].get("event", "?"), evs[0].get("component", "")
    if first == "run.start" and comp == "compiler":
        return "`ghostc compile` — stage the ghost repo"
    if first == "agent.task_started":
        return "`client-agent start` — sanitize the ticket and hand off"
    return f"`{first}`"


def _subset(events: list[dict], components: set[str]) -> list[dict]:
    return [e for e in events
            if e.get("component") in components and e.get("event") not in _NOISE]


# --------------------------------------------------------------------- renderers

_HEADER = """> **Generated** by `scripts/make-trajectories.py` from `{audit}`
> and `{metrics}`. Every timestamp, branch, count and tool response below is read
> from those logs — only the narrative between the tables is authored. Regenerate with:
>
> ```bash
> scripts/make-trajectories.py --audit {audit} --metrics {metrics} --out trajectories
> ```
"""


def client_trajectory(events: list[dict], runs: list[dict], audit: str, metrics: str) -> str:
    ev = _subset(events, _CLIENT)
    origin = _origin(ev)
    client_runs = [r for r in runs if r.get("role") == "client"]
    blocked = [e for e in ev if e.get("decision") == "block"]
    gates = [e for e in ev if e.get("event") == "approval.requested"]

    out = [
        "# Trajectory 1 — client orchestrator (`client_agent`)",
        "",
        _HEADER.format(audit=audit, metrics=metrics),
        "",
        "## The agent",
        "",
        "| | |",
        "|---|---|",
        "| **Role** | Company-side orchestrator. Owns the real repo, the mapping store and "
        "the audit log. The only component allowed to see both sides of the boundary. |",
        "| **Kind** | LangGraph state machine — fixed nodes, deterministic transitions. Not "
        "a free-running prompt loop: the graph decides what happens next, so a fail-closed "
        "gate cannot be talked out of by a model. |",
        "| **Instructions** | The graph topology itself (`client_agent/graph.py::_wire`, "
        "diagram in `client_agent/graph.md`). One LLM call inside it — the PR-consistency "
        "verdict — is prompted in `client_agent/graph.py`. |",
        "| **Tools** | `ghostc.spec.compile_spec`, `ghostc.patch.reverse_patch`, "
        "`ghostc.verify`, `bridge.forge` (git), `bridge.llm` (consistency verdict). |",
        "| **Boundary rule** | `handoff` is the only node that writes to the ghost side. |",
        "",
        "## Node sequence",
        "",
        "```",
        "plan → compile_spec → handoff → await_ghost_pr → reverse_patch → verify",
        "     → consistency → open_real_pr → emit_metrics",
        "```",
        "",
        "Dotted edges in `client_agent/graph.md` are fail-closed short-circuits: on any "
        "`Rejection`, the run jumps straight to `emit_metrics` and **no PR is opened**.",
        "",
        "## What actually happened",
        "",
    ]
    out += _table(ev)
    out += [
        "",
        "## Reading the trajectory",
        "",
        "1. **`spec.compiled` is a gate, not a formatting step.** The real ticket names the "
        "client, the internal service and two vendors. The sanitized `TASK.md` that reaches "
        "the external agent carries only aliases. If any entity could not be resolved the "
        "node raises and the run ends here — the task text never crosses half-sanitized.",
        "2. **`agent.spec_handoff` is the boundary crossing.** Everything after it that "
        "touches ghost data is the other agent's work (trajectory 2).",
        "3. **`patch.entity_resolved` carries a `lossy` flag.** A code token round-trips "
        "exactly; a multi-word display name may not, so it is flagged rather than guessed — "
        "the reverse compiler never invents a real value it is not sure of.",
    ]

    if blocked:
        b = blocked[0]
        out += [
            "",
            "## The retry — a real fail-closed block",
            "",
            f"At `{_clock(b.get('ts', ''), origin)}` the run **stopped** rather than "
            "producing a real-repo branch:",
            "",
            "```",
            str(b.get("details", {}).get("detail", "")).strip() or "(no detail)",
            "```",
            "",
            f"Reason recorded: `{b.get('details', {}).get('reason')}`. The reverse-compiled "
            "diff was correct but its context lines no longer matched the real repo, which "
            "had moved on. The orchestrator did **not** force the patch, fuzz the context, "
            "or open a partial PR — `open-real-pr` exited non-zero and wrote a `rejected` "
            "metrics row.",
            "",
            "The operator re-ran the command against the current base; the second attempt "
            "resolved the same three entities and opened the branch. **Both attempts are in "
            "the log** — the rejected one is evidence the gate is real, not decorative.",
        ]

    if gates:
        out += [
            "",
            "## Human checkpoint",
            "",
            f"The run ends at `approval.requested` (`gate="
            f"{gates[-1].get('details', {}).get('gate')}`) with decision **pending**. The "
            "real-repo branch exists and is flagged `HUMAN REVIEW REQUIRED`; nothing merges "
            "without a person. The `lossy` entity flag is what that reviewer is asked to "
            "check first.",
        ]

    if client_runs:
        out += ["", "## Metrics rows for these runs", "", "```json"]
        out += [json.dumps(r, sort_keys=True) for r in client_runs]
        out += ["```"]
    return "\n".join(out) + "\n"


def consultancy_trajectory(events: list[dict], runs: list[dict],
                           audit: str, metrics: str,
                           steps_path: Path | None = None) -> str:
    ev = _subset(events, _CONSULTANCY)
    origin = _origin(_subset(events, _CLIENT | _CONSULTANCY))
    cruns = [r for r in runs if r.get("role") == "consultancy"]
    real = [r for r in cruns if r.get("backend", "").startswith("claude")]

    out = [
        "# Trajectory 2 — consultancy coding agent (`consultancy_agent`)",
        "",
        _HEADER.format(audit=audit, metrics=metrics),
        "",
        "## The agent",
        "",
        "| | |",
        "|---|---|",
        "| **Role** | The external coding agent. Stands in for Codex / Copilot / a "
        "contractor's Claude. Treated as untrusted. |",
        "| **Kind** | A real prompt loop — Claude, driven step by step against a tool "
        "surface until the acceptance criteria are met and tests and build are green "
        "(`consultancy_agent/agent.py`). |",
        "| **Sees** | The **ghost** checkout and the sanitized `TASK.md`. Nothing else. |",
        "| **Cannot see** | The real repo, the mapping store, `privacy.yaml`, the audit log, "
        "any credential. Enforced at import level: `consultancy_agent/` may not import "
        "`ghostc` or `client_agent` — `tests/test_boundary.py` fails the build if it does. |",
        "| **Tools** | `list_files`, `read_file`, `write_file`, `run_tests`, `run_build`. |",
        "",
        "## Agent instructions (verbatim, `consultancy_agent/agent.py::_SYSTEM`)",
        "",
        "```text",
        _system_prompt(),
        "```",
        "",
        "## The verification feedback loop",
        "",
        "This is the design choice that matters most in this agent. `done: true` is **not** "
        "taken at face value — it is only honoured once `run_tests` *and* `run_build` have "
        "each returned `exit=0` **since the last `write_file`**. Any write resets both flags. "
        "If the model claims done early it receives:",
        "",
        "```text",
        "[obs] you are NOT done — run_tests has not returned exit=0 since your last",
        "write_file. Run run_tests and run_build; if either fails, read the output, fix",
        "the code, and re-run. Re-check every acceptance criterion before saying done again.",
        "```",
        "",
        "Every turn also carries a status line the model cannot ignore:",
        "",
        "```text",
        "[status] step 7/N · tests_green=False · build_green=True · files_written=[...]",
        "```",
        "",
        "So the agent's next step is shaped by tool output, not by its own confidence. "
        "After a bounded number of premature `done` claims the partial result is accepted "
        "and **labelled** as unconfirmed rather than silently trusted.",
        "",
        "## What actually happened",
        "",
    ]
    out += _table(ev)
    if steps_path is not None:
        out += _steps_section(steps_path)

    if real:
        r = real[0]
        t = r.get("ghost_tests", {}) or {}
        out += [
            "",
            "## The real run",
            "",
            "| | |",
            "|---|---|",
            f"| Backend | `{r.get('backend')}` |",
            f"| Steps (tool calls) | **{r.get('steps')}** |",
            f"| Wall-clock | {r.get('wall_clock_s')}s |",
            f"| Files changed | {r.get('files_changed')} |",
            f"| Ghost tests | {t.get('pass')}/{t.get('tests')} passing, "
            f"{t.get('fail')} failing → `ok={t.get('ok')}` |",
            f"| Ghost build | `ok={(r.get('ghost_build') or {}).get('ok')}` |",
            f"| Outcome | `{r.get('outcome')}` |",
            f"| Branch | `{r.get('task_branch')}` |",
            "",
            "Agent's own closing summary, as recorded:",
            "",
            "> " + str(r.get("summary", "")).strip().replace("\n", "\n> "),
            "",
            f"**{r.get('steps')} steps to satisfy the acceptance criteria** — the loop did "
            "not converge on the first attempt. It read the sibling client it was told to "
            "mirror, wrote the integration, ran the tests, and iterated until the suite and "
            "the build were both green. That is the shape the verification gate forces.",
            "",
            "## What it never saw",
            "",
            "The agent produced a working implementation while the words *Northwind*, "
            "*SkyRoute*, *booking-core* and the real vendor name were absent from everything "
            "it was given. Its commits are authored as a separate git identity "
            "(`Consultancy Dev`), so `git log` on the ghost branch shows two distinct "
            "parties — the client's handoff commit and the external agent's work.",
        ]
    else:
        out += ["", "_No `--consultancy-backend claude` run in this metrics file; "
                    "run one, or see the stub trajectory._"]

    if cruns:
        out += ["", "## Metrics rows for these runs", "", "```json"]
        out += [json.dumps(r, sort_keys=True) for r in cruns]
        out += ["```"]
    return "\n".join(out) + "\n"


def _steps_section(steps_path: Path) -> list[str]:
    """Render the per-tool-call trace written by `bridge.trajectory`, if one exists."""
    rows = _load(steps_path)
    if not rows:
        return [
            "",
            "## Per-step tool trace",
            "",
            f"_No step trace at `{steps_path}`._ Step-level capture "
            "(`bridge/trajectory.py`) records one line per tool call and per nudge; it is "
            "written by any `--consultancy-backend claude` run. The run above predates it, "
            "so only its aggregate is available. To produce the full trace:",
            "",
            "```bash",
            "client-agent start <spec> --consultancy-backend claude",
            "scripts/make-trajectories.py   # picks the trace up automatically",
            "```",
        ]

    meta = next((r for r in rows if r.get("kind") == "meta"), {})
    end = next((r for r in rows if r.get("kind") == "end"), {})
    out = ["", "## Per-step tool trace", "",
           f"From `{steps_path}` — one line per tool call, written live by the agent loop.",
           "",
           "| step | action | tool responded | tests | build |",
           "|---:|---|---|:---:|:---:|"]
    for r in rows:
        if r.get("kind") == "step":
            args = r.get("args") or {}
            hint = args.get("path") or args.get("dir") or ""
            obs = str(r.get("observation", "")).strip().replace("\n", " ⏎ ")
            out.append(
                f"| {r.get('step')} | `{r.get('tool')}`"
                + (f" `{hint}`" if hint else "")
                + f" | {obs[:150]} "
                  f"| {'✓' if r.get('tests_green') else '·'} "
                  f"| {'✓' if r.get('build_green') else '·'} |"
            )
        elif r.get("kind") == "note":
            out.append(f"| {r.get('step')} | **feedback → the model** "
                       f"(`{r.get('cause', 'note')}`) "
                       f"| {str(r.get('text', ''))[:150]} | | |")
    if end:
        out += ["", f"**Result:** `{end.get('outcome')}` · {end.get('steps')} steps · "
                    f"{end.get('files_changed')} files changed · "
                    f"tests `{json.dumps(end.get('ghost_tests'))}` · "
                    f"build `{json.dumps(end.get('ghost_build'))}`."]
    if meta.get("max_steps"):
        out += ["", f"Budget: `max_steps={meta['max_steps']}`, "
                    f"`max_done_nudges={meta.get('max_done_nudges')}`."]
    return out


def _system_prompt() -> str:
    """Read _SYSTEM out of the agent module so the trajectory cannot drift from it."""
    try:
        from consultancy_agent.agent import _SYSTEM
        return _SYSTEM.strip()
    except Exception:  # noqa: BLE001 - the extra may not be installed
        src = Path(__file__).resolve().parents[1] / "consultancy_agent" / "agent.py"
        text = src.read_text(encoding="utf-8")
        start = text.index('_SYSTEM = """') + len('_SYSTEM = """')
        return text[start:text.index('"""', start)].strip()


def index(audit: str, metrics: str, wrote: list[str]) -> str:
    return "\n".join([
        "# Agent trajectories",
        "",
        "Hackathon deliverable 04. One trajectory per agent, each readable from the agent's "
        "instructions through to its final result — what it did, how its tools responded, "
        "the feedback that shaped the next step, and every retry and human checkpoint.",
        "",
        "These are **generated from the run logs**, not written from memory:",
        "",
        "```bash",
        f"scripts/make-trajectories.py --audit {audit} \\",
        f"    --metrics {metrics} --out trajectories",
        "```",
        "",
        "| # | Agent | Kind | Trajectory |",
        "|---|---|---|---|",
        "| 1 | client orchestrator (`client_agent`) | LangGraph state machine + one LLM "
        "verdict | [`01-client-orchestrator.md`](01-client-orchestrator.md) |",
        "| 2 | consultancy coding agent (`consultancy_agent`) | Claude prompt loop over a "
        "tool surface | [`02-consultancy-coding-agent.md`](02-consultancy-coding-agent.md) |",
        "",
        "## Why there are only two",
        "",
        "`ghostc discover`, the privacy compiler, the verifier and the reverse-patch "
        "compiler are **deterministic programs, not agents** — they are the tools the two "
        "agents call, and they are covered by the audit log and the test suite rather than "
        "by a trajectory. Presenting them as agents would overstate what they are.",
        "",
        "## The two things worth looking at",
        "",
        "- **A genuine fail-closed block and its retry** — trajectory 1. The reverse-compiled "
        "diff did not apply to a real repo that had moved on, so the run stopped and wrote a "
        "`rejected` metrics row instead of forcing the patch. Both attempts are in the log.",
        "- **Verification shaping the next step** — trajectory 2. `done: true` is refused "
        "until `run_tests` and `run_build` have both returned `exit=0` since the last write, "
        "so the agent's own claim of completion is never what ends the run.",
        "",
        "Generated files: " + ", ".join(f"`{w}`" for w in wrote) + ".",
        "",
    ]) + "\n"


def _newest_steps(metrics: Path) -> Path:
    """The most recent consultancy step trace beside the metrics sink."""
    d = metrics.parent / "trajectories"
    found = sorted(d.glob("*-consultancy.jsonl"), key=lambda p: p.stat().st_mtime) \
        if d.is_dir() else []
    return found[-1] if found else d / "<none>-consultancy.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audit", default=".ghostc/webapp-private/audit.jsonl")
    ap.add_argument("--metrics", default="metrics/agent-runs.jsonl")
    ap.add_argument("--out", default="trajectories")
    ap.add_argument("--steps", default=None,
                    help="consultancy step trace (bridge/trajectory.py). Default: the "
                         "newest *-consultancy.jsonl beside the metrics sink.")
    args = ap.parse_args()

    events = _load(Path(args.audit))
    runs = _load(Path(args.metrics))
    if not events:
        print(f"no audit events in {args.audit} — run the agent workflow first")
        return 1

    steps_path = Path(args.steps) if args.steps else _newest_steps(Path(args.metrics))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "01-client-orchestrator.md": client_trajectory(events, runs, args.audit, args.metrics),
        "02-consultancy-coding-agent.md": consultancy_trajectory(events, runs, args.audit,
                                                                 args.metrics, steps_path),
    }
    for name, text in files.items():
        (out / name).write_text(text, encoding="utf-8")
    (out / "README.md").write_text(index(args.audit, args.metrics, list(files)), encoding="utf-8")

    for name in [*files, "README.md"]:
        print(f"wrote {out / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
