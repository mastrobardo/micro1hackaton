"""compile_repo end-to-end on the fixture: zero leaks, determinism, structure."""
from __future__ import annotations

import json
import re
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


# --- the ghost tree explains itself: unconfigured surfaces are declared, not silent ---

def test_ghost_spec_declares_unconfigured_surfaces_left_verbatim(compiled):
    """`adversary.js` keeps Meridian/Contoso by design (auto_alias off). A reader of
    the ghost must be told that, or it reads as an unexplained leak."""
    spec = compiled.spec.read_text()
    assert "Surfaces present verbatim" in spec
    assert "Meridian" in spec and "contoso" in spec.lower()
    assert "not cleared for release" in spec
    surfaces = {c["surface"] for c in compiled.result.pending_review}
    assert any("Meridian" in s for s in surfaces)


def test_pending_surfaces_are_actually_still_in_the_ghost(compiled):
    """The spec's claim must match the tree — otherwise it is just prose."""
    corpus = "\n".join(read_tree(compiled.ghost).values()).casefold()
    for c in compiled.result.pending_review:
        assert c["surface"].casefold() in corpus, f"{c['surface']} declared but absent"


def test_accepted_proposal_is_aliased_and_drops_off_the_pending_list(
        tmp_path, real_repo, privacy_yaml):
    """A reviewer's accept promotes the surface to an entity — it is no longer pending."""
    from ghostc.compile import compile_repo

    decisions = Path(__file__).resolve().parents[1] / "fixtures" / "decisions.example.jsonl"
    res = compile_repo(
        str(real_repo), config_path=str(privacy_yaml),
        out=str(tmp_path / "ghost"), spec_path=str(tmp_path / "spec.md"),
        mapping_path=str(tmp_path / "p" / "m.json"),
        audit_path=str(tmp_path / "p" / "a.jsonl"),
        candidates_path=str(tmp_path / "p" / "c.jsonl"),
        decisions_path=str(decisions),
    )
    surfaces = {c["surface"].casefold() for c in res.pending_review}
    assert not any("meridian" in s for s in surfaces), "accepted surface still listed pending"
    assert "vendor_meridian" in res.entities          # it was compiled as an entity

    # The only surviving spelling is the package import specifier, which `compile`
    # keeps verbatim on purpose (a renamed dependency would not resolve in the ghost)
    # and declares in the spec's "Dependency names left un-aliased" table.
    corpus = "\n".join(read_tree(tmp_path / "ghost").values())
    survivors = set(re.findall(r"[\w@/.-]*[Mm]eridian[\w@/.-]*", corpus))
    assert survivors == {"@meridianaero/flight-sdk"}, survivors
    assert "Meridian Aero Systems" not in corpus
    kept = {k["specifier"] for k in res.kept_specifiers}
    assert "@meridianaero/flight-sdk" in kept
    assert "Dependency names left un-aliased" in (tmp_path / "spec.md").read_text()


def test_reviewer_ignored_surface_is_marked_as_decided(tmp_path, real_repo, privacy_yaml):
    from ghostc.compile import compile_repo

    decisions = Path(__file__).resolve().parents[1] / "fixtures" / "decisions.example.jsonl"
    res = compile_repo(
        str(real_repo), config_path=str(privacy_yaml),
        out=str(tmp_path / "ghost"), spec_path=str(tmp_path / "spec.md"),
        mapping_path=str(tmp_path / "p" / "m.json"),
        audit_path=str(tmp_path / "p" / "a.jsonl"),
        candidates_path=str(tmp_path / "p" / "c.jsonl"),
        decisions_path=str(decisions),
    )
    contoso = [c for c in res.pending_review if "contoso" in c["surface"].casefold()]
    assert contoso and contoso[0]["reviewed_ignore"] is True
    spec = (tmp_path / "spec.md").read_text()
    assert "reviewer chose **ignore**" in spec
    assert "not cleared for release" not in spec   # nothing undecided remains


