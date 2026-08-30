"""ghostc verify — fail-closed leak / mapping / build gate over the ghost repo."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import jsonschema
import pytest
from click.testing import CliRunner

from ghostc.cli import main
from ghostc.scanning import anchored_scan, looks_like_mapping
from ghostc.verify import verify_ghost
from tests.conftest import load_jsonl

pytestmark = pytest.mark.usefixtures("real_repo")
AUDIT_SCHEMA = json.loads(
    (Path(__file__).resolve().parents[1] / "schemas" / "audit-event.schema.json").read_text()
)


@pytest.fixture
def ghost_copy(compiled, tmp_path) -> Path:
    dst = tmp_path / "ghost"
    shutil.copytree(compiled.ghost, dst)
    return dst


# -- scanning primitive ---------------------------------------------------

def test_anchored_scan_is_boundary_bounded_and_longest_first():
    hits = anchored_scan("strip-ansi and ip-a and Northwind Airlines",
                         ["ip-a", "Northwind", "Northwind Airlines"])
    texts = [h.text for h in hits]
    assert "ip-a" in texts                       # standalone token
    assert texts.count("Northwind") == 0         # subsumed by the longer needle
    assert "Northwind Airlines" in texts
    assert anchored_scan("strip-ansi", ["ip-a"]) == []   # not a substring hit


@pytest.mark.parametrize("text, expected", [
    ('{"mapping_version": 1, "entries": []}', True),
    ('{"entity_id": "x", "real": "Foo", "real_sha256": "ab", "ghost": "y", "frozen": true}', True),
    ('see the real_sha256 column in notes', True),
    ('{"name": "real project", "count": 3}', False),
    ('const frozen = true;', False),
])
def test_looks_like_mapping(text, expected):
    assert looks_like_mapping(text) is expected


# -- happy path ---------------------------------------------------------

def test_freshly_compiled_ghost_passes(compiled, privacy_yaml):
    res = verify_ghost(compiled.ghost, compiled.mapping, config_path=str(privacy_yaml))
    assert res.ok, res.summary()
    assert {c.name for c in res.checks} == {"leak_scan", "mapping_leak", "build"}
    assert next(c for c in res.checks if c.name == "leak_scan").status == "pass"


# -- leak scan --------------------------------------------------------

def test_blocks_on_a_planted_real_value(ghost_copy, compiled, privacy_yaml):
    target = ghost_copy / "src" / "config" / "config.js"
    target.write_text(target.read_text() + "\n// contact Northwind Airlines ops\n")

    res = verify_ghost(ghost_copy, compiled.mapping, config_path=str(privacy_yaml))
    assert not res.ok
    leak = next(c for c in res.checks if c.name == "leak_scan")
    assert leak.status == "fail"
    assert any(h.entity_id == "client_northwind" and h.file.endswith("config.js")
               for h in leak.leaks)


def test_blocks_on_a_secret_value_from_the_mapping_only(ghost_copy, compiled):
    # the API-key value lives in the mapping `real` field; no config needed to catch it
    (ghost_copy / "leak.txt").write_text("key = sk_live_northwind_9f3ab7c21e5d4088\n")
    res = verify_ghost(ghost_copy, compiled.mapping, config_path=None)
    assert not res.ok
    assert any(h.entity_id == "secret_skyroute_key"
               for c in res.checks if c.name == "leak_scan" for h in c.leaks)


# -- mapping-leak scan -----------------------------------------------

def test_blocks_when_the_mapping_store_is_inside_the_ghost(ghost_copy, compiled, privacy_yaml):
    (ghost_copy / "docs").mkdir(exist_ok=True)
    shutil.copy(compiled.mapping, ghost_copy / "docs" / "mapping.json")
    res = verify_ghost(ghost_copy, compiled.mapping, config_path=str(privacy_yaml))
    assert not res.ok
    ml = next(c for c in res.checks if c.name == "mapping_leak")
    assert ml.status == "fail" and any("mapping.json" in f for f in ml.files)


# -- build gate -----------------------------------------------------

def test_build_gate_skips_without_toolchain_but_still_passes(compiled, privacy_yaml):
    res = verify_ghost(compiled.ghost, compiled.mapping, config_path=str(privacy_yaml))
    build = next(c for c in res.checks if c.name == "build")
    assert build.status in {"pass", "skipped"}
    if build.status == "skipped":
        assert res.ok  # skipped build does not block on its own


def test_require_build_turns_a_skip_into_a_block(compiled, privacy_yaml):
    res = verify_ghost(compiled.ghost, compiled.mapping, config_path=str(privacy_yaml),
                       require_build=True)
    build = next(c for c in res.checks if c.name == "build")
    if not shutil.which("yarn") or not (compiled.ghost / "node_modules").is_dir():
        assert build.status == "fail" and not res.ok


# -- missing inputs fail closed ------------------------------------

def test_missing_ghost_is_a_block(tmp_path, compiled):
    res = verify_ghost(tmp_path / "nope", compiled.mapping)
    assert not res.ok and res.checks[0].name == "input"


def test_missing_mapping_is_a_block(compiled, tmp_path):
    res = verify_ghost(compiled.ghost, tmp_path / "nope.json")
    assert not res.ok and res.checks[0].name == "input"


# -- CLI + audit ---------------------------------------------------

def test_cli_pass_emits_verify_pass_and_exits_zero(compiled, privacy_yaml, tmp_path):
    audit = tmp_path / "audit.jsonl"
    res = CliRunner().invoke(main, [
        "verify", "--ghost", str(compiled.ghost), "--mapping", str(compiled.mapping),
        "--config", str(privacy_yaml), "--audit", str(audit),
    ])
    assert res.exit_code == 0
    assert res.output.startswith("PASS")
    events = [r["event"] for r in load_jsonl(audit)]
    assert events == ["verify.scan", "verify.pass"]
    for rec in load_jsonl(audit):
        jsonschema.Draft202012Validator(AUDIT_SCHEMA).validate(rec)


def test_cli_block_exits_one_and_audit_has_no_cleartext(ghost_copy, compiled, privacy_yaml,
                                                        tmp_path, seed_entities):
    (ghost_copy / "boom.js").write_text("// SkyRoute Data Ltd feed for Northwind Airlines\n")
    audit = tmp_path / "audit.jsonl"
    res = CliRunner().invoke(main, [
        "verify", "--ghost", str(ghost_copy), "--mapping", str(compiled.mapping),
        "--config", str(privacy_yaml), "--audit", str(audit),
    ])
    assert res.exit_code == 1
    assert "BLOCK" in res.output
    events = [r["event"] for r in load_jsonl(audit)]
    assert events == ["verify.scan", "verify.block"]

    raw = audit.read_text()
    for e in seed_entities:
        assert e["real"] not in raw
