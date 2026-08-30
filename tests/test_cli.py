"""CLI surface: command list, version, validate-config exit codes, stub behaviour."""
from __future__ import annotations

import pytest
from click.testing import CliRunner

from ghostc.cli import main

RUNNER = CliRunner()
STUBS = ["discover", "apply-patch", "eval"]


def test_help_lists_the_six_commands():
    res = RUNNER.invoke(main, ["--help"])
    assert res.exit_code == 0
    for cmd in ["validate-config", "discover", "compile", "verify", "apply-patch", "eval"]:
        assert cmd in res.output


def test_version_option():
    res = RUNNER.invoke(main, ["--version"])
    assert res.exit_code == 0 and "ghostc" in res.output


def test_compile_help_exposes_boundary_separated_paths():
    res = RUNNER.invoke(main, ["compile", "--help"])
    assert res.exit_code == 0
    for opt in ["--out", "--spec", "--mapping", "--audit"]:
        assert opt in res.output
    assert "workspace/private/mapping.json" in res.output
    assert "workspace/private/audit.jsonl" in res.output


def test_validate_config_ok(repo_root):
    res = RUNNER.invoke(main, ["validate-config", "--config", str(repo_root / "privacy.yaml")])
    assert res.exit_code == 0
    assert res.output.startswith("OK")
    assert "entities: 14" in res.output


def test_validate_config_rejects_broken_file(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("version: 1\nmapping_version: 1\n", encoding="utf-8")  # missing required keys
    res = RUNNER.invoke(main, ["validate-config", "--config", str(bad)])
    assert res.exit_code != 0
    assert "INVALID" in res.output


@pytest.mark.parametrize("cmd", STUBS)
def test_stub_commands_exit_nonzero_with_pointer(cmd):
    args = {"discover": ["--repo", "."],
            "apply-patch": ["--ghost-diff", "/dev/null", "--real", "."],
            "eval": []}[cmd]
    res = RUNNER.invoke(main, [cmd, *args])
    assert res.exit_code != 0
    assert "PROGRESS.md" in res.output


def test_compile_is_not_a_stub(real_repo, tmp_path, repo_root):
    res = RUNNER.invoke(main, [
        "compile", "--repo", str(real_repo), "--config", str(repo_root / "privacy.yaml"),
        "--out", str(tmp_path / "ghost"), "--mapping", str(tmp_path / "m.json"),
        "--audit", str(tmp_path / "a.jsonl"), "--dry-run",
    ])
    assert res.exit_code == 0
    assert "entities:" in res.output


def test_compile_blocks_on_unapproved_restricted_entity(real_repo, tmp_path, repo_root):
    import yaml

    cfg = yaml.safe_load((repo_root / "privacy.yaml").read_text())
    cfg["entities"].append({
        "id": "disc_pending", "real": "PendingCo", "kind": "client", "level": "restricted",
        "strategy": "synthetic_id", "ghost": "client-z", "source": "discovered",
    })
    p = tmp_path / "privacy.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    res = RUNNER.invoke(main, ["compile", "--repo", str(real_repo), "--config", str(p),
                               "--out", str(tmp_path / "ghost"),
                               "--mapping", str(tmp_path / "m.json"),
                               "--audit", str(tmp_path / "a.jsonl"), "--dry-run"])
    assert res.exit_code != 0
    assert "BLOCKED" in res.output and "disc_pending" in res.output
