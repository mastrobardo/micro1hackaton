"""`ghostc.review.model` — the streamlit-free glue the app + tests share."""
from __future__ import annotations

import json

from ghostc.review.model import (config_delta, delta_yaml, load_candidates,
                                 review_rows)
from ghostc.review.store import DecisionStore, surface_key

_CANDS = [
    {"surface": "Meridian Aero Systems", "entity_id": None, "kind": "vendor",
     "level": "internal", "score": 0.99, "action": "review", "evidence": "declared alias",
     "aliases": ["Meridian", "meridianClient"], "proposed_ghost": None,
     "occurrences": [{"surface": "MERIDIAN_API_KEY", "file": "a.js", "line": 1},
                     {"surface": "Meridian", "file": "a.js", "line": 2}]},
    {"surface": "helmet", "entity_id": None, "kind": None, "level": None, "score": 0.2,
     "action": "ignore", "evidence": "weak", "aliases": [], "occurrences": []},
    {"surface": "Northwind Airlines", "entity_id": "client_northwind", "kind": "client",
     "level": "restricted", "score": 1.0, "action": "review", "evidence": "exact",
     "aliases": [], "occurrences": []},
]


def _write_cands(tmp_path):
    p = tmp_path / "candidates.jsonl"
    p.write_text("\n".join(json.dumps(c) for c in _CANDS) + "\n", encoding="utf-8")
    return p


def test_load_and_filter_to_open_proposals(tmp_path):
    cands = load_candidates(_write_cands(tmp_path))
    rows = review_rows(cands, DecisionStore(tmp_path / "d.jsonl"))
    # only the unconfigured, non-ignored proposal
    assert [r["surface"] for r in rows] == ["Meridian Aero Systems"]
    assert rows[0]["occurrences"] == 2 and rows[0]["decision"] is None


def test_apply_decision_records_and_shows_on_next_load(tmp_path):
    cands = load_candidates(_write_cands(tmp_path))
    store = DecisionStore(tmp_path / "d.jsonl")
    from ghostc.review.model import apply_decision
    apply_decision(store, cands[0], "accept", level="confidential",
                   entity_id="vendor_meridian", approved_by="al", note="reseller")
    rows = review_rows(load_candidates(_write_cands(tmp_path)),
                       DecisionStore(tmp_path / "d.jsonl"))
    assert rows[0]["decision"] == "accept" and rows[0]["approved_by"] == "al"


def test_config_delta_adds_accepted_proposal_and_clears_restricted(tmp_path):
    cands = load_candidates(_write_cands(tmp_path))
    store = DecisionStore(tmp_path / "d.jsonl")
    store.record(surface="Meridian Aero Systems", reviewer_action="accept",
                 key=surface_key("Meridian Aero Systems"), entity_id="vendor_meridian",
                 level="confidential", approved_by="al")
    store.record(surface="Northwind Airlines", reviewer_action="accept",
                 key="client_northwind", entity_id="client_northwind",
                 level="restricted", approved_by="al")
    cfg = {"entities": [{"id": "client_northwind", "level": "restricted",
                         "source": "discovered", "real": "Northwind Airlines",
                         "kind": "client", "strategy": "synthetic_id", "ghost": "client-a"}]}
    delta = config_delta(store, cfg, cands)
    assert delta["clear"] == ["client_northwind"]
    assert [e["id"] for e in delta["add"]] == ["vendor_meridian"]
    added = delta["add"][0]
    assert added["source"] == "human" and added["approved_by"] == "al"
    assert added["ghost"].startswith("vendor-")
    # match spellings carried over from the candidate
    assert any(m["value"] == "MERIDIAN_API_KEY" for m in added.get("match", []))
    assert "vendor_meridian" in delta_yaml(delta)


def test_delta_yaml_empty(tmp_path):
    assert "no change" in delta_yaml({"add": [], "clear": []})
