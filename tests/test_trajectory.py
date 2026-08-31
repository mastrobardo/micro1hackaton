"""bridge.trajectory — the per-step agent trajectory sink (deliverable 04)."""
from __future__ import annotations

import json

import pytest

from bridge.trajectory import _clip, open_trajectory, trajectory_dir


def _rows(path):
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def test_writes_meta_steps_notes_and_end_in_order(tmp_path):
    t = open_trajectory("branch-x", {"agent": "consultancy"}, path=tmp_path)
    t.step(1, tool="list_files", args={"dir": "."}, observation="src/\npackage.json")
    t.note(2, "you are NOT done", cause="premature_done")
    t.step(3, tool="run_tests", args={}, observation="exit=0", tests_green=True)
    t.end(outcome="ok", steps=3)

    rows = _rows(t.path)
    assert [r["kind"] for r in rows] == ["meta", "step", "note", "step", "end"]
    assert rows[0]["agent"] == "consultancy"
    assert rows[1]["tool"] == "list_files" and rows[1]["args"] == {"dir": "."}
    assert rows[2]["cause"] == "premature_done"
    assert rows[3]["tests_green"] is True
    assert rows[4]["outcome"] == "ok"
    assert all("ts" in r and r["schema"] == 1 for r in rows)


def test_long_fields_are_clipped_not_mirrored(tmp_path):
    """A write_file arg is a whole file; the trace must stay a trace."""
    t = open_trajectory("b", {}, path=tmp_path)
    t.step(1, tool="write_file", args={"content": "x" * 5000}, observation="y" * 5000)
    row = _rows(t.path)[1]
    assert len(row["args"]["content"]) < 1000
    assert row["args"]["content"].endswith("chars]")
    assert len(row["observation"]) < 1000


def test_refuses_to_write_inside_the_working_repo(tmp_path):
    """`git add -A` in the agent's checkout would commit and push the trace."""
    repo = tmp_path / "ghost"
    repo.mkdir()
    with pytest.raises(ValueError, match="refusing to write a trajectory inside"):
        open_trajectory("b", {}, path=repo, forbid_inside=repo)


def test_allows_a_path_outside_the_working_repo(tmp_path):
    repo = tmp_path / "ghost"
    repo.mkdir()
    t = open_trajectory("b", {}, path=tmp_path / "traces", forbid_inside=repo)
    assert t.path.exists()


def test_dir_resolution_prefers_explicit_then_env_then_metrics_sibling(tmp_path, monkeypatch):
    monkeypatch.delenv("GHOSTC_TRAJECTORY_DIR", raising=False)
    monkeypatch.delenv("GHOSTC_METRICS_FILE", raising=False)
    assert trajectory_dir(tmp_path) == tmp_path

    monkeypatch.setenv("GHOSTC_TRAJECTORY_DIR", str(tmp_path / "env"))
    assert trajectory_dir() == tmp_path / "env"

    monkeypatch.delenv("GHOSTC_TRAJECTORY_DIR")
    monkeypatch.setenv("GHOSTC_METRICS_FILE", str(tmp_path / "m" / "runs.jsonl"))
    assert trajectory_dir() == tmp_path / "m" / "trajectories"


def test_name_is_slugified_into_a_safe_filename(tmp_path):
    t = open_trajectory("ghostc/task/001-add x", {}, path=tmp_path)
    assert "/" not in t.path.name and t.path.name.endswith(".jsonl")


def test_clip_recurses_into_nested_dicts():
    out = _clip({"a": {"b": "z" * 5000}})
    assert len(out["a"]["b"]) < 1000


def test_bridge_trajectory_is_stdlib_only():
    """consultancy_agent may import bridge — bridge must not drag in heavy deps."""
    import bridge.trajectory as mod
    src = (mod.__file__ or "")
    assert src.endswith("trajectory.py")
    text = open(src, encoding="utf-8").read()
    for forbidden in ("import anthropic", "import langsmith", "from ghostc",
                      "import langgraph"):
        assert forbidden not in text
