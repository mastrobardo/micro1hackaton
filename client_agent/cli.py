"""``ghostc-agent`` / ``client-agent`` — the client-side agent workflow CLI.

    client-agent start <spec>            # reduced, hook-triggered flow (spec file -> ghost
                                         #   branch -> post-receive hook -> consultancy develops)
    ghostc-agent run-task --task <file|-> [--backend auto|claude|stub]   # full pipeline
    ghostc-agent print-graph            # regenerate client_agent/graph.md

``client-agent`` and ``ghostc-agent`` are the same Click group (two console-script
names). Split from ``ghostc`` proper: ``ghostc`` is the deterministic privacy
compiler, this is the LangGraph orchestrator on top of it (needs the [agents] extra).
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import click

from bridge.env import load_env
from ghostc.config import ConfigError, load_config

# Defaults for `client-agent start` — the runnable webapp fixture
# (fixtures/webapp/app -> ../ghostc-demo/{real,ghost}); see memory/demoable-fixture.md.
# The reduced flow works on the REAL repos: `../ghostc-demo/ghost` gets a bare
# origin `../ghostc-demo/ghost.git` + a `post-receive` hook, and the consultancy
# gets its own clone `../ghostc-demo/ghost-consultancy`. Boundary-internal artifacts
# (mapping = real values, audit) stay in a gitignored in-repo dir — NOT under
# ../ghostc-demo/ next to the ghost tree (THREAT_MODEL).
_SPECS_DIR = "specs"
_WEBAPP_CONFIG = "fixtures/webapp/privacy.webapp.yaml"
_WEBAPP_GHOST = "../ghostc-demo/ghost"
_WEBAPP_REAL = "../ghostc-demo/real"
_WEBAPP_MAPPING = ".ghostc/webapp-private/mapping.json"
_WEBAPP_AUDIT = ".ghostc/webapp-private/audit.jsonl"
_AGENT_WORKSPACE = ".ghostc/agent"          # full pipeline only (synthesized forge)


def _resolve_spec(name_or_path: str) -> tuple[str, str, str]:
    """(text, spec_id, stem) for a spec given as a bare name, a path, or '-' (stdin).

    ``spec_id`` is the boundary-neutral ``task-id:`` (→ ghost branch name); ``stem``
    is the real spec filename (the human's descriptive name, used to derive the
    *decoded* real-repo branch).
    """
    if name_or_path == "-":
        return click.get_text_stream("stdin").read(), "spec-stdin", "spec-stdin"
    p = Path(name_or_path)
    if not p.exists() and p.parent == Path("."):
        cand = Path(_SPECS_DIR) / name_or_path
        p = cand if cand.exists() else cand.with_suffix(".md")
    if not p.exists():
        raise SystemExit(f"spec not found: {name_or_path} (looked in ./ and ./{_SPECS_DIR}/)")
    text = p.read_text(encoding="utf-8")
    m = re.search(r"task-id:\s*([A-Za-z0-9._-]+)", text)
    return text, (m.group(1) if m else p.stem), p.stem


@click.group()
def main() -> None:
    """Client-side agent: real task -> ghost branch + TASK.md -> ghost PR -> real-repo PR."""
    # Load .env (repo root or $GHOSTC_ENV_FILE) before anything reads os.environ.
    # Never overrides a var already set in the real environment.
    load_env()


@main.command("run-task")
@click.option("--task", "task_path", required=True, type=click.Path(),
              help="Real implementation task text: a file path, or '-' for stdin.")
@click.option("--task-id", default=None,
              help="Stable id for the ghost/real branches + PRs (default: derived).")
@click.option("--real-repo", default="workspace/real", show_default=True, type=click.Path())
@click.option("--ghost-tree", default="workspace/ghost", show_default=True,
              type=click.Path(), help="Ghost repo produced by `ghostc compile`.")
@click.option("--config", "config_path", default="privacy.yaml", show_default=True,
              type=click.Path())
@click.option("--mapping", "mapping_path", default="workspace/private/mapping.json",
              show_default=True, type=click.Path())
@click.option("--audit", "audit_path", default="workspace/private/audit.jsonl",
              show_default=True, type=click.Path())
@click.option("--workspace", default=_AGENT_WORKSPACE, show_default=True,
              type=click.Path(), help="Where the agent's ghost/real git remotes live.")
@click.option("--backend", type=click.Choice(["auto", "claude", "stub"]),
              default="auto", show_default=True,
              help="LLM backend for the consistency gate. auto: Claude if a key is set.")
@click.option("--metrics-file", default=None, type=click.Path(),
              help="Per-run metrics JSONL sink (default: metrics/agent-runs.jsonl "
                   "or $GHOSTC_METRICS_FILE).")
def run_task_cmd(task_path: str, task_id: str | None, real_repo: str, ghost_tree: str,
                 config_path: str, mapping_path: str, audit_path: str, workspace: str,
                 backend: str, metrics_file: str | None) -> None:
    """Run one task: real task -> ghost branch + TASK.md -> ghost PR -> reverse-patch ->
    real-repo PR (human review). Fail closed."""
    try:
        from client_agent.graph import run_task
    except ImportError as exc:
        raise SystemExit("the agent workflow needs the [agents] extra:\n"
                         f"  pip install -e '.[agents]'\n  ({exc})")

    try:
        load_config(config_path)
    except ConfigError as exc:
        raise SystemExit(f"INVALID CONFIG\n{exc}")

    text = (click.get_text_stream("stdin").read() if task_path == "-"
            else Path(task_path).read_text(encoding="utf-8"))
    tid = task_id or "task-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]

    state = run_task(text, task_id=tid, real_repo=real_repo, ghost_tree=ghost_tree,
                     config_path=config_path, mapping_path=mapping_path,
                     audit_path=audit_path, workspace=workspace, backend=backend,
                     metrics_file=metrics_file)

    m = state.get("metrics", {})
    if state.get("rejected"):
        click.echo(f"REJECTED (fail closed): {state['rejected']}")
        click.echo(f"  wall-clock: {m.get('wall_clock_s')}s  (metrics + audit still written)")
        raise SystemExit(1)

    rp = state["real_pr"]
    click.echo(f"real PR opened: #{rp['id']}  {rp['ref']}  (branch {rp['branch']})")
    click.echo(f"  ghost PR:     #{state['ghost_pr']['id']}")
    click.echo(f"  consistency:  {m.get('consistency')}  {m.get('consistency_flags') or ''}")
    click.echo(f"  entities:     resolved={m.get('entities_resolved') or []}  "
               f"lossy={m.get('lossy_entities') or []}")
    click.echo(f"  llm:          {m.get('llm_model')}  {m.get('llm_tokens')} tok")
    click.echo(f"  wall-clock:   {m.get('wall_clock_s')}s")
    click.echo("  -> HUMAN REVIEW REQUIRED before merge")


@main.command("start")
@click.argument("spec")
@click.option("--full", is_flag=True,
              help="Run the whole pipeline (ghost PR, reverse-patch, real PR) instead of "
                   "stopping after the consultancy develops the ghost branch.")
@click.option("--config", "config_path", default=_WEBAPP_CONFIG, show_default=True,
              type=click.Path())
@click.option("--ghost-tree", default=_WEBAPP_GHOST, show_default=True, type=click.Path(),
              help="Ghost repo produced by `ghostc compile`.")
@click.option("--real-repo", default=_WEBAPP_REAL, show_default=True, type=click.Path())
@click.option("--mapping", "mapping_path", default=_WEBAPP_MAPPING, show_default=True,
              type=click.Path())
@click.option("--audit", "audit_path", default=_WEBAPP_AUDIT, show_default=True,
              type=click.Path())
@click.option("--consultancy-repo", default=None, type=click.Path(),
              help="The consultancy's own clone of the ghost origin "
                   "(default: <ghost-tree>/../ghost-consultancy). Reduced flow only.")
@click.option("--workspace", default=_AGENT_WORKSPACE, show_default=True, type=click.Path(),
              help="Throwaway git remotes for the --full pipeline only.")
@click.option("--backend", type=click.Choice(["auto", "claude", "stub"]),
              default="auto", show_default=True,
              help="LLM backend for the client's own nodes (consistency gate, in --full).")
@click.option("--consultancy-backend", type=click.Choice(["auto", "claude", "stub"]),
              default="stub", show_default=True,
              help="Backend the post-receive hook runs the consultancy agent with.")
@click.option("--metrics-file", default=None, type=click.Path(),
              help="Per-run metrics JSONL sink (default: metrics/agent-runs.jsonl "
                   "or $GHOSTC_METRICS_FILE). The post-receive hook forwards it so the "
                   "consultancy writes into the same sink.")
@click.option("--task-id", default=None, help="Override the id derived from the spec.")
def start_cmd(spec: str, full: bool, config_path: str, ghost_tree: str, real_repo: str,
              mapping_path: str, audit_path: str, consultancy_repo: str | None,
              workspace: str, backend: str, consultancy_backend: str,
              metrics_file: str | None, task_id: str | None) -> None:
    """Drive a spec file through the workflow: real task -> sanitized TASK.md on a ghost
    feature branch -> post-receive hook -> consultancy develops the branch (no PR)."""
    try:
        from client_agent.graph import run_task
    except ImportError as exc:
        raise SystemExit("the agent workflow needs the [agents] extra:\n"
                         f"  pip install -e '.[agents]'\n  ({exc})")

    try:
        load_config(config_path)
    except ConfigError as exc:
        raise SystemExit(f"INVALID CONFIG\n{exc}")

    text, spec_id, _stem = _resolve_spec(spec)
    tid = task_id or spec_id

    state = run_task(text, task_id=tid, real_repo=real_repo, ghost_tree=ghost_tree,
                     config_path=config_path, mapping_path=mapping_path,
                     audit_path=audit_path, workspace=workspace, backend=backend,
                     consultancy_backend=consultancy_backend,
                     consultancy_repo=consultancy_repo, metrics_file=metrics_file,
                     stop_after=None if full else "develop")

    m = state.get("metrics", {})
    if state.get("rejected"):
        click.echo(f"REJECTED (fail closed): {state['rejected']}")
        click.echo(f"  wall-clock: {m.get('wall_clock_s')}s  (metrics + audit still written)")
        raise SystemExit(1)

    if full:
        rp = state["real_pr"]
        click.echo(f"real PR opened: #{rp['id']}  {rp['ref']}  (branch {rp['branch']})")
        click.echo("  -> HUMAN REVIEW REQUIRED before merge")
        return
    branch = state["ghost_branch"]
    ghost = state.get("ghost_branch_in") or ghost_tree
    click.echo(f"ghost branch developed: {branch}   (in {ghost})")
    click.echo(f"  handoff commit (sanitized TASK.md, ghostc-client): "
               f"{(state.get('handoff_sha') or '')[:10]}")
    click.echo(f"  consultancy commit: {(state.get('consultancy_commit') or '')[:10]}  "
               f"(+{m.get('consultancy_commits', 0)} on top of TASK.md)")
    authors = m.get("consultancy_authors") or []
    if authors:
        click.echo(f"  authors on the branch: {', '.join(authors)}")
    click.echo(f"  substitutions: {m.get('substitutions')}   wall-clock: {m.get('wall_clock_s')}s")
    click.echo(f"  inspect:  git -C {ghost} log --stat {branch}")
    click.echo("  no PR (reduced flow) — run `client-agent open-real-pr <spec>` to "
               "reverse-compile the consultancy's work onto the real repo")


@main.command("open-real-pr")
@click.argument("spec")
@click.option("--config", "config_path", default=_WEBAPP_CONFIG, show_default=True,
              type=click.Path())
@click.option("--ghost-tree", default=_WEBAPP_GHOST, show_default=True, type=click.Path(),
              help="Ghost repo whose ghostc/task/<id> branch the consultancy developed.")
@click.option("--real-repo", default=_WEBAPP_REAL, show_default=True, type=click.Path())
@click.option("--mapping", "mapping_path", default=_WEBAPP_MAPPING, show_default=True,
              type=click.Path())
@click.option("--audit", "audit_path", default=_WEBAPP_AUDIT, show_default=True,
              type=click.Path())
@click.option("--task-id", default=None, help="Ghost branch id (default: from the spec).")
@click.option("--real-branch", default=None,
              help="Override the decoded real-repo branch name "
                   "(default: ghostc/real/<spec-name reverse-compiled through the mapping>).")
@click.option("--base", default=None, help="Base branch on the real repo (default: its HEAD).")
@click.option("--metrics-file", default=None, type=click.Path(),
              help="Per-run metrics JSONL sink (default: metrics/agent-runs.jsonl "
                   "or $GHOSTC_METRICS_FILE).")
def open_real_pr_cmd(spec: str, config_path: str, ghost_tree: str, real_repo: str,
                     mapping_path: str, audit_path: str, task_id: str | None,
                     real_branch: str | None, base: str | None,
                     metrics_file: str | None) -> None:
    """Simulate the forge webhook: reverse-compile the consultancy's ghost-branch
    implementation and open a decoded branch on the real repo for human review.

    Run this AFTER `client-agent start <spec>` (the consultancy must have developed
    `ghostc/task/<id>`). Fail-closed: on a reverse-patch rejection nothing is
    written to the real repo.
    """
    try:
        from client_agent.reverse_pr import NotReady, open_real_pr
        from ghostc.patch import Rejection
    except ImportError as exc:
        raise SystemExit("the agent workflow needs the [agents] extra:\n"
                         f"  pip install -e '.[agents]'\n  ({exc})")

    try:
        load_config(config_path)
    except ConfigError as exc:
        raise SystemExit(f"INVALID CONFIG\n{exc}")

    _text, spec_id, stem = _resolve_spec(spec)
    tid = task_id or spec_id

    try:
        row = open_real_pr(task_id=tid, spec_slug=stem, config_path=config_path,
                           ghost_tree=ghost_tree, real_repo=real_repo,
                           mapping_path=mapping_path, audit_path=audit_path,
                           real_branch=real_branch, base=base, metrics_file=metrics_file)
    except NotReady as exc:
        raise SystemExit(f"NOT READY: {exc}\n  run `client-agent start {spec}` first")
    except Rejection as rej:
        raise SystemExit(f"REJECTED (fail closed): {rej}\n"
                         "  nothing written to the real repo (metrics + audit recorded)")

    click.echo(f"real branch opened: {row['real_branch']}   (in {row['real_repo']})")
    click.echo(f"  reverse-compiled from: {row['ghost_branch']}  "
               f"commit {row['real_commit'][:10]} (ghostc-client)")
    click.echo(f"  entities resolved: {row['entities_resolved'] or []}   "
               f"lossy: {row['lossy_entities'] or []}")
    click.echo(f"  translated: {row['files']} file(s), {row['hunks']} hunk(s)   "
               f"wall-clock: {row['wall_clock_s']}s")
    click.echo(f"  inspect:  git -C {row['real_repo']} log --stat {row['real_branch']}")
    click.echo("  -> HUMAN REVIEW REQUIRED before merge (see PR_BODY.md on the branch)")


@main.command("print-graph")
@click.option("--out", default="client_agent/graph.md", show_default=True,
              type=click.Path(), help="Write a mermaid diagram of the StateGraph here.")
def print_graph(out: str) -> None:
    """Regenerate the mermaid diagram of the client StateGraph."""
    try:
        from client_agent.graph import graph_mermaid
    except ImportError as exc:
        raise SystemExit(f"needs the [agents] extra: pip install -e '.[agents]'  ({exc})")

    nodes_table = (
        "## Nodes\n\n"
        "| node | what it does | audit event(s) |\n"
        "|---|---|---|\n"
        "| `plan` | start the run, record backend + start time | `agent.task_started` |\n"
        "| `compile_spec` | `ghostc.spec.compile_spec` → sanitized `TASK.md`. **Fail-closed gate.** | `spec.compiled` / `spec.rejected` |\n"
        "| `handoff` | *(reduced)* in `../ghostc-demo/ghost`: branch `ghostc/task/<id>`, commit the sanitized `TASK.md` as `ghostc-client`, `git push -f origin` — which fires the bare origin's `post-receive` hook. *(full)* same via `LocalBareForge`. | `agent.spec_handoff` |\n"
        "| `await_consultancy` | *(reduced)* `git fetch origin`; confirm the hook's consultancy run pushed a commit on top of the `TASK.md` commit; `git branch -f` so it is checkoutable; record authors | `agent.consultancy_developed` |\n"
        "| `await_ghost_pr` | *(full)* consultancy implements + opens a **ghost PR** (`consultancy_agent.sim`) | `agent.ghost_pr_opened` |\n"
        "| `reverse_patch` | *(full)* `ghostc.patch.reverse_patch` ghost diff → real diff. **Fail-closed gate.** | `patch.*` |\n"
        "| `verify` | *(full)* `git apply --check` the real diff against the real repo | `verify.scan` / `verify.pass` / `verify.block` |\n"
        "| `consistency` | *(full)* LLM verdict: real diff vs. task | `consistency.verdict` |\n"
        "| `open_real_pr` | *(full)* apply the real diff, open a **real-repo PR**, flag for human review | `agent.real_pr_opened`, `approval.requested` |\n"
        "| `emit_metrics` | assemble the metrics row; also the sink for every fail-closed short-circuit | `agent.metrics`, `agent.task_completed` |\n\n"
        "Dotted edges are the fail-closed short-circuits: on any `Rejection` / block the "
        "run skips straight to `emit_metrics` and **no PR is opened**. `handoff` is the "
        "only node that writes to the ghost side — the privacy boundary is on that wire.\n")
    Path(out).write_text(
        "# Client agent — LangGraph\n\n"
        "Auto-generated by `ghostc-agent print-graph`. Topology in "
        "`client_agent/graph.py::_wire`.\n\n"
        "## Full pipeline (`run-task`)\n\n"
        f"```mermaid\n{graph_mermaid()}\n```\n\n"
        "## Reduced flow (`client-agent start`, hook-triggered, real repos)\n\n"
        "`handoff` commits + `git push -f origin` on `../ghostc-demo/ghost`; the bare "
        "origin's `post-receive` hook runs the consultancy agent against its own "
        "clone; `await_consultancy` fetches the branch back. No forge, no PR.\n\n"
        "The reverse-compile back to the real repo is a **separate** command, "
        "`client-agent open-real-pr <spec>` (`client_agent/reverse_pr.py`) — run after "
        "the consultancy has developed the ghost branch. It is not a graph node: it "
        "simulates a forge webhook firing into the company boundary "
        "(`git diff <handoff>..origin/ghostc/task/<id>` → `reverse_patch` → a decoded "
        "`ghostc/real/<name>` branch on `../ghostc-demo/real`).\n\n"
        f"```mermaid\n{graph_mermaid(reduced=True)}\n```\n\n"
        f"{nodes_table}", encoding="utf-8")
    click.echo(f"wrote {out}")


if __name__ == "__main__":
    main()
