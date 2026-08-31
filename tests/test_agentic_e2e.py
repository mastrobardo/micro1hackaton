"""Reduced, hook-triggered end-to-end flow on the REAL repos:

    client-agent start  ->  ghost repo: branch ghostc/task/<id> + sanitized TASK.md,
    `git push origin` -> bare origin's post-receive hook runs `consultancy-agent start`
    against its own clone -> consultancy commits (as a different git identity) + pushes
    -> client fetches the branch back.  STOP (no PR).

Offline + deterministic: the consultancy runs with `--backend stub`.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("langgraph")
pytest.importorskip("dotenv")

from client_agent.graph import run_task                       # noqa: E402
from ghostc.mapping import MappingStore                        # noqa: E402

TASK = ("Add a GET /healthz endpoint for Northwind Airlines that pings the "
        "booking-core service and returns 200.")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True,
        env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        | {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}).stdout


@pytest.fixture
def bench(tmp_path, privacy_yaml):
    demo = tmp_path / "ghostc-demo"
    ghost = demo / "ghost"
    (ghost / "src").mkdir(parents=True)
    (ghost / "README.md").write_text("# demo service\n", encoding="utf-8")
    (ghost / "src" / "app.js").write_text("const app = express();\n", encoding="utf-8")
    _git(ghost, "init", "-q", "-b", "main")
    _git(ghost, "add", "-A")
    _git(ghost, "commit", "-q", "-m", "ghost baseline (ghostc compile)")

    private = tmp_path / "private"
    store = MappingStore(private / "mapping.json")
    store.upsert(entity_id="client_northwind", real="Northwind Airlines", ghost="client-a",
                 kind="client", level="restricted", strategy="synthetic_id")
    store.upsert(entity_id="svc_booking_core", real="booking-core", ghost="service-a",
                 kind="internal_service", level="confidential", strategy="semantic_alias")
    store.save()

    return {
        "kw": {
            "real_repo": str(tmp_path / "unused-real"),
            "ghost_tree": str(ghost),
            "config_path": str(privacy_yaml),
            "mapping_path": str(private / "mapping.json"),
            "audit_path": str(private / "audit.jsonl"),
            "scratch_dir": str(tmp_path / "scratch"),
        },
        "ghost": ghost,
        "demo": demo,
    }


def _events(audit_path: str) -> list[str]:
    return [json.loads(l)["event"]
            for l in Path(audit_path).read_text(encoding="utf-8").splitlines() if l.strip()]


def _metric_rows() -> list[dict]:
    p = Path(os.environ["GHOSTC_METRICS_FILE"])          # redirected per-test by conftest
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] \
        if p.exists() else []


def test_reduced_flow_hook_develops_the_ghost_branch(bench):
    ghost = bench["ghost"]
    state = run_task(TASK, task_id="healthz", backend="stub",
                     stop_after="develop", consultancy_backend="stub", **bench["kw"])

    assert not state.get("rejected")
    assert state["consultancy_pushed"] is True
    assert state.get("real_pr") is None and state.get("ghost_pr") is None
    assert state["ghost_branch"] == "ghostc/task/healthz"
    assert state["ghost_branch_in"] == str(ghost)

    # the branch is a real branch on the real ghost repo (via its bare origin)
    _git(ghost, "fetch", "-q", "origin")
    log = _git(ghost, "log", "--format=%s|%an",
               "origin/ghostc/task/healthz").splitlines()
    assert log[0].split("|")[0] == "impl: ghostc/task/healthz"      # consultancy
    assert log[1] == "task: healthz|ghostc-client"                  # client handoff
    # two distinct actors on the branch
    assert log[0].split("|")[1] == "Consultancy Dev"
    assert set(state["metrics"]["consultancy_authors"]) == {"Consultancy Dev"}

    files = _git(ghost, "show", "--name-only", "--format=", "origin/ghostc/task/healthz")
    assert "IMPL_NOTES.md" in files
    # checkoutable locally, not just as origin/*
    assert "ghostc/task/healthz" in _git(ghost, "branch", "--list", "ghostc/task/healthz")

    m = state["metrics"]
    assert m["consultancy_pushed"] is True and m["consultancy_commits"] == 1
    assert m["real_pr"] is None and m["wall_clock_s"] is not None

    # the bare origin + the consultancy's own clone exist beside the ghost repo
    assert (bench["demo"] / "ghost.git").is_dir()
    assert (bench["demo"] / "ghost-consultancy" / ".git").is_dir()

    ev = _events(bench["kw"]["audit_path"])
    for e in ("agent.task_started", "spec.compiled", "agent.spec_handoff",
              "agent.consultancy_developed", "agent.metrics", "agent.task_completed"):
        assert e in ev, f"missing audit event {e}"
    assert "agent.real_pr_opened" not in ev and "agent.ghost_pr_opened" not in ev

    # every agent run appends one row to the shared metrics sink — the client's
    # consolidated row plus the consultancy's own (via the post-receive hook, which
    # exports GHOSTC_METRICS_FILE so both write to the same file)
    rows = _metric_rows()
    by_role = {r["role"] for r in rows}
    assert by_role == {"client", "consultancy"}
    client_row = next(r for r in rows if r["role"] == "client")
    assert client_row["command"] == "start" and client_row["flow"] == "reduced"
    assert client_row["outcome"] == "ok" and client_row["task_id"] == "healthz"
    cons_row = next(r for r in rows if r["role"] == "consultancy")
    assert cons_row["task_branch"] == "ghostc/task/healthz" and cons_row["outcome"] == "ok"


def test_reduced_flow_is_idempotent_and_leak_free(bench):
    ghost = bench["ghost"]
    run_task(TASK, task_id="healthz", backend="stub",
             stop_after="develop", consultancy_backend="stub", **bench["kw"])
    # a second run must not choke on the stale task branch
    state = run_task(TASK, task_id="healthz", backend="stub",
                     stop_after="develop", consultancy_backend="stub", **bench["kw"])
    assert not state.get("rejected") and state["consultancy_pushed"] is True

    _git(ghost, "fetch", "-q", "origin")
    blob = _git(ghost, "show", "origin/ghostc/task/healthz:TASK.md")
    blob += _git(ghost, "show", "origin/ghostc/task/healthz:IMPL_NOTES.md")
    assert "Northwind" not in blob and "booking-core" not in blob
    # the ghost repo's own worktree is back on main, untouched
    assert _git(ghost, "rev-parse", "--abbrev-ref", "HEAD").strip() == "main"
