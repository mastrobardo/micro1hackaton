"""The built fixture matches a frozen ground-truth: seeds present, aliases absent.

`tests/expected/groundtruth.json` is the leak metric's baseline. Regenerate it with
`python -m tests.gen_groundtruth` if the fixture legitimately changes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.conftest import read_tree, scan_entity_hits

EXPECTED = Path(__file__).resolve().parent / "expected" / "groundtruth.json"


@pytest.fixture(scope="module")
def corpus(real_repo) -> str:
    tree = read_tree(real_repo, skip_dirs=(".git", "node_modules"))
    return "\n".join(tree.values())


@pytest.fixture(scope="module")
def expected() -> dict:
    return json.loads(EXPECTED.read_text(encoding="utf-8"))


def test_every_seed_entity_occurs_in_the_fixture(corpus, seed_entities, expected):
    hits = scan_entity_hits(corpus, seed_entities)
    present = {e["id"] for e in seed_entities} - set(expected["absent_by_design"])
    missing = present - hits.keys()
    assert not missing, f"seed entities with no occurrence in the fixture: {missing}"


def test_entity_absent_by_design_is_really_absent(corpus, seed_entities, expected):
    for eid in expected["absent_by_design"]:
        ent = next(e for e in seed_entities if e["id"] == eid)
        hits = scan_entity_hits(corpus, [ent])
        assert hits == {}, f"{eid} was supposed to be absent but occurs {hits}"


def test_occurrence_counts_match_frozen_groundtruth(corpus, seed_entities, expected):
    hits = scan_entity_hits(corpus, seed_entities)
    assert hits == expected["occurrences"]


def test_no_ghost_alias_appears_in_the_real_fixture(corpus, config):
    aliases = sorted({e["ghost"] for e in config["entities"] if e["ghost"]})
    rx = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(re.escape(a) for a in aliases) + r")(?![A-Za-z0-9_])")
    found = sorted(set(rx.findall(corpus)))
    assert not found, f"ghost aliases already present in real fixture (dirty baseline): {found}"
