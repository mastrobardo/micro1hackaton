"""load_config: happy path, schema gate, unique-id gate, approval filter."""
from __future__ import annotations

import copy

import pytest
import yaml

from ghostc.config import ConfigError, entities_needing_approval, load_config


@pytest.fixture
def write_cfg(tmp_path, repo_root):
    base = yaml.safe_load((repo_root / "privacy.yaml").read_text(encoding="utf-8"))

    def _write(mutate=None) -> str:
        cfg = copy.deepcopy(base)
        if mutate:
            mutate(cfg)
        p = tmp_path / "privacy.yaml"
        p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
        return str(p)

    return _write


def test_good_config_loads(write_cfg):
    cfg = load_config(write_cfg())
    assert cfg["mapping_version"] == 1
    assert len(cfg["entities"]) == 14


def test_missing_file_raises():
    with pytest.raises(ConfigError, match="not found"):
        load_config("/no/such/privacy.yaml")


@pytest.mark.parametrize("mutate, needle", [
    (lambda c: c["entities"][0].pop("ghost"), "schema validation"),
    (lambda c: c["entities"][0].__setitem__("level", "topsecret"), "schema validation"),
    (lambda c: c.pop("levels"), "schema validation"),
    (lambda c: (c["entities"][1].__setitem__("strategy", "semantic_alias"),
                c["entities"][1].__setitem__("ghost", "")), "schema validation"),
])
def test_broken_config_raises(write_cfg, mutate, needle):
    with pytest.raises(ConfigError, match=needle):
        load_config(write_cfg(mutate))


def test_duplicate_entity_id_raises(write_cfg):
    def dup(c):
        c["entities"].append(copy.deepcopy(c["entities"][0]))

    with pytest.raises(ConfigError, match="duplicate entity id"):
        load_config(write_cfg(dup))


def test_seed_config_has_no_pending_approvals(write_cfg):
    assert entities_needing_approval(load_config(write_cfg())) == []


def test_discovered_restricted_entity_needs_approval(write_cfg):
    def add_discovered(c):
        c["entities"].append({
            "id": "disc_acme", "real": "AcmeCorp", "kind": "client",
            "level": "restricted", "strategy": "synthetic_id", "ghost": "client-z",
            "source": "discovered",
        })

    cfg = load_config(write_cfg(add_discovered))
    assert [e["id"] for e in entities_needing_approval(cfg)] == ["disc_acme"]

    cfg["entities"][-1]["approved_by"] = "reviewer@corp"
    assert entities_needing_approval(cfg) == []
