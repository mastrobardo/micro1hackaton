"""baseline_repo: dumb keyword redaction — runs, deterministic, and measurably
weaker than `compile` (casing variants + compound tokens leak through)."""
from __future__ import annotations

import subprocess

import pytest

from ghostc.baseline import baseline_repo
from tests.conftest import read_tree

pytestmark = pytest.mark.usefixtures("real_repo")


@pytest.fixture
def baseline_tree(tmp_path, real_repo, privacy_yaml):
    out = tmp_path / "baseline-ghost"
    res = baseline_repo(str(real_repo), config_path=str(privacy_yaml), out=str(out),
                        spec_path=str(tmp_path / "baseline-spec.md"),
                        audit_path=str(tmp_path / "private" / "audit.jsonl"))
    return out, res


def test_writes_a_tree_and_a_sibling_spec(baseline_tree, tmp_path):
    out, res = baseline_tree
    assert out.is_dir()
    assert (tmp_path / "baseline-spec.md").exists()
    assert res.files_scanned == 84
    assert res.replacements > 0


def test_git_baseline_commit(baseline_tree):
    out, _ = baseline_tree
    log = subprocess.run(["git", "-C", str(out), "log", "--oneline"],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert log.count("\n") == 0 and log


def test_deterministic_across_independent_runs(tmp_path, real_repo, privacy_yaml):
    trees = []
    for i in range(2):
        out = tmp_path / f"run{i}"
        baseline_repo(str(real_repo), config_path=str(privacy_yaml), out=str(out),
                      spec_path=str(tmp_path / f"s{i}.md"),
                      audit_path=str(tmp_path / f"a{i}.jsonl"))
        trees.append(read_tree(out))
    assert trees[0] == trees[1]


def test_exact_configured_keywords_are_gone(baseline_tree):
    out, _ = baseline_tree
    corpus = "\n".join(read_tree(out).values())
    for kw in ["Northwind Airlines", "SkyRoute Data Ltd", "booking-core", "pricing-svc",
               "fare-cache", "10.20.4.7", "sk_live_northwind_9f3ab7c21e5d4088"]:
        assert kw not in corpus, f"keyword {kw!r} should have been replaced"


def test_casing_variants_leak_through_the_baseline(baseline_tree):
    """The whole point: a keyword `sed` cannot see these; `compile` does."""
    out, _ = baseline_tree
    corpus = "\n".join(read_tree(out).values())
    for leaked in ["SKYROUTE_API_KEY", "SKYROUTE_BASE_URL", "bookingCore",
                   "BOOKING_CORE_URL", "DATADOG_SITE", "SENTRY_DSN"]:
        assert leaked in corpus, f"expected {leaked!r} to leak through keyword redaction"


def test_compilers_matchers_still_find_residual_entities(tmp_path, baseline_tree, privacy_yaml):
    """Run the compiler's casing-aware detector over the baseline tree -> >0 hits."""
    from ghostc.compile import compile_repo

    out, _ = baseline_tree
    res = compile_repo(str(out), config_path=str(privacy_yaml),
                       out=str(tmp_path / "d" / "ghost"),
                       spec_path=str(tmp_path / "d" / "s.md"),
                       mapping_path=str(tmp_path / "d" / "m.json"),
                       audit_path=str(tmp_path / "d" / "a.jsonl"), dry_run=True)
    assert res.hits > 0
    assert "vendor_skyroute" in res.entities


def test_same_file_count_as_compile(tmp_path, baseline_tree, real_repo, privacy_yaml):
    from ghostc.compile import compile_repo

    out, _ = baseline_tree
    compile_repo(str(real_repo), config_path=str(privacy_yaml),
                 out=str(tmp_path / "ghost"),
                 spec_path=str(tmp_path / "ghost-spec.md"),
                 mapping_path=str(tmp_path / "private" / "mapping.json"),
                 audit_path=str(tmp_path / "private" / "audit.jsonl"))
    assert len(read_tree(out)) == len(read_tree(tmp_path / "ghost"))


def test_dry_run_writes_nothing(tmp_path, real_repo, privacy_yaml):
    out = tmp_path / "baseline-ghost"
    res = baseline_repo(str(real_repo), config_path=str(privacy_yaml), out=str(out),
                        spec_path=str(tmp_path / "s.md"),
                        audit_path=str(tmp_path / "a.jsonl"), dry_run=True)
    assert not out.exists()
    assert not (tmp_path / "s.md").exists()
    assert res.replacements > 0