def test_determinism_across_independent_runs(tmp_path, real_repo, privacy_yaml):
    from ghostc.compile import compile_repo

    trees, mappings = [], []
    for i in range(2):
        out = tmp_path / f"run{i}"
        compile_repo(str(real_repo), config_path=str(privacy_yaml),
                     out=str(out / "ghost"), mapping_path=str(out / "m.json"),
                     audit_path=str(out / "a.jsonl"),
                     candidates_path=str(out / "candidates.jsonl"))
        trees.append(read_tree(out / "ghost"))
        mappings.append(_norm_mapping(out / "m.json"))
    assert trees[0] == trees[1]
    assert mappings[0] == mappings[1]


def test_frozen_alias_reused_on_second_run(tmp_path, real_repo, privacy_yaml):
    from ghostc.compile import compile_repo

    kw = dict(config_path=str(privacy_yaml), mapping_path=str(tmp_path / "m.json"),
              audit_path=str(tmp_path / "a.jsonl"),
              candidates_path=str(tmp_path / "candidates.jsonl"))
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


# -- threshold-driven detection layer ---------------------------------------

def test_compile_writes_candidates_and_review_audit(compiled):
    from tests.conftest import load_jsonl

    cand = compiled.mapping.parent / "candidates.jsonl"
    assert cand.exists()
    rows = load_jsonl(cand)
    assert rows and all({"surface", "score", "action"} <= r.keys() for r in rows)
    events = {r["event"] for r in load_jsonl(compiled.audit)}
    assert "compile.candidate_review" in events


def test_detection_off_matches_matcher_only_output(tmp_path, real_repo, privacy_yaml):
    from ghostc.compile import compile_repo

    kw = dict(config_path=str(privacy_yaml), audit_path=str(tmp_path / "a.jsonl"))
    on = compile_repo(str(real_repo), out=str(tmp_path / "on"),
                      mapping_path=str(tmp_path / "on.json"),
                      candidates_path=str(tmp_path / "c.jsonl"), detect=True, **kw)
    off = compile_repo(str(real_repo), out=str(tmp_path / "off"),
                       mapping_path=str(tmp_path / "off.json"), detect=False, **kw)
    # auto_alias defaults off → the ghost tree is byte-identical either way
    assert read_tree(tmp_path / "on") == read_tree(tmp_path / "off")
    assert set(on.entities) == set(off.entities)


def test_auto_alias_mints_and_transforms_a_discovered_entity(tmp_path, real_repo, repo_root):
    import yaml

    from ghostc.compile import compile_repo

    cfg = yaml.safe_load((repo_root / "privacy.yaml").read_text())
    cfg.setdefault("detection", {})["auto_alias"] = True
    p = tmp_path / "privacy.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    res = compile_repo(str(real_repo), config_path=str(p), out=str(tmp_path / "ghost"),
                       mapping_path=str(tmp_path / "m.json"),
                       audit_path=str(tmp_path / "a.jsonl"),
                       candidates_path=str(tmp_path / "c.jsonl"))
    minted = [eid for eid in res.entities if eid.startswith("disc_")]
    assert minted, "auto_alias did not mint any discovered entity"
    adv = (tmp_path / "ghost" / "src" / "integrations" / "adversary.js").read_text()
    assert "Meridian Aero Systems" not in adv          # prose name aliased
    assert "MERIDIAN_API_KEY" not in adv               # env var aliased
    # the package specifier is KEPT verbatim — a renamed dep would not resolve
    assert "require('@meridianaero/flight-sdk')" in adv
    assert res.kept_specifiers
    assert any(k["specifier"] == "@meridianaero/flight-sdk" for k in res.kept_specifiers)


