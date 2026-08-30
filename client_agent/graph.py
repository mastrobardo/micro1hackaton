"""The client-side orchestrator as a LangGraph ``StateGraph``.

Runs inside the company trust boundary. One task in, one real-repo PR out:

    plan → compile_spec → [leak gate] → handoff (ghost branch + TASK.md)
         → await_ghost_pr → reverse_patch → verify → consistency
         → open_real_pr → emit_metrics

``compile_spec`` and ``reverse_patch`` are the fail-closed gates: on a
:class:`ghostc.spec.Rejection` / :class:`ghostc.patch.Rejection` the run
short-circuits to ``emit_metrics`` (which records the failure) and no real PR is
opened. Every node emits an audit event; the metrics row is derived from the log.
A rendered diagram lives at ``client_agent/graph.md`` (regenerate with
``python -m client_agent print-graph``).

Phase B note: ``await_ghost_pr`` calls an injected consultancy callable
(:func:`consultancy_agent.sim.run_consultancy` by default). Phase D turns this
into a real ``interrupt()`` resumed by a git hook.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Callable

from langgraph.graph import END, START, StateGraph

from bridge.forge import LocalBareForge
from bridge.llm import configure_langsmith, get_llm
from client_agent.state import TaskState, new_state
from consultancy_agent.sim import run_consultancy
from ghostc.audit import AuditLog, new_operation_id
from ghostc.mapping import MappingStore
from ghostc.patch import Rejection as PatchRejection
from ghostc.patch import reverse_patch
from ghostc.spec import Rejection as SpecRejection
from ghostc.spec import compile_spec

ConsultancyFn = Callable[..., str]

_CONSISTENCY_SYS = (
    "You are a code-review gate. Given an implementation task and a unified diff, "
    "decide whether the diff plausibly implements the task and nothing more. "
    'Reply with ONLY compact JSON: {"verdict": "consistent" | "flagged", '
    '"flags": ["<short reason>", ...]}.'
)


def _merge_metrics(state: TaskState, **kw) -> dict:
    return {**state.get("metrics", {}), **kw}


def _git(cwd: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, input=stdin,
                          capture_output=True, text=True)


def _wire(g: StateGraph) -> None:
    """Fixed edge topology — shared by the live graph and the diagram renderer."""
    g.add_edge(START, "plan")
    g.add_edge("plan", "compile_spec")
    g.add_conditional_edges("compile_spec", _after_spec,
                            {"handoff": "handoff", "emit_metrics": "emit_metrics"})
    g.add_edge("handoff", "await_ghost_pr")
    g.add_edge("await_ghost_pr", "reverse_patch")
    g.add_conditional_edges("reverse_patch", _after_reverse,
                            {"verify": "verify", "emit_metrics": "emit_metrics"})
    g.add_conditional_edges("verify", _after_verify,
                            {"consistency": "consistency", "emit_metrics": "emit_metrics"})
    g.add_edge("consistency", "open_real_pr")
    g.add_edge("open_real_pr", "emit_metrics")
    g.add_edge("emit_metrics", END)


def _after_spec(state: TaskState) -> str:
    return "emit_metrics" if state.get("rejected") else "handoff"


def _after_reverse(state: TaskState) -> str:
    return "emit_metrics" if state.get("rejected") else "verify"


def _after_verify(state: TaskState) -> str:
    return "emit_metrics" if state.get("rejected") else "consistency"


def build_client_graph(*, forge: LocalBareForge, audit: AuditLog, config_path: str,
                       mapping_path: str, audit_path: str, real_repo: str,
                       scratch: Path, backend: str,
                       consultancy_fn: ConsultancyFn):
    llm = get_llm(backend)
    mapping_version = MappingStore(mapping_path).data.get("mapping_version", 1)

    def plan(state: TaskState) -> dict:
        audit.emit("agent.task_started", "client_agent",
                   details={"task_id": state["task_id"], "backend": backend})
        return {"metrics": _merge_metrics(state, started_at=time.time(),
                                          llm_model=llm.model, llm_tokens=0)}

    def compile_spec_node(state: TaskState) -> dict:
        out = scratch / f"{state['task_id']}.TASK.md"
        try:
            gs = compile_spec(state["real_task"], config_path=config_path,
                              mapping_path=mapping_path, audit_path=audit_path,
                              operation_id=audit.operation_id, out_path=str(out))
        except SpecRejection as rej:
            return {"rejected": f"spec: {rej}"}
        return {"ghost_task": gs.ghost_task,
                "substitutions": [s.to_dict() for s in gs.substitutions]}

    def handoff(state: TaskState) -> dict:
        branch = f"ghostc/task/{state['task_id']}"
        forge.create_branch("ghost", branch)
        task_md = (scratch / f"{state['task_id']}.TASK.md").read_text(encoding="utf-8")
        forge.commit_file("ghost", branch, "TASK.md", task_md,
                          f"task: {state['task_id']}")
        forge.push("ghost", branch)
        audit.emit("agent.spec_handoff", "client_agent",
                   details={"task_id": state["task_id"], "branch": branch,
                            "substitutions": len(state.get("substitutions", []))})
        return {"ghost_branch": branch}

    def await_ghost_pr(state: TaskState) -> dict:
        pr_id = consultancy_fn(forge, "ghost", task_branch=state["ghost_branch"],
                               impl_branch=f"ghostc/impl/{state['task_id']}",
                               task_id=state["task_id"], ghost_task=state["ghost_task"],
                               substitutions=state.get("substitutions", []))
        pr = forge.get_pr("ghost", pr_id)
        audit.emit("agent.ghost_pr_opened", "consultancy_agent",
                   details={"task_id": state["task_id"], "pr": pr.id,
                            "ref": pr.ref, "files": pr.diff.count("\ndiff --git ") + 1})
        return {"ghost_pr": pr.to_dict()}

    def reverse_patch_node(state: TaskState) -> dict:
        diff_path = scratch / f"{state['task_id']}.ghost-pr.diff"
        diff_path.write_text(state["ghost_pr"]["diff"], encoding="utf-8")
        try:
            res = reverse_patch(str(diff_path), mapping_path, config_path=config_path,
                                mapping_version=mapping_version, do_apply=False,
                                audit_path=audit_path)
        except PatchRejection as rej:
            return {"rejected": f"reverse-patch: {rej}"}
        return {"real_diff": res.real_diff,
                "metrics": _merge_metrics(state, entities_resolved=res.entities_resolved,
                                          lossy_entities=res.lossy_entities,
                                          files=res.files, hunks=res.hunks)}

    def verify_node(state: TaskState) -> dict:
        chk = _git(Path(real_repo), "apply", "--check", "--whitespace=nowarn", "-",
                   stdin=state["real_diff"])
        ok = chk.returncode == 0
        audit.emit("verify.scan", "verifier",
                   details={"check": "real_diff_applies", "ok": ok})
        if not ok:
            audit.emit("verify.block", "verifier", decision="block",
                       details={"detail": (chk.stderr or chk.stdout).strip()[:400]})
            return {"rejected": "verify: real diff does not apply cleanly"}
        audit.emit("verify.pass", "verifier", details={"check": "real_diff_applies"})
        return {"metrics": _merge_metrics(state, real_diff_applies=True)}

    def consistency_node(state: TaskState) -> dict:
        prompt = (f"TASK:\n{state['real_task']}\n\nDIFF:\n{state['real_diff'][:8000]}\n\n"
                  "Is the diff consistent with the task?")
        reply = llm.complete(system=_CONSISTENCY_SYS, user=prompt, max_tokens=512)
        verdict, flags = _parse_verdict(reply.text)
        audit.emit("consistency.verdict", "consistency", decision=verdict,
                   details={"task_id": state["task_id"], "flags": flags,
                            "model": reply.model})
        return {"metrics": _merge_metrics(
            state, consistency=verdict, consistency_flags=flags,
            llm_tokens=state.get("metrics", {}).get("llm_tokens", 0) + reply.total_tokens)}

    def open_real_pr(state: TaskState) -> dict:
        branch = f"ghostc/real/{state['task_id']}"
        forge.create_branch("real", branch)
        forge.apply_diff("real", branch, state["real_diff"], f"apply: {state['task_id']}")
        forge.push("real", branch)
        m = state.get("metrics", {})
        body = (f"Reverse-compiled from ghost PR #{state['ghost_pr']['id']}.\n\n"
                f"- consistency: **{m.get('consistency', 'n/a')}** "
                f"{m.get('consistency_flags') or ''}\n"
                f"- entities resolved: {m.get('entities_resolved') or []}\n"
                f"- lossy (verify prose): {m.get('lossy_entities') or []}\n\n"
                f"**HUMAN REVIEW REQUIRED** before merge.")
        pr = forge.open_pr("real", branch=branch, base="main",
                           title=f"[real] {state['task_id']}", body=body)
        audit.emit("agent.real_pr_opened", "client_agent",
                   details={"task_id": state["task_id"], "pr": pr.id, "ref": pr.ref})
        audit.emit("approval.requested", "orchestrator", actor="system",
                   decision="pending",
                   details={"gate": "real_pr_review", "pr": pr.id})
        return {"real_pr": pr.to_dict(),
                "approvals": state.get("approvals", []) +
                [{"gate": "real_pr_review", "status": "pending", "pr": pr.id}]}

    def emit_metrics(state: TaskState) -> dict:
        m = dict(state.get("metrics", {}))
        started = m.pop("started_at", None)
        m.update(task_id=state["task_id"], rejected=state.get("rejected"),
                 substitutions=len(state.get("substitutions", [])),
                 ghost_pr=(state.get("ghost_pr") or {}).get("id"),
                 real_pr=(state.get("real_pr") or {}).get("id"),
                 wall_clock_s=round(time.time() - started, 3) if started else None)
        audit.emit("agent.metrics", "client_agent", details=m)
        audit.emit("agent.task_completed", "client_agent",
                   decision="rejected" if state.get("rejected") else "ok",
                   details={"task_id": state["task_id"],
                            "rejected": state.get("rejected")})
        return {"metrics": m}

    g = StateGraph(TaskState)
    for name, fn in [("plan", plan), ("compile_spec", compile_spec_node),
                     ("handoff", handoff), ("await_ghost_pr", await_ghost_pr),
                     ("reverse_patch", reverse_patch_node), ("verify", verify_node),
                     ("consistency", consistency_node), ("open_real_pr", open_real_pr),
                     ("emit_metrics", emit_metrics)]:
        g.add_node(name, fn)
    _wire(g)
    return g.compile()


def graph_mermaid() -> str:
    """Render the fixed graph topology as a mermaid diagram (no deps needed)."""
    g = StateGraph(TaskState)
    for name in ["plan", "compile_spec", "handoff", "await_ghost_pr", "reverse_patch",
                 "verify", "consistency", "open_real_pr", "emit_metrics"]:
        g.add_node(name, lambda s: {})
    _wire(g)
    return g.compile().get_graph().draw_mermaid()


def _parse_verdict(text: str) -> tuple[str, list[str]]:
    import json
    import re

    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            v = str(obj.get("verdict", "flagged")).lower()
            flags = [str(f) for f in obj.get("flags", [])]
            return ("consistent" if v == "consistent" else "flagged", flags)
        except ValueError:
            pass
    return ("flagged", ["unparseable consistency reply"])


def run_task(real_task: str, *, task_id: str, real_repo: str, ghost_tree: str,
             config_path: str = "privacy.yaml",
             mapping_path: str = "workspace/private/mapping.json",
             audit_path: str = "workspace/private/audit.jsonl",
             workspace: str = "workspace/agent", backend: str = "auto",
             consultancy_fn: ConsultancyFn = run_consultancy) -> TaskState:
    """Run one task through the full client workflow. Returns the final state."""
    for p, label in [(real_repo, "real repo"), (ghost_tree, "ghost tree"),
                     (mapping_path, "mapping store")]:
        if not Path(p).exists():
            raise SystemExit(f"{label} not found: {p} (run `ghostc compile` first)")

    configure_langsmith()
    ws = Path(workspace)
    scratch = ws / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)

    forge = LocalBareForge(ws / "remotes")
    forge.ensure_repo("ghost")
    forge.seed_from("ghost", Path(ghost_tree), "ghost baseline")
    forge.ensure_repo("real")
    forge.seed_from("real", Path(real_repo), "real baseline")

    audit = AuditLog(audit_path, new_operation_id())
    graph = build_client_graph(
        forge=forge, audit=audit, config_path=config_path, mapping_path=mapping_path,
        audit_path=audit_path, real_repo=real_repo, scratch=scratch, backend=backend,
        consultancy_fn=consultancy_fn)
    return graph.invoke(new_state(task_id, real_task))
