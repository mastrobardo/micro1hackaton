"""ghostc eval: baseline vs compile residual-leak metric (MVP, no external agent)."""
from __future__ import annotations

import csv
import io

import pytest
from click.testing import CliRunner

from ghostc.cli import main
from ghostc.eval import run_eval
from tests.conftest import load_jsonl

pytestmark = pytest.mark.usefixtures("real_repo")


@pytest.fixture
def evaluated(tmp_path, real_repo, privacy_yaml):
    return run_eval(str(real_repo), config_path=str(privacy_yaml),
                    baseline_out=str(tmp_path / "baseline-ghost"),
                    compile_out=str(tmp_path / "ghost"),
                    report=str(tmp_path / "eval-report"),
                    audit_path=str(tmp_path / "private" / "audit.jsonl"))


def test_compile_leaves_zero_residual_baseline_does_not(evaluated):
    base = evaluated.by_label("baseline")
    comp = evaluated.by_label("compile")
    assert comp.residual_total == 0
    assert comp.residual_by_entity == {}
    assert base.residual_total > 0
    assert base.residual_total > comp.residual_total


def test_baseline_residual_names_vendor_and_service_entities(evaluated):
    leaked = evaluated.by_label("baseline").residual_by_entity
    assert "vendor_skyroute" in leaked
    assert any(k.startswith("svc_") for k in leaked)


def test_strict_scan_of_real_repo_matches_groundtruth(evaluated):
    # same method as tests/expected/groundtruth.json -> must agree
    assert evaluated.real_strict_total == evaluated.groundtruth_total
    assert evaluated.real_residual_total >= evaluated.real_strict_total


def test_report_md_and_csv_written_and_consistent(evaluated):
    assert evaluated.report_md.exists() and evaluated.report_csv.exists()
    md = evaluated.report_md.read_text()
    assert "baseline keyword redaction vs" in md

    rows = list(csv.reader(io.StringIO(evaluated.report_csv.read_text())))
    assert rows[0] == ["metric", "baseline", "compile", "improvement"]
    residual_row = next(r for r in rows if r[0].startswith("Residual entity occurrences"))
    assert residual_row[1] == str(evaluated.by_label("baseline").residual_total)
    assert residual_row[2] == "0"


def test_audit_has_eval_component_events(evaluated, tmp_path):
    events = [r for r in load_jsonl(tmp_path / "private" / "audit.jsonl")
              if r.get("component") == "eval"]
    names = [r["event"] for r in events]
    assert names.count("eval.metric") == 2
    assert "eval.summary" in names


def test_cli_eval_runs_and_prints_verdict(tmp_path, real_repo, privacy_yaml):
    res = CliRunner().invoke(main, [
        "eval", "--real", str(real_repo), "--config", str(privacy_yaml),
        "--baseline-out", str(tmp_path / "b"), "--compile-out", str(tmp_path / "g"),
        "--report", str(tmp_path / "rep"), "--audit", str(tmp_path / "a.jsonl"),
    ])
    assert res.exit_code == 0, res.output
    assert "compile residual=0" in res.output
    assert (tmp_path / "rep.md").exists()
