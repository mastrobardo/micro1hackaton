"""`ghostc compile --decisions` / `discover --decisions` — the review log the
pipeline consumes. No file -> today's behaviour (backward compatible)."""
from __future__ import annotations

import copy
import json

import yaml
from click.testing import CliRunner

from ghostc.cli import main

RUNNER = CliRunner()


def _cfg(tmp_path, repo_root, mutate):
    cfg = yaml.safe_load((repo_root / "privacy.yaml").read_text(encoding="utf-8"))
    mutate(cfg)
    p = tmp_path / "privacy.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return str(p)


def _repo(tmp_path, body: str) -> str:
    r = tmp_path / "repo" / "src"
    r.mkdir(parents=True)
    (r / "x.js").write_text(body, encoding="utf-8")
    return str(tmp_path / "repo")


def _paths(tmp_path):
    return ["--out", str(tmp_path / "ghost"), "--mapping", str(tmp_path / "m.json"),
            "--audit", str(tmp_path / "a.jsonl"), "--spec", str(tmp_path / "s.md"),
            "--candidates", str(tmp_path / "c.jsonl"), "--no-detect"]


_RESTRICTED = {"id": "disc_acme", "real": "Acme Partners Ltd", "kind": "vendor",
               "level": "restricted", "strategy": "synthetic_id", "ghost": "vendor-z",
               "source": "discovered",
               "match": [{"kind": "literal", "value": "Acme Partners Ltd"}]}


def test_compile_blocks_on_unapproved_restricted(tmp_path, repo_root):
    cfg = _cfg(tmp_path, repo_root,
              lambda c: c["entities"].append(copy.deepcopy(_RESTRICTED)))
    repo = _repo(tmp_path, "const v = 'Acme Partners Ltd';\n")
    res = RUNNER.invoke(main, ["compile", "--repo", repo, "--config", cfg, *_paths(tmp_path)])
    assert res.exit_code != 0
    assert "awaiting human approval" in res.output and "disc_acme" in res.output


def test_decisions_file_clears_the_restricted_entity(tmp_path, repo_root):
    cfg = _cfg(tmp_path, repo_root,
              lambda c: c["entities"].append(copy.deepcopy(_RESTRICTED)))
    repo = _repo(tmp_path, "const v = 'Acme Partners Ltd';\n")
    dec = tmp_path / "decisions.jsonl"
    dec.write_text(json.dumps({
        "reviewer_action": "accept", "entity_id": "disc_acme", "key": "disc_acme",
        "surface": "Acme Partners Ltd", "approved_by": "al", "level": "restricted",
        "proposed_action": "review", "proposed_level": "restricted", "ghost": "vendor-z",
        "note": "", "occurrences": 1, "ts": "2026-08-31T00:00:00+00:00", "op_id": "op_t"}) + "\n",
        encoding="utf-8")
    res = RUNNER.invoke(main, ["compile", "--repo", repo, "--config", cfg,
                              "--decisions", str(dec), *_paths(tmp_path)])
    assert res.exit_code == 0, res.output
    mapping = json.loads((tmp_path / "m.json").read_text())
    assert any(e["entity_id"] == "disc_acme" and e["ghost"] == "vendor-z"
               for e in mapping["entries"])
    ghost_js = (tmp_path / "ghost" / "src" / "x.js").read_text()
    assert "Acme Partners" not in ghost_js and "vendor z" in ghost_js.lower()


def test_accepted_proposal_becomes_a_compiled_entity(tmp_path, repo_root):
    from ghostc.audit import hash_real
    cfg = _cfg(tmp_path, repo_root, lambda c: None)
    repo = _repo(tmp_path, "// integrate Zeta Freight\nconst z = 'Zeta Freight';\n")
    dec = tmp_path / "decisions.jsonl"
    dec.write_text(json.dumps({
        "reviewer_action": "accept", "entity_id": "rev_zeta", "surface": "Zeta Freight",
        "key": "sha256:" + hash_real("Zeta Freight"), "approved_by": "al",
        "level": "confidential", "proposed_action": "review", "proposed_level": "confidential",
        "ghost": None, "note": "", "occurrences": 2,
        "ts": "2026-08-31T00:00:00+00:00", "op_id": "op_t"}) + "\n", encoding="utf-8")
    res = RUNNER.invoke(main, ["compile", "--repo", repo, "--config", cfg,
                              "--decisions", str(dec), *_paths(tmp_path)])
    assert res.exit_code == 0, res.output
    mapping = json.loads((tmp_path / "m.json").read_text())
    entry = next(e for e in mapping["entries"] if e["entity_id"] == "rev_zeta")
    assert entry["ghost"].startswith("vendor-")
    ghost_js = (tmp_path / "ghost" / "src" / "x.js").read_text()
    assert "Zeta Freight" not in ghost_js


def test_no_decisions_file_is_unchanged_behaviour(tmp_path, repo_root):
    cfg = _cfg(tmp_path, repo_root, lambda c: None)
    repo = _repo(tmp_path, "const ok = 1;\n")
    a = RUNNER.invoke(main, ["compile", "--repo", repo, "--config", cfg, *_paths(tmp_path)])
    b = RUNNER.invoke(main, ["compile", "--repo", repo, "--config", cfg,
                            "--decisions", str(tmp_path / "missing.jsonl"), *_paths(tmp_path)])
    assert a.exit_code == 0 and b.exit_code == 0


def test_discover_annotates_proposals_with_decisions(tmp_path, repo_root, real_repo):
    res = RUNNER.invoke(main, ["discover", "--repo", str(real_repo),
                              "--config", str(repo_root / "privacy.yaml"),
                              "--out", str(tmp_path / "c.jsonl"),
                              "--audit", str(tmp_path / "a.jsonl"),
                              "--decisions", "fixtures/decisions.example.jsonl"])
    assert res.exit_code == 0, res.output
    assert "reviewer: accept" in res.output
    assert "scorer-vs-human agreement" in res.output
