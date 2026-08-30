"""Detection scoring core: noisy-OR combination, action classification, and the
lexical helpers (tokenizer, structural shapes, de-obfuscation). All synthetic —
no fixture required.
"""
from __future__ import annotations

import pytest

from ghostc.detect.candidate import (
    Signal,
    classify,
    combine_score,
    evidence_label,
    has_hard_evidence,
)
from ghostc.detect.decode import decoded_literals
from ghostc.detect.settings import DEFAULTS, detection_settings
from ghostc.detect.shapes import shape_hits
from ghostc.detect.tokenize import contains_run, segments, tokens, words


# -- noisy-OR score combination ------------------------------------------------

def test_exact_signal_short_circuits_to_one():
    assert combine_score([Signal("exact", 1.0), Signal("weak", 0.02)]) == 1.0


def test_independent_signals_accumulate():
    # 1 - (1-0.9)(1-0.85) = 0.985
    assert combine_score([Signal("import_ref", 0.9), Signal("stem", 0.85)]) == 0.985


def test_no_signal_is_zero():
    assert combine_score([]) == 0.0
    assert combine_score([Signal("noise", 0.0)]) == 0.0


def test_score_is_monotonic_in_evidence():
    base = [Signal("fuzzy", 0.6)]
    more = base + [Signal("shape", 0.45)]
    assert combine_score(more) > combine_score(base)


# -- hard vs soft evidence ---------------------------------------------------

@pytest.mark.parametrize("name", ["exact", "stem", "import_ref", "symbol_context"])
def test_structural_signals_are_hard(name):
    assert has_hard_evidence([Signal(name, 0.5)])


def test_graph_is_hard_only_when_strong():
    assert not has_hard_evidence([Signal("graph", 0.7)])
    assert has_hard_evidence([Signal("graph", 0.92)])


@pytest.mark.parametrize("name", ["fuzzy", "semantic", "shape", "acronym"])
def test_lexical_signals_are_not_hard(name):
    assert not has_hard_evidence([Signal(name, 0.99)])


# -- action classification -------------------------------------------------

def test_high_score_with_hard_signal_auto_transforms_configured_entity():
    action = classify(score=0.97, level="confidential", resolved=True,
                      signals=[Signal("stem", 0.85), Signal("import_ref", 0.9)],
                      settings=DEFAULTS)
    assert action == "auto"


def test_restricted_never_auto_even_at_full_confidence():
    action = classify(score=1.0, level="restricted", resolved=True,
                      signals=[Signal("exact", 1.0)], settings=DEFAULTS)
    assert action == "review"


def test_unconfigured_proposal_needs_auto_alias_to_transform():
    sig = [Signal("stem", 0.9), Signal("import_ref", 0.9)]
    off = classify(score=0.99, level="confidential", resolved=False,
                   signals=sig, settings=detection_settings({}))
    on = classify(score=0.99, level="confidential", resolved=False, signals=sig,
                  settings=detection_settings({"detection": {"auto_alias": True}}))
    assert off == "review" and on == "auto"


def test_fuzzy_only_high_score_stays_in_review():
    action = classify(score=0.95, level="confidential", resolved=False,
                      signals=[Signal("fuzzy", 0.8), Signal("semantic", 0.44)],
                      settings=DEFAULTS)
    assert action == "review"


def test_low_score_is_ignored():
    action = classify(score=0.1, level=None, resolved=False,
                      signals=[Signal("weak", 0.1)], settings=DEFAULTS)
    assert action == "ignore"


def test_thresholds_are_configurable():
    s = detection_settings({"detection": {"auto_threshold": 0.5, "review_threshold": 0.2}})
    assert s.auto_threshold == 0.5 and s.review_threshold == 0.2
    assert classify(score=0.55, level="internal", resolved=True,
                    signals=[Signal("stem", 0.55)], settings=s) == "auto"


# -- evidence label -------------------------------------------------------

def test_evidence_label_reads_like_the_report():
    assert evidence_label([Signal("exact", 1.0)]) == "exact"
    assert evidence_label([Signal("import_ref", 0.9)]) == "package / import"
    assert evidence_label([Signal("semantic", 0.4)]) == "semantic only"
    assert evidence_label([]) == "weak / no evidence"
    combo = evidence_label([Signal("stem", 0.85), Signal("graph", 0.7)])
    assert "identifier token" in combo and "reference graph" in combo


# -- tokenizer ----------------------------------------------------------

@pytest.mark.parametrize("token,expected", [
    ("MERIDIAN_API_KEY", ["meridian", "api", "key"]),
    ("api.meridianaero.example", ["api", "meridianaero", "example"]),
    ("getMeridianSchedules", ["get", "meridian", "schedules"]),
    ("@meridianaero/flight-sdk", ["meridianaero", "flight", "sdk"]),
    ("third_party_meridian_inventory", ["third", "party", "meridian", "inventory"]),
])
def test_segments_split_every_separator_and_camel(token, expected):
    assert segments(token) == expected


def test_contains_run_finds_stem_inside_compound():
    assert contains_run(segments("MERIDIAN_API_KEY"), ["meridian"]) == 0
    assert contains_run(segments("get_booking_core_url"), ["booking", "core"]) == 1
    assert contains_run(segments("unrelated_token"), ["meridian"]) is None


