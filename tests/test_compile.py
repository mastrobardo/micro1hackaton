"""compile_repo end-to-end on the fixture: zero leaks, determinism, structure."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.conftest import read_tree, scan_entity_hits

pytestmark = pytest.mark.usefixtures("real_repo")


def _norm_mapping(path):
    d = json.loads(path.read_text())
    d.pop("created", None)
    d.pop("updated", None)
    for e in d["entries"]:
        e.pop("first_seen_run", None)
    return json.dumps(d, sort_keys=True)


METADATA_NAMES = {"mapping.json", "audit.jsonl", "ghost-spec.md"}


def test_ghost_tree_contains_no_generated_metadata(compiled):
    offenders = [p.relative_to(compiled.ghost).as_posix()
                 for p in compiled.ghost.rglob("*")
                 if p.is_file() and p.name in METADATA_NAMES]
    assert offenders == [], f"metadata written inside the ghost repo: {offenders}"


def test_metadata_lands_outside_the_ghost_by_layout(compiled):
    assert compiled.mapping.exists() and "private" in compiled.mapping.parts
    assert compiled.audit.exists() and "private" in compiled.audit.parts
    assert compiled.spec.exists() and compiled.spec.parent == compiled.ghost.parent
    assert not compiled.mapping.is_relative_to(compiled.ghost)
    assert not compiled.spec.is_relative_to(compiled.ghost)


@pytest.mark.parametrize("bad_key", ["mapping_path", "audit_path", "spec_path"])
def test_refuses_artifact_paths_inside_the_ghost(tmp_path, real_repo, privacy_yaml, bad_key):
    from ghostc.compile import compile_repo

    ghost = tmp_path / "ghost"
    kw = dict(
        config_path=str(privacy_yaml), out=str(ghost),
        spec_path=str(tmp_path / "ghost-spec.md"),
        mapping_path=str(tmp_path / "private" / "mapping.json"),
        audit_path=str(tmp_path / "private" / "audit.jsonl"),
    )
    kw[bad_key] = str(ghost / "leak" / Path(kw[bad_key]).name)
    with pytest.raises(SystemExit, match="inside the ghost repo"):
        compile_repo(str(real_repo), **kw)


def test_default_artifact_paths_are_boundary_separated():
    import inspect

    from ghostc.compile import compile_repo

    d = inspect.signature(compile_repo).parameters
    assert d["mapping_path"].default == "workspace/private/mapping.json"
    assert d["audit_path"].default == "workspace/private/audit.jsonl"
    assert d["spec_path"].default == "workspace/ghost-spec.md"
    assert d["out"].default == "workspace/ghost"


def test_no_real_value_survives_into_ghost(compiled, seed_entities):
    corpus = "\n".join(read_tree(compiled.ghost).values())
    hits = scan_entity_hits(corpus, seed_entities)
    assert hits == {}, f"leaked entities in ghost: {hits}"


def test_raw_sensitive_tokens_absent_from_ghost(compiled):
    corpus = "\n".join(read_tree(compiled.ghost).values())
    for token in ["Northwind", "SkyRoute", "skyroute", "Datadog", "datadoghq", "Sentry",
                  "booking-core", "pricing-svc", "fare-cache", "northwind-internal",
                  "10.20.4.7", "nwa-prod-eu-west-1", "447015923388", "sk_live",
                  "Priya", "priya.nair"]:
        assert token not in corpus, f"{token!r} present in ghost tree"


def test_mapping_is_complete_and_frozen(compiled):
    d = json.loads(compiled.mapping.read_text())
    assert len(d["entries"]) == 13  # all seeds except vendor_aerofeed (absent from fixture)
    assert all(e["frozen"] is True for e in d["entries"])
    assert all(e.get("real_sha256") for e in d["entries"])


def test_ghost_spec_has_no_real_values_and_spans_levels(compiled, seed_entities):
    spec = compiled.spec.read_text()
    assert scan_entity_hits(spec, seed_entities) == {}
    for level in ("internal", "confidential", "restricted"):
        assert level in spec


def test_determinism_across_independent_runs(tmp_path, real_repo, privacy_yaml):
    from ghostc.compile import compile_repo

    trees, mappings = [], []
    for i in range(2):
        out = tmp_path / f"run{i}"
        compile_repo(str(real_repo), config_path=str(privacy_yaml),
                     out=str(out / "ghost"), mapping_path=str(out / "m.json"),
                     audit_path=str(out / "a.jsonl"))
        trees.append(read_tree(out / "ghost"))
        mappings.append(_norm_mapping(out / "m.json"))
    assert trees[0] == trees[1]
    assert mappings[0] == mappings[1]


def test_frozen_alias_reused_on_second_run(tmp_path, real_repo, privacy_yaml):
    from ghostc.compile import compile_repo

    kw = dict(config_path=str(privacy_yaml), mapping_path=str(tmp_path / "m.json"),
              audit_path=str(tmp_path / "a.jsonl"))
    first = compile_repo(str(real_repo), out=str(tmp_path / "g1"), **kw)
    second = compile_repo(str(real_repo), out=str(tmp_path / "g2"), **kw)

    assert all(not r.reused for r in first.entities.values())   # first run: all created
    assert all(r.reused for r in second.entities.values())      # second run: all reused
    assert read_tree(tmp_path / "g1") == read_tree(tmp_path / "g2")


def test_dry_run_writes_nothing(tmp_path, real_repo, privacy_yaml):
    from ghostc.compile import compile_repo

    ghost = tmp_path / "ghost"
    res = compile_repo(str(real_repo), config_path=str(privacy_yaml), out=str(ghost),
                       mapping_path=str(tmp_path / "m.json"),
                       audit_path=str(tmp_path / "a.jsonl"), dry_run=True)
    assert not ghost.exists()
    assert not (tmp_path / "m.json").exists()
    assert not (tmp_path / "a.jsonl").exists()
    assert len(res.entities) == 13


def test_git_dir_is_a_fresh_baseline_not_a_copy(compiled):
    assert (compiled.ghost / ".git").is_dir()
    log = subprocess.run(["git", "-C", str(compiled.ghost), "log", "--oneline"],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert log.count("\n") == 0
    assert "ghost baseline" in log


def test_sensitive_path_component_renamed(compiled):
    integrations = compiled.ghost / "src" / "integrations"
    names = {p.name for p in integrations.iterdir()}
    assert "vendorAClient.js" in names
    assert "skyRouteClient.js" not in names
    assert compiled.result.files_renamed >= 3


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_ghost_javascript_still_parses(compiled):
    for js in (compiled.ghost / "src" / "integrations").glob("*.js"):
        r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
        assert r.returncode == 0, f"{js.name}: {r.stderr}"
