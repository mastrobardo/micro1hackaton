"""Client orchestrator (LangGraph): full loop on a synthetic fixture + fail-closed."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("langgraph")

from client_agent.graph import run_task          # noqa: E402
from ghostc.spec import Rejection as SpecRejection  # noqa: E402
from ghostc.mapping import MappingStore                   # noqa: E402

TASK = ("Add a GET /healthz endpoint for Northwind Airlines that pings the "
        "booking-core service and returns 200.")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                        "HOME": str(cwd), "PATH": __import__("os").environ["PATH"]})


@pytest.fixture
def bench(tmp_path, privacy_yaml):
    real = tmp_path / "real"
    (real / "src").mkdir(parents=True)
    (real / "README.md").write_text("# demo service\n", encoding="utf-8")
    (real / "src" / "app.js").write_text("const app = express();\n", encoding="utf-8")
    _git(real, "init", "-q", "-b", "main")
    _git(real, "add", "-A")
    _git(real, "commit", "-q", "-m", "init")

    ghost = tmp_path / "ghost"
    (ghost / "src").mkdir(parents=True)
    (ghost / "README.md").write_text("# demo service\n", encoding="utf-8")
    (ghost / "src" / "app.js").write_text("const app = express();\n", encoding="utf-8")

    private = tmp_path / "private"
    store = MappingStore(private / "mapping.json")
    store.upsert(entity_id="client_northwind", real="Northwind Airlines", ghost="client-a",
                 kind="client", level="restricted", strategy="synthetic_id")
    store.upsert(entity_id="svc_booking_core", real="booking-core", ghost="service-a",
                 kind="internal_service", level="confidential", strategy="semantic_alias")
    store.save()

    return {
        "real_repo": str(real), "ghost_tree": str(ghost),
        "config_path": str(privacy_yaml),
        "mapping_path": str(private / "mapping.json"),
        "audit_path": str(private / "audit.jsonl"),
        "workspace": str(tmp_path / "agent"),
    }


def _events(audit_path: str) -> list[str]:
    return [json.loads(l)["event"]
            for l in Path(audit_path).read_text(encoding="utf-8").splitlines() if l.strip()]


def test_full_loop_opens_a_real_pr(bench):
    state = run_task(TASK, task_id="healthz", backend="stub", **bench)

    assert not state.get("rejected")
    assert state["ghost_pr"]["id"] and state["real_pr"]["id"]
    assert state["real_pr"]["ref"].startswith("refs/ghostc/pr/")

    m = state["metrics"]
    assert m["consistency"] == "consistent"          # StubLLM verdict
    assert m["real_diff_applies"] is True
    assert set(m["entities_resolved"]) & {"client_northwind", "svc_booking_core"}
    assert m["wall_clock_s"] is not None

    ev = _events(bench["audit_path"])
    for e in ("agent.task_started", "spec.compiled", "screen.scanned", "agent.spec_handoff",
              "agent.ghost_pr_opened", "consistency.verdict", "agent.real_pr_opened",
              "approval.requested", "agent.metrics", "agent.task_completed"):
        assert e in ev, f"missing audit event {e}"


def test_real_diff_is_translated_back_but_ghost_pr_stays_sanitized(bench):
    state = run_task(TASK, task_id="healthz", backend="stub", **bench)

    # real diff is boundary-internal -> carries the real spellings
    assert "Northwind Airlines" in state["real_diff"] or "booking-core" in state["real_diff"]
    # the ghost PR the consultancy saw does NOT
    assert "Northwind" not in state["ghost_pr"]["diff"]
    assert "booking-core" not in state["ghost_pr"]["diff"]


def test_spec_rejection_fails_closed(bench, monkeypatch):
    def boom(*a, **k):
        raise SpecRejection("real value survived", "forced in test")

    monkeypatch.setattr("client_agent.graph.compile_spec", boom)
    state = run_task(TASK, task_id="rej", backend="stub", **bench)

    assert state.get("rejected", "").startswith("spec:")
    assert state.get("real_pr") is None
    ev = _events(bench["audit_path"])
    assert "agent.metrics" in ev and "agent.task_completed" in ev
    assert "agent.real_pr_opened" not in ev


def test_missing_precondition_is_a_clean_error(bench):
    bench["mapping_path"] = bench["mapping_path"] + ".nope"
    with pytest.raises(SystemExit):
        run_task(TASK, task_id="x", backend="stub", **bench)


# --- the screen gate (unknown entities the closed-world compiler cannot see) --- #

LEAKY = ("Add a GET /healthz endpoint for Northwind Airlines that also pings "
         "gw.prod.contoso.internal and returns 200.")


def test_screen_blocks_an_unknown_entity_before_the_handoff(bench):
    """`gw.prod.contoso.internal` is in neither privacy.yaml nor the mapping, so
    compile_spec passes it through untouched and its leak scan cannot see it. The
    screen is what stops it — before `handoff`, the only node that writes ghost-side."""
    state = run_task(LEAKY, task_id="leak", backend="stub", **bench)

    assert state.get("rejected", "").startswith("screen:")
    assert state.get("ghost_branch") is None and state.get("real_pr") is None
    m = state["metrics"]
    assert m["screen_blocked"] is True and m["screen_findings"] >= 1
    assert m["screen_llm"] == "skipped"          # stub backend -> deterministic only

    ev = _events(bench["audit_path"])
    assert "screen.scanned" in ev and "screen.blocked" in ev
    assert "agent.spec_handoff" not in ev and "agent.real_pr_opened" not in ev


def test_screen_findings_stay_boundary_internal(bench):
    state = run_task(LEAKY, task_id="leak", backend="stub", **bench)
    # the findings name the real surface ...
    assert any("contoso" in f["surface"] for f in state["screen_findings"])
    # ... the audit log and the metrics row do not
    assert "contoso" not in Path(bench["audit_path"]).read_text(encoding="utf-8")
    assert "contoso" not in json.dumps(state["metrics"])


def test_warn_mode_records_without_gating(bench):
    state = run_task(LEAKY, task_id="warn", backend="stub", screen_mode="warn", **bench)
    assert not state.get("rejected")
    assert state["real_pr"]["id"] and state["metrics"]["screen_findings"] >= 1
    assert state["metrics"]["screen_blocked"] is False


def test_screen_off_skips_the_gate(bench):
    state = run_task(LEAKY, task_id="off", backend="stub", screen_mode="off", **bench)
    assert not state.get("rejected") and state["metrics"]["screen_findings"] == 0


def test_reviewer_ignore_lets_the_run_through(bench, tmp_path):
    """The review board closes the loop: a cleared false positive stops gating."""
    from ghostc.review.store import DecisionStore

    d = tmp_path / "decisions.jsonl"
    DecisionStore(d).record(surface="gw.prod.contoso.internal", reviewer_action="ignore",
                            proposed_action="review", note="decommissioned host")
    state = run_task(LEAKY, task_id="cleared", backend="stub",
                     decisions_path=str(d), **bench)
    assert not state.get("rejected") and state["real_pr"]["id"]
    assert state["metrics"]["screen_suppressed"] == 1


def test_findings_file_feeds_the_review_board(bench, tmp_path):
    out = tmp_path / "screen-findings.jsonl"
    run_task(LEAKY, task_id="f", backend="stub", findings_path=str(out), **bench)
    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert rows and rows[0]["source"] == "ghost_task"


def test_adjudicator_failure_is_reported_as_error_not_ran(bench, monkeypatch):
    """A blown-up adjudicator must not be recorded as a clean run — the cost fields
    are merged back onto the result, the status is not."""
    import client_agent.graph as g

    class Boom:
        model = "fake"

        def __call__(self, ghost, real):
            raise RuntimeError("529 overloaded")

        def info(self):
            return {"status": "ran", "model": "fake", "calls": 1, "tokens": 7}

    monkeypatch.setattr(g, "build_adjudicator",
                        lambda backend, mode: (Boom(), {"status": "ran"}))
    state = run_task(TASK, task_id="boom", backend="stub", **bench)
    assert state["metrics"]["screen_llm"] == "error"
    assert state["metrics"]["llm_tokens"] >= 7      # the cost still counted
