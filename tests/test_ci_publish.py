"""`client_agent.publish` — PR body / title / branch resolution from the metrics
sink, plus the CI leak-count regression gate. Pure stdlib, no network, no `gh`."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from client_agent import publish

_ROWS = [
    {"role": "consultancy", "command": "start", "backend": "stub", "files_changed": 2,
     "ghost_tests": None, "ghost_build": None, "outcome": "ok",
     "task_branch": "ghostc/task/001-x", "ts": "2026-08-31T13:05:01Z"},
    {"role": "client", "command": "start", "flow": "reduced", "task_id": "001-x",
     "ghost_branch": "ghostc/task/001-x", "substitutions": 4, "consultancy_commits": 1,
     "consultancy_authors": ["Consultancy Dev"], "outcome": "ok",
     "ts": "2026-08-31T13:05:02Z"},
    {"role": "client", "command": "open-real-pr", "flow": "reverse-pr", "outcome": "ok",
     "task_id": "001-x", "ghost_branch": "ghostc/task/001-x",
     "ghost_handoff": "0734129dbd556da0", "real_branch": "ghostc/real/add-companyx",
     "base": "main", "entities_resolved": ["vendor_companyx"], "lossy_entities": [],
     "fallbacks": [], "files": 1, "hunks": 1, "ts": "2026-08-31T13:05:10Z"},
]


def _metrics(tmp_path: Path, rows=_ROWS) -> Path:
    p = tmp_path / "agent-runs.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def test_resolve_fields(tmp_path):
    rows = publish.load_rows(_metrics(tmp_path))
    assert publish.resolve(rows, "task_id") == "001-x"
    assert publish.resolve(rows, "ghost_branch") == "ghostc/task/001-x"
    assert publish.resolve(rows, "real_branch") == "ghostc/real/add-companyx"
    assert publish.resolve(rows, "base") == "main"


def test_resolve_ghost_branch_falls_back_to_task_id(tmp_path):
    rows = [{"role": "client", "command": "open-real-pr", "outcome": "ok",
             "task_id": "77-y", "real_branch": "ghostc/real/y", "ts": "t"}]
    assert publish.resolve(rows, "ghost_branch") == "ghostc/task/77-y"


def test_latest_picks_newest_by_ts(tmp_path):
    rows = [
        {"role": "client", "command": "open-real-pr", "outcome": "ok",
         "real_branch": "old", "ts": "2026-08-31T10:00:00Z"},
        {"role": "client", "command": "open-real-pr", "outcome": "ok",
         "real_branch": "new", "ts": "2026-08-31T12:00:00Z"},
    ]
    assert publish.resolve(rows, "real_branch") == "new"


def test_titles(tmp_path):
    rows = publish.load_rows(_metrics(tmp_path))
    assert publish.title(rows, "ghost") == "[ghost] 001-x — sanitized task branch"
    assert publish.title(rows, "real") == "[real] add-companyx — reverse-compiled from ghost"


def test_ghost_body_has_the_key_facts_and_no_real_names(tmp_path):
    body = publish.ghost_body(publish.load_rows(_metrics(tmp_path)))
    assert "`ghostc/task/001-x`" in body
    assert "4 entity spellings" in body
    assert "`stub`" in body and "1 by Consultancy Dev" in body
    assert "n/a (deterministic stub backend)" in body
    for real in ("Northwind", "SkyRoute", "CompanyX", "booking-core"):
        assert real not in body


def test_real_body_reports_restored_entities_and_review_gate(tmp_path):
    body = publish.real_body(publish.load_rows(_metrics(tmp_path)))
    assert "`vendor_companyx`" in body
    assert "`ghostc/task/001-x` @ `0734129dbd`" in body
    assert "1 file(s), 1 hunk(s)" in body
    assert "none" in body                       # lossy / fallbacks
    assert "HUMAN REVIEW REQUIRED" in body


def test_real_body_flags_lossy_and_fallbacks(tmp_path):
    rows = [dict(_ROWS[2], lossy_entities=["client_a"], fallbacks=["src/server.js"])]
    body = publish.real_body(rows)
    assert "`client_a`" in body and "`src/server.js`" in body


def test_cli_resolve(tmp_path):
    m = _metrics(tmp_path)
    out = subprocess.run(
        [sys.executable, "-m", "client_agent.publish", "resolve",
         "--field", "real_branch", "--metrics-file", str(m)],
        capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "ghostc/real/add-companyx"


def test_cli_empty_metrics_exits_2(tmp_path):
    m = tmp_path / "empty.jsonl"
    m.write_text("", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "client_agent.publish", "body", "--side", "ghost",
         "--metrics-file", str(m)], capture_output=True, text=True)
    assert r.returncode == 2


# --- leak-count regression gate -------------------------------------------------
_GATE = Path(__file__).resolve().parents[1] / "scripts" / "ci" / "check_leak_gate.py"


def _run_gate(tmp_path: Path, baseline: str, compile_: str, *args: str):
    csv = tmp_path / "eval-report.csv"
    csv.write_text(
        "metric,baseline,compile,improvement\n"
        f"Residual entity occurrences (casing-aware) — target 0,{baseline},{compile_},x\n"
        "Strict token leaks (verify / groundtruth method) — target 0,0,0,—\n",
        encoding="utf-8")
    return subprocess.run([sys.executable, str(_GATE), str(csv), *args],
                          capture_output=True, text=True)


def test_leak_gate_passes_on_the_expected_numbers(tmp_path):
    assert _run_gate(tmp_path, "28", "0").returncode == 0


def test_leak_gate_fails_when_compile_leaks(tmp_path):
    r = _run_gate(tmp_path, "28", "3")
    assert r.returncode == 1 and "regression" in r.stdout


def test_leak_gate_fails_when_baseline_no_longer_worse(tmp_path):
    r = _run_gate(tmp_path, "0", "0")
    assert r.returncode == 1


def test_leak_gate_cap_override_allows_known_residual(tmp_path):
    assert _run_gate(tmp_path, "28", "2", "2").returncode == 0
