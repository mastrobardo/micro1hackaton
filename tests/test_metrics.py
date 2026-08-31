"""bridge.metrics — the append-only per-run metrics sink."""
from __future__ import annotations

import json

import pytest

from bridge.metrics import metrics_path, record_run


def _rows(p) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_record_run_appends_one_json_line_and_stamps_schema_and_ts(tmp_path):
    sink = tmp_path / "runs.jsonl"
    record_run({"role": "client", "command": "start", "outcome": "ok"}, path=sink)
    record_run({"role": "consultancy", "command": "start", "outcome": "ok"}, path=sink)

    rows = _rows(sink)
    assert [r["role"] for r in rows] == ["client", "consultancy"]
    assert all(r["schema"] == 1 and "T" in r["ts"] for r in rows)


def test_record_run_creates_missing_parent_dirs(tmp_path):
    sink = tmp_path / "nested" / "deep" / "runs.jsonl"
    record_run({"role": "client"}, path=sink)
    assert sink.is_file() and _rows(sink)[0]["role"] == "client"


def test_explicit_path_beats_env_beats_default(tmp_path, monkeypatch):
    env_sink = tmp_path / "from-env.jsonl"
    arg_sink = tmp_path / "from-arg.jsonl"
    monkeypatch.setenv("GHOSTC_METRICS_FILE", str(env_sink))

    assert metrics_path() == env_sink
    assert metrics_path(arg_sink) == arg_sink

    record_run({"role": "client"})              # -> env
    record_run({"role": "client"}, path=arg_sink)
    assert env_sink.is_file() and arg_sink.is_file()

    monkeypatch.delenv("GHOSTC_METRICS_FILE")
    assert metrics_path() == pytest.importorskip("pathlib").Path("metrics/agent-runs.jsonl")


def test_caller_fields_win_over_the_auto_stamped_ones(tmp_path):
    sink = tmp_path / "runs.jsonl"
    record_run({"schema": 99, "ts": "custom", "role": "client"}, path=sink)
    r = _rows(sink)[0]
    assert r["schema"] == 99 and r["ts"] == "custom"
