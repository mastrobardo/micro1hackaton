"""ghostc discover — recall on the seeded layer, precision against OSS libraries,
and the candidates / audit artifacts. Fixture-gated: skips without workspace/real.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ghostc.discover import discover_repo
from tests.conftest import load_jsonl

GROUNDTRUTH = json.loads(
    (Path(__file__).resolve().parent / "expected" / "discover-groundtruth.json")
    .read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def discovered(tmp_path_factory, real_repo, privacy_yaml):
    out = tmp_path_factory.mktemp("discover")
    return discover_repo(str(real_repo), config_path=str(privacy_yaml),
                         out=str(out / "candidates.jsonl"),
                         audit_path=str(out / "audit.jsonl"))


def test_configured_entities_are_refound_from_code(discovered):
    found = {c.entity_id for c in discovered.scan.candidates
             if c.entity_id and c.action != "ignore"}
    expected = set(GROUNDTRUTH["configured_expected"])
    missing = expected - found
    assert not missing, f"discover missed configured entities: {sorted(missing)}"
    assert discovered.metrics["recall_configured"] >= GROUNDTRUTH["configured_recall_min"]


def test_absent_by_design_entity_is_not_claimed(discovered):
    found = {c.entity_id for c in discovered.scan.candidates
             if c.entity_id and c.action != "ignore"}
    assert "vendor_aerofeed" not in found        # not present in the fixture


@pytest.mark.parametrize("name", list(GROUNDTRUTH["proposals_expected"]))
def test_unconfigured_entity_is_proposed(discovered, name):
    spec = GROUNDTRUTH["proposals_expected"][name]
    stems = set(spec["stems"])
    hit = [
        c for c in discovered.proposals
        if c.score >= spec["min_score"] and stems & _tokens(c)
    ]
    assert hit, f"{name}: no proposal with stems {stems} at score ≥ {spec['min_score']}"


def test_no_oss_library_is_proposed(discovered):
    surfaces = {c.surface.lower() for c in discovered.scan.candidates
                if c.action != "ignore"}
    surfaces |= {a.lower() for c in discovered.scan.candidates
                 if c.action != "ignore" for a in c.aliases}
    leaked = sorted(t for t in GROUNDTRUTH["precision_denylist"] if t.lower() in surfaces)
    assert not leaked, f"discover proposed known-public tokens: {leaked}"


def test_meridian_aggregates_its_disguises(discovered):
    mer = next((c for c in discovered.proposals if "meridian" in _tokens(c)), None)
    assert mer is not None
    forms = " ".join([mer.surface, *mer.aliases]).lower()
    # camel identifier, SCREAMING env var, scoped package, acronym — one candidate
    assert "mas" in _tokens(mer)
    assert len(mer.occurrences) >= 10


def test_candidates_jsonl_is_valid_and_ranked(discovered):
    rows = load_jsonl(discovered.candidates_path)
    assert rows and all({"surface", "score", "action", "signals"} <= r.keys() for r in rows)
    scores = [r["score"] for r in rows]
    assert scores == sorted(scores, reverse=True)


def test_audit_has_discover_events_without_cleartext(discovered, seed_entities):
    audit = discovered.candidates_path.parent / "audit.jsonl"
    recs = load_jsonl(audit)
    events = {r["event"] for r in recs}
    assert {"run.start", "discover.candidate_scored", "run.end"} <= events
    assert any(r["event"] == "discover.entity_proposed" for r in recs)
    blob = audit.read_text(encoding="utf-8")
    for ent in seed_entities:
        assert ent["real"] not in blob


def test_restricted_proposal_is_never_auto(discovered):
    for c in discovered.scan.candidates:
        if c.level == "restricted":
            assert c.action != "auto"


def _tokens(cand) -> set[str]:
    raw = " ".join([cand.surface, *cand.aliases]).lower()
    for ch in "/._-:@":
        raw = raw.replace(ch, " ")
    return set(raw.split())