def test_tokens_carry_spans_and_norm():
    got = tokens("use MERIDIAN_API_KEY here")
    tok = next(t for t in got if "MERIDIAN" in t.text)
    assert tok.text == "MERIDIAN_API_KEY"
    assert "use ".__len__() == tok.start
    assert tok.norm == "meridian-api-key"


def test_words_lowercases_prose():
    assert words("Meridian Aero Systems GmbH") == ["meridian", "aero", "systems", "gmbh"]


# -- structural shapes -------------------------------------------------

@pytest.mark.parametrize("text,kind", [
    ("mas_live_7d8f3a91c4e52b019f7a", "prefixed_secret"),
    ("mas-client-secret-4b7c91e2a6", "named_secret"),
    ("MAS-EU-2025-041", "contract_id"),
    ("tenant-meridian-eu-prod-17", "tenant_id"),
    ("gw.prod.contoso.internal", "internal_host"),
    ("@meridianaero/flight-sdk", "scoped_npm_package"),
    ("10.20.4.7", "rfc1918_ip"),
    ("priya.nair@northwind-internal.net", "email"),
])
def test_shape_family_is_recognised(text, kind):
    kinds = {h.kind for h in shape_hits(text)}
    assert kind in kinds


def test_shape_weight_keeps_it_review_only():
    for h in shape_hits("mas_live_7d8f3a91c4e52b019f7a AKIA0123456789ABCDEF"):
        assert h.weight < DEFAULTS.auto_threshold


def test_plain_prose_has_no_shape():
    assert shape_hits("the quick brown fox jumps over the lazy dog") == []


# -- de-obfuscation --------------------------------------------------

def test_string_concat_is_folded():
    src = "const x = 'https://' + 'gw.prod.' + 'contoso.' + 'internal';"
    assert any(d.text == "https://gw.prod.contoso.internal" and d.method == "concat"
               for d in decoded_literals(src))


def test_array_join_is_folded():
    src = "const e = ['MERIDIAN', 'API', 'KEY'].join('_');"
    assert any(d.text == "MERIDIAN_API_KEY" and d.method == "join"
               for d in decoded_literals(src))


def test_base64_blob_is_decoded():
    # base64("Meridian Aero Systems")
    src = "const n = 'TWVyaWRpYW4gQWVybyBTeXN0ZW1z';"
    assert any(d.text == "Meridian Aero Systems" and d.method == "base64"
               for d in decoded_literals(src))


def test_ordinary_code_decodes_to_nothing():
    src = "const total = count + 1;\nconst name = user.firstName;\n"
    assert decoded_literals(src) == []


# -- reference graph -------------------------------------------------------

_LAUNDER_JS = """
const { AcmeClient: RestrictedClient } = require('@acmecorp/sdk');
const client = new RestrictedClient({ key: process.env.ACME_KEY });
const provider = client;
const registry = { primary: provider };
registry.primaryKey = process.env.ACME_KEY;
module.exports = { provider };
"""


def test_graph_taint_follows_alias_chain():
    from ghostc.detect.graph import build_graph, str_node

    rg = build_graph({"a.js": (_LAUNDER_JS, "javascript")})
    taint = rg.taint({str_node("@acmecorp/sdk"): 0.95}, decay=0.85, floor_hops=4)
    assert taint["RestrictedClient"].score == pytest.approx(0.8075, abs=1e-3)
    assert "client" in taint and "provider" in taint
    assert taint["provider"].hops == 3
    assert "provider" in rg.exported


def test_graph_taint_decays_and_stops_at_floor():
    from ghostc.detect.graph import build_graph, str_node

    rg = build_graph({"a.js": (_LAUNDER_JS, "javascript")})
    shallow = rg.taint({str_node("@acmecorp/sdk"): 0.95}, decay=0.85, floor_hops=1)
    assert "client" not in shallow          # 2 hops, past the floor


# -- entity profiles + per-surface signals --------------------------------

def _profile(**kw):
    from ghostc.detect.signals import profile_from_config

    base = {"id": "e", "real": "Meridian Aero Systems", "kind": "vendor",
            "level": "confidential",
            "match": [{"kind": "literal", "value": "Meridian"},
                      {"kind": "identifier", "value": "meridian"},
                      {"kind": "identifier", "value": "MAS"}]}
    base.update(kw)
    return profile_from_config(base)


def test_profile_splits_names_stems_aliases():
    p = _profile()
    assert "Meridian Aero Systems" in p.names
    assert ["meridian", "aero", "systems"] in p.stems
    assert "MAS" in p.aliases


def test_stem_signal_matches_run_inside_compound():
    from ghostc.detect.signals import stem_signal
    from ghostc.detect.tokenize import segments

    s = stem_signal(segments("getMeridianSchedules"), _profile())
    assert s is not None and s.name == "stem"


def test_fuzzy_signal_ignores_bare_generic_words():
    from ghostc.detect.signals import fuzzy_signal

    assert fuzzy_signal("Systems", _profile(), min_len=6, min_ratio=88) is None


def test_alias_enumeration_is_parsed_from_a_comment():
    from ghostc.detect.signals import alias_enumerations

    comment = """
     * The vendor is also known internally as:
     *   - Meridian
     *   - MAS
     *   - meridianaero
     *   - meridian-flight
    """
    groups = alias_enumerations(comment)
    assert groups and "meridianaero" in {i.lower() for i in groups[0]}
