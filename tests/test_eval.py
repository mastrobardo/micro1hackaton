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
    assert names.count("eval.case") == len(evaluated.cases)


# --- per-case results (the brief asks for 10+ cases, same cases both approaches) ---

def test_at_least_ten_scored_cases(evaluated):
    scored = [c for c in evaluated.cases if c.exercised]
    assert len(scored) >= 10, f"only {len(scored)} scored cases"


def test_every_scored_case_passes_under_compile_and_some_fail_under_baseline(evaluated):
    scored = [c for c in evaluated.cases if c.exercised]
    assert all(c.compile_residual == 0 and c.passed for c in scored)
    assert any(c.baseline_residual > 0 for c in scored), "baseline must lose somewhere"


def test_unexercised_case_is_reported_but_not_scored(evaluated):
    """A configured entity absent from the fixture cannot separate the approaches."""
    for c in evaluated.cases:
        if c.real_occurrences == 0:
            assert not c.exercised and not c.passed
            assert c.result.startswith("n/a")


def test_case_totals_reconcile_with_the_aggregate_metric(evaluated):
    base = evaluated.by_label("baseline")
    assert sum(c.baseline_residual for c in evaluated.cases) == base.residual_total
    assert sum(c.compile_residual for c in evaluated.cases) == 0


def test_hard_case_is_identified(evaluated):
    hard = [c for c in evaluated.cases if c.hard]
    assert hard, "the report must name a challenging case"
    assert hard[0].baseline_residual > 0
    assert hard[0].real_occurrences == max(c.real_occurrences for c in evaluated.cases)


def test_cases_csv_written_with_one_row_per_case(evaluated):
    assert evaluated.cases_csv is not None and evaluated.cases_csv.exists()
    rows = list(csv.reader(io.StringIO(evaluated.cases_csv.read_text())))
    assert rows[0][:5] == ["case", "entity", "kind", "level", "ghost_alias"]
    assert len(rows) - 1 == len(evaluated.cases)


def test_report_md_contains_the_per_case_table(evaluated):
    md = evaluated.report_md.read_text()
    assert "## Per-case results" in md
    assert "Challenging case" in md
    for c in evaluated.cases:
        assert c.entity_id in md


def test_cli_eval_runs_and_prints_verdict(tmp_path, real_repo, privacy_yaml):
    res = CliRunner().invoke(main, [
        "eval", "--real", str(real_repo), "--config", str(privacy_yaml),
        "--baseline-out", str(tmp_path / "b"), "--compile-out", str(tmp_path / "g"),
        "--report", str(tmp_path / "rep"), "--audit", str(tmp_path / "a.jsonl"),
    ])
    assert res.exit_code == 0, res.output
    assert "compile residual=0" in res.output
    assert (tmp_path / "rep.md").exists()
