"""`ghostc.screen` — the outbound gate for entities the compiler never knew about.

The compiler is closed-world: it substitutes what `privacy.yaml` + `mapping.json`
name, and its leak scan looks for those same real spellings. These tests pin the
second gate — what happens to a sensitive value that was in neither.
"""
from __future__ import annotations

import json

from pathlib import Path

import pytest

from ghostc.detect.settings import DEFAULTS
from ghostc.review.store import DecisionStore
from ghostc.screen import ScreenError, screen_text, write_findings

_CFG = {
    "mapping_version": 1,
    "entities": [
        {"id": "client_northwind", "kind": "client", "level": "restricted",
         "strategy": "alias", "real": "Northwind Airlines", "ghost": "Client A"},
        {"id": "vendor_skyroute", "kind": "vendor", "level": "internal",
         "strategy": "alias", "real": "SkyRoute Data Ltd", "ghost": "@vendor-a/sdk"},
    ],
}

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"

CLEAN = "Add a booking endpoint for Client A using the @vendor-a/sdk client."


def _screen(text, **kw):
    kw.setdefault("cfg", _CFG)
    kw.setdefault("mapping_path", None)
    kw.setdefault("candidates_path", None)
    return screen_text(text, **kw)


# -- the layers -------------------------------------------------------------- #

def test_clean_ghost_text_passes():
    res = _screen(CLEAN)
    assert res.findings == [] and not res.blocked
    assert res.metrics()["screen_findings"] == 0


def test_ghost_aliases_are_not_findings():
    """`@vendor-a/sdk` matches the scoped-package shape. It is the compiler's own
    output, so it must never gate — that would make every compiled task fail."""
    res = _screen("Install @vendor-a/sdk and call it from Client A's handler.")
    assert [c.surface for c in res.findings] == []


def test_shape_finding_blocks():
    res = _screen("Point the job at gw.prod.contoso.internal before Friday.")
    assert res.blocked
    assert [c.surface for c in res.flagged] == ["gw.prod.contoso.internal"]
    assert res.flagged[0].kind == "domain" and res.flagged[0].level == "confidential"
    assert "gw.prod.contoso.internal" in res.summary()


def test_email_is_a_restricted_person_finding():
    res = _screen("Ask priya.nair@northwind.example to confirm the schema.")
    assert res.blocked and res.flagged[0].level == "restricted"


def test_screen_never_auto_transforms():
    """No screen signal is a *hard* signal, so `classify` can only ever say
    review/ignore here. The screener queues; it does not decide."""
    res = _screen("secrets: mas_live_9f8e7d6c5b4a3210 and gw.prod.contoso.internal")
    assert res.findings and all(c.action in ("review", "ignore") for c in res.findings)


def test_restricted_structural_hit_is_queued_below_threshold():
    """The email shape weighs 0.35 — under `review_threshold` — because in a *repo*
    it is usually a package author. In an outbound document it is a person, and
    restricted material never crosses unreviewed."""
    res = _screen("Ping ops@example.com.")
    assert res.findings[0].score < DEFAULTS.review_threshold
    assert res.findings[0].action == "review" and res.blocked


def test_restricted_floor_does_not_apply_to_the_adjudicator_alone():
    """A shape is a fact about the text; an LLM accusation is an opinion. A weak
    opinion about a restricted kind gets scored, not floored."""
    def adj(ghost, real):
        return [{"surface": "Halcyon", "kind": "client", "confidence": 0.1}]

    res = _screen("The Halcyon rollout is next week.", adjudicator=adj)
    assert res.findings[0].action == "ignore" and not res.blocked


def test_anchor_layer_flags_an_unfrozen_discover_proposal(tmp_path):
    cands = tmp_path / "candidates.jsonl"
    cands.write_text(json.dumps({
        "surface": "Meridian", "entity_id": None, "kind": "vendor", "level": "internal",
        "score": 0.99, "action": "review", "aliases": ["Meridian Aero Systems"]}) + "\n",
        encoding="utf-8")
    res = _screen("Wire the Meridian feed into the booking core.",
                  candidates_path=str(cands))
    assert res.blocked and res.flagged[0].surface == "Meridian"
    assert res.flagged[0].evidence  # carries the discover score in the signal detail

    # ... and an alias spelling of the same proposal is caught too
    assert _screen("Meridian Aero Systems owns the feed.",
                   candidates_path=str(cands)).blocked


def test_layers_accumulate_by_noisy_or(tmp_path):
    cands = tmp_path / "candidates.jsonl"
    cands.write_text(json.dumps({
        "surface": "gw.prod.contoso.internal", "entity_id": None, "kind": "domain",
        "level": "confidential", "score": 0.9, "action": "review", "aliases": []}) + "\n",
        encoding="utf-8")
    one = _screen("host gw.prod.contoso.internal")
    both = _screen("host gw.prod.contoso.internal", candidates_path=str(cands))
    assert both.findings[0].score > one.findings[0].score


# -- the adjudicator seam ---------------------------------------------------- #

