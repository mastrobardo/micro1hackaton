"""`ghostc.review.store.DecisionStore` — append-only log, latest-wins, agreement."""
from __future__ import annotations

import json

from ghostc.audit import AuditLog
from ghostc.review.store import DecisionStore, surface_key


def _store(tmp_path):
    return DecisionStore(tmp_path / "decisions.jsonl")


def test_record_appends_and_reloads(tmp_path):
    s = _store(tmp_path)
    s.record(surface="Meridian", reviewer_action="accept", entity_id="vendor_m",
             level="confidential", approved_by="al")
    # a fresh handle sees the persisted record
    again = DecisionStore(tmp_path / "decisions.jsonl")
    assert len(again.records) == 1
    r = again.records[0]
    assert r["surface"] == "Meridian" and r["entity_id"] == "vendor_m"
    assert r["reviewer_action"] == "accept" and r["approved_by"] == "al"
    assert r["key"] == "vendor_m"


def test_latest_supersedes_but_history_is_kept(tmp_path):
    s = _store(tmp_path)
    k = surface_key("Contoso")
    s.record(surface="Contoso", reviewer_action="ignore", key=k)
    s.record(surface="Contoso", reviewer_action="accept", key=k,
             entity_id="v_c", approved_by="al", level="confidential")
    assert len(s.history(k)) == 2
    assert s.latest()[k]["reviewer_action"] == "accept"


def test_escalate_defaults_level_restricted(tmp_path):
    s = _store(tmp_path)
    r = s.record(surface="X", reviewer_action="escalate", entity_id="e_x")
    assert r["level"] == "restricted"


def test_cleared_restricted_needs_accept_and_approver(tmp_path):
    s = _store(tmp_path)
    s.record(surface="A", reviewer_action="accept", entity_id="e_a")          # no approver
    s.record(surface="B", reviewer_action="accept", entity_id="e_b", approved_by="al")
    s.record(surface="C", reviewer_action="escalate", entity_id="e_c", approved_by="al")
    assert s.cleared_restricted() == {"e_b"}


def test_ignored_and_accepted_partition(tmp_path):
    s = _store(tmp_path)
    s.record(surface="A", reviewer_action="ignore", key=surface_key("A"))
    s.record(surface="B", reviewer_action="accept", entity_id="e_b")
    assert s.ignored_keys() == {surface_key("A")}
    assert [r["entity_id"] for r in s.accepted()] == ["e_b"]


def test_summarize_agreement(tmp_path):
    s = _store(tmp_path)
    # scorer said review, human accepted -> agree
    s.record(surface="A", reviewer_action="accept", entity_id="a", proposed_action="review")
    # scorer said review, human ignored -> disagree (override)
    s.record(surface="B", reviewer_action="ignore", key=surface_key("B"),
             proposed_action="review")
    # scorer said ignore, human ignored -> agree
    s.record(surface="C", reviewer_action="ignore", key=surface_key("C"),
             proposed_action="ignore")
    sm = s.summarize()
    assert sm["n_decisions"] == 3 and sm["n_agree"] == 2
    assert sm["agreement_rate"] == round(2 / 3, 3)
    assert sm["overrides"] == 1


def test_record_emits_hash_only_audit_event(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    s = _store(tmp_path)
    s.record(surface="SecretCorp", reviewer_action="accept", entity_id="v_s",
             approved_by="al", audit=AuditLog(audit_path))
    events = [json.loads(x) for x in audit_path.read_text().splitlines()]
    ev = next(e for e in events if e["event"] == "review.decision_recorded")
    assert ev["component"] == "review" and ev["decision"] == "accept"
    assert "SecretCorp" not in audit_path.read_text()          # cleartext never logged
    assert ev["subject"]["real_sha256"] and ev["subject"]["entity_id"] == "v_s"


def test_bad_action_rejected(tmp_path):
    s = _store(tmp_path)
    try:
        s.record(surface="X", reviewer_action="maybe")
    except ValueError as e:
        assert "reviewer_action" in str(e)
    else:
        raise AssertionError("expected ValueError")
