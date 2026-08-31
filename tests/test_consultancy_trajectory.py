"""The consultancy agent's step trace — deliverable 04's "what the agent did".

Drives `_agent_loop` with a scripted LLM so the whole verification-feedback cycle
(premature `done` -> nudge -> run_tests -> accepted) is exercised offline, with no
API key and no cost.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from bridge.trajectory import open_trajectory

agent = pytest.importorskip("consultancy_agent.agent",
                            reason="the agent workflow needs the [agents] extra")


class ScriptedLLM:
    """Replays a fixed list of replies, one per turn."""

    model = "scripted"

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = 0

    def complete(self, *, system, user, max_tokens):  # noqa: ARG002 - signature parity
        self.seen += 1
        return SimpleNamespace(text=self.replies.pop(0) if self.replies else
                               json.dumps({"done": True, "summary": "out of script"}))


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / "ghost"
    root.mkdir()
    (root / "TASK.md").write_text("# Task\n\n## Acceptance criteria\n- AC1: add a file\n")
    return root


def _rows(path):
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def test_trace_records_tool_calls_and_their_observations(tmp_path, checkout):
    llm = ScriptedLLM([
        json.dumps({"tool": "list_files", "args": {"dir": "."}}),
        json.dumps({"tool": "write_file", "args": {"path": "a.js", "content": "x"}}),
        json.dumps({"done": True, "summary": "done"}),
    ])
    trace = open_trajectory("t", {"agent": "consultancy"}, path=tmp_path / "tr")
    agent._agent_loop(llm, checkout, "task", trace=trace)

    rows = _rows(trace.path)
    steps = [r for r in rows if r["kind"] == "step"]
    assert [s["tool"] for s in steps][:2] == ["list_files", "write_file"]
    assert "TASK.md" in steps[0]["observation"]           # the tool actually responded
    assert "wrote a.js" in steps[1]["observation"]
    assert (checkout / "a.js").exists()


def test_trace_records_the_nudge_that_shaped_the_next_step(tmp_path, checkout):
    """`done` before tests are green must be refused, and the refusal recorded."""
    llm = ScriptedLLM([
        json.dumps({"tool": "write_file", "args": {"path": "a.js", "content": "x"}}),
        json.dumps({"done": True, "summary": "too early"}),
        json.dumps({"tool": "list_files", "args": {"dir": "."}}),
    ])
    trace = open_trajectory("t", {}, path=tmp_path / "tr")
    agent._agent_loop(llm, checkout, "task", trace=trace)

    notes = [r for r in _rows(trace.path) if r["kind"] == "note"]
    premature = [n for n in notes if n.get("cause") == "premature_done"]
    assert premature, "the refusal of a premature done must appear in the trace"
    assert "NOT done" in premature[0]["text"]
    assert premature[0]["tests_green"] is False


def test_trace_records_an_unparseable_reply(tmp_path, checkout):
    llm = ScriptedLLM(["not json at all",
                       json.dumps({"tool": "list_files", "args": {"dir": "."}})])
    trace = open_trajectory("t", {}, path=tmp_path / "tr")
    agent._agent_loop(llm, checkout, "task", trace=trace)

    causes = [r.get("cause") for r in _rows(trace.path) if r["kind"] == "note"]
    assert "unparseable_reply" in causes


def test_loop_runs_unchanged_without_a_trace(tmp_path, checkout):
    """Tracing is optional — the agent must behave identically with trace=None."""
    script = [json.dumps({"tool": "write_file", "args": {"path": "a.js", "content": "x"}}),
              json.dumps({"done": True, "summary": "s"})]
    changed, steps, _ = agent._agent_loop(ScriptedLLM(list(script)), checkout, "task")
    assert changed == {"a.js"} and steps >= 1


def test_write_file_content_is_clipped_in_the_trace(tmp_path, checkout):
    """A trace must not become a second copy of the repo."""
    llm = ScriptedLLM([json.dumps({"tool": "write_file",
                                   "args": {"path": "big.js", "content": "z" * 20000}}),
                       json.dumps({"done": True, "summary": "s"})])
    trace = open_trajectory("t", {}, path=tmp_path / "tr")
    agent._agent_loop(llm, checkout, "task", trace=trace)

    step = next(r for r in _rows(trace.path) if r["kind"] == "step")
    assert len(step["args"]["content"]) < 1000
    assert (checkout / "big.js").read_text() == "z" * 20000   # the real write is full