def test_adjudicator_claim_is_anchored_to_the_outbound_text():
    """A claim the model invents — or one that only exists in the real half of its
    prompt — must not score. Only verbatim occurrences in the ghost text count."""
    def adj(ghost, real):
        return [{"surface": "Northwind Airlines", "kind": "client", "confidence": 1.0,
                 "why": "only in the real task"},
                {"surface": "Halcyon Freight", "kind": "client", "confidence": 0.9,
                 "why": "unsubstituted client"}]

    res = _screen("Add a Halcyon Freight tariff table for Client A.",
                  real_text="Add a Northwind Airlines tariff table.", adjudicator=adj)
    assert [c.surface for c in res.flagged] == ["Halcyon Freight"]
    assert res.llm == {"status": "ran", "claims": 2, "anchored": 1, "dropped": 1}


def test_adjudicator_alone_reviews_but_never_reaches_auto():
    def adj(ghost, real):
        return [{"surface": "Halcyon", "kind": "client", "confidence": 1.0}]

    res = _screen("The Halcyon rollout is next week.", adjudicator=adj)
    assert res.flagged[0].score <= DEFAULTS.auto_threshold
    assert res.flagged[0].score >= DEFAULTS.review_threshold
    assert res.blocked


def test_adjudicator_failure_is_survivable():
    def adj(ghost, real):
        raise RuntimeError("529 overloaded")

    res = _screen("Point the job at gw.prod.contoso.internal.", adjudicator=adj)
    assert res.llm["status"] == "error"
    assert res.blocked          # the deterministic layer still gates


# -- policy ------------------------------------------------------------------ #

def test_warn_mode_scores_without_gating():
    res = _screen("host gw.prod.contoso.internal", mode="warn")
    assert res.flagged and not res.blocked


def test_off_mode_skips_the_pass():
    res = _screen("host gw.prod.contoso.internal", mode="off")
    assert res.findings == [] and not res.blocked and res.llm["status"] == "off"


def test_bad_mode_rejected():
    with pytest.raises(ScreenError):
        _screen(CLEAN, mode="maybe")


def test_reviewer_ignore_suppresses_a_finding_permanently(tmp_path):
    d = tmp_path / "decisions.jsonl"
    text = "Ping ops@example.com about the migration."
    assert _screen(text, decisions_path=str(d)).blocked

    DecisionStore(d).record(surface="ops@example.com", reviewer_action="ignore",
                            proposed_action="review", note="shared team alias")
    res = _screen(text, decisions_path=str(d))
    assert not res.blocked and res.suppressed == 1


def test_reviewer_accept_keeps_blocking(tmp_path):
    """Accepting a proposal does not sanitize anything — the entity still has to
    reach `privacy.yaml` before the compiler can substitute it, so the gate holds."""
    d = tmp_path / "decisions.jsonl"
    DecisionStore(d).record(surface="ops@example.com", reviewer_action="accept",
                            entity_id="person_ops", level="restricted")
    assert _screen("Ping ops@example.com.", decisions_path=str(d)).blocked


# -- observability ----------------------------------------------------------- #

def test_audit_events_are_hash_only(tmp_path):
    audit = tmp_path / "audit.jsonl"
    res = _screen("host gw.prod.contoso.internal", audit_path=str(audit))
    events = [json.loads(ln) for ln in audit.read_text(encoding="utf-8").splitlines()]
    assert [e["event"] for e in events] == ["screen.scanned", "screen.blocked"]
    assert "gw.prod.contoso.internal" not in audit.read_text(encoding="utf-8")
    assert events[1]["details"]["findings"][0]["real_sha256"]
    assert res.metrics()["screen_blocked"] is True


def test_screen_events_validate_against_the_audit_schema(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((_SCHEMA_DIR / "audit-event.schema.json").read_text(encoding="utf-8"))
    v = jsonschema.Draft202012Validator(schema)
    audit = tmp_path / "audit.jsonl"
    _screen("host gw.prod.contoso.internal", audit_path=str(audit))
    _screen("nothing to see", audit_path=str(audit), mode="off")
    for line in audit.read_text(encoding="utf-8").splitlines():
        v.validate(json.loads(line))


def test_metrics_carry_no_surfaces():
    res = _screen("host gw.prod.contoso.internal")
    assert "contoso" not in json.dumps(res.metrics())


def test_write_findings_appends_jsonl(tmp_path):
    res = _screen("host gw.prod.contoso.internal")
    p = write_findings(res, tmp_path / "screen-findings.jsonl")
    rows = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["surface"] == "gw.prod.contoso.internal"
    assert rows[0]["source"] == "ghost_task" and rows[0]["op_id"] == res.operation_id


def test_findings_file_is_readable_by_the_review_board(tmp_path):
    """`write_findings` emits the Candidate shape, so `ghostc-review --candidates
    <screen-findings.jsonl>` triages screen findings with no new code."""
    from ghostc.review.model import load_candidates, review_rows

    res = _screen("Point it at gw.prod.contoso.internal and ping ops@x.example")
    p = write_findings(res, tmp_path / "screen-findings.jsonl")
    rows = review_rows(load_candidates(p), DecisionStore(tmp_path / "d.jsonl"))
    assert [r["surface"] for r in rows] == ["gw.prod.contoso.internal", "ops@x.example"]
    assert all(r["decision"] is None for r in rows)