def test_import_specifier_kept_but_relative_specifier_still_rewritten(tmp_path):
    """Package specifiers are kept; first-party (./ ../) specifiers still rewrite."""
    from ghostc.compile import compile_repo

    repo = tmp_path / "src"
    repo.mkdir(parents=True)
    (repo / "acme.js").write_text("module.exports = {};\n", encoding="utf-8")
    (repo / "app.js").write_text(
        "const sdk = require('@acmecorp/sdk');\n"
        "const local = require('./acme');\n"
        "import helper from '../src/acme';\n"
        "const ACME_KEY = process.env.ACME_KEY;\n", encoding="utf-8")
    cfg = {
        "version": 1, "mapping_version": 1,
        "levels": {"internal": {"transform": True, "approval": "auto"}},
        "strategies": ["semantic_alias"], "defaults_by_kind": {}, "exclusions": [],
        "entities": [{
            "id": "vendor_acme", "real": "AcmeCorp", "kind": "vendor", "level": "internal",
            "strategy": "semantic_alias", "ghost": "vendor-a",
            "match": [{"kind": "identifier", "value": "acmecorp"},
                      {"kind": "identifier", "value": "acme"}],
        }],
    }
    import yaml as _yaml

    p = tmp_path / "privacy.yaml"
    p.write_text(_yaml.safe_dump(cfg), encoding="utf-8")
    res = compile_repo(str(repo), config_path=str(p), out=str(tmp_path / "ghost"),
                       mapping_path=str(tmp_path / "m.json"),
                       audit_path=str(tmp_path / "a.jsonl"),
                       candidates_path=str(tmp_path / "c.jsonl"), detect=False)
    out = (tmp_path / "ghost" / "app.js").read_text()
    assert "require('@acmecorp/sdk')" in out                 # package: kept verbatim
    assert "require('./vendor-a')" in out                    # first-party: rewritten
    assert "from '../src/vendor-a'" in out                   # first-party: rewritten
    assert (tmp_path / "ghost" / "vendor-a.js").exists()     # + the target file renamed
    assert "ACME_KEY" not in out and "VENDOR_A_KEY" in out   # env var: rewritten
    assert [k["specifier"] for k in res.kept_specifiers] == ["@acmecorp/sdk"]


def test_rewrite_imports_flag_forces_package_specifier_rewrite(tmp_path):
    from ghostc.compile import compile_repo

    repo = tmp_path / "src"
    repo.mkdir(parents=True)
    (repo / "app.js").write_text("const s = require('@acmecorp/sdk');\n", encoding="utf-8")
    cfg = {
        "version": 1, "mapping_version": 1,
        "levels": {"internal": {"transform": True, "approval": "auto"}},
        "strategies": ["semantic_alias"], "defaults_by_kind": {}, "exclusions": [],
        "entities": [{
            "id": "vendor_acme", "real": "AcmeCorp", "kind": "vendor", "level": "internal",
            "strategy": "semantic_alias", "ghost": "vendor-a", "rewrite_imports": True,
            "match": [{"kind": "identifier", "value": "acmecorp"}],
        }],
    }
    import yaml as _yaml

    p = tmp_path / "privacy.yaml"
    p.write_text(_yaml.safe_dump(cfg), encoding="utf-8")
    res = compile_repo(str(repo), config_path=str(p), out=str(tmp_path / "ghost"),
                       mapping_path=str(tmp_path / "m.json"),
                       audit_path=str(tmp_path / "a.jsonl"),
                       candidates_path=str(tmp_path / "c.jsonl"), detect=False)
    out = (tmp_path / "ghost" / "app.js").read_text()
    assert "require('@vendor-a/sdk')" in out
    assert res.kept_specifiers == []


def test_auto_alias_blocks_on_restricted_discovery():
    """A discovered restricted proposal must halt compile (human-approval gate)."""
    from types import SimpleNamespace

    from ghostc.compile import _augment_with_auto_candidates
    from ghostc.detect.settings import detection_settings

    fake = SimpleNamespace(candidates=[SimpleNamespace(
        entity_id=None, action="auto", kind="client", level="restricted",
        surface="AcmeAir", aliases=["acmeair"], occurrences=[], score=0.97)])
    settings = detection_settings({"detection": {"auto_alias": True}})
    _cfg, minted, blocked = _augment_with_auto_candidates(
        {"entities": [], "mapping_version": 1}, fake, settings)
    assert minted and blocked == [minted[0]["id"]]
