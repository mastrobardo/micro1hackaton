"""Entity matchers: node-kind gating, compound tokens, span/level/remove tie-breaks."""
from __future__ import annotations

import pytest

from ghostc.matching import build_matchers, transform_text

LEVELS = {
    "public": {"transform": False, "approval": "none"},
    "internal": {"transform": True, "approval": "auto"},
    "confidential": {"transform": True, "approval": "auto_if_unambiguous"},
    "restricted": {"transform": True, "approval": "human", "blocks_sync": True},
}
STRATEGIES = ["semantic_alias", "synthetic_id", "synthetic_endpoint", "generalize", "remove"]


def make_config(entities):
    return {
        "version": 1, "mapping_version": 1, "levels": LEVELS,
        "strategies": STRATEGIES, "defaults_by_kind": {}, "exclusions": [],
        "entities": entities,
    }


def ent(**kw):
    base = dict(kind="vendor", level="internal", strategy="semantic_alias")
    base.update(kw)
    return base


@pytest.fixture(scope="module")
def seed_matchers(request):
    from ghostc.config import load_config

    root = request.config.rootpath
    return build_matchers(load_config(root / "privacy.yaml"))


def apply(text, kind, matchers):
    return transform_text(text, kind, matchers)[0]


# -- node-kind gating ------------------------------------------------------

def test_literal_only_fires_in_text_not_identifier(seed_matchers):
    # "datadoghq" is a literal for vendor_datadog; not a stem
    assert apply("datadoghq", "identifier", seed_matchers) == "datadoghq"
    assert apply("datadoghq", "string", seed_matchers) == "vendor-c"
    assert apply("datadoghq", "comment", seed_matchers) == "vendor-c"


def test_identifier_stem_recased_in_place(seed_matchers):
    assert apply("bookingCore", "identifier", seed_matchers) == "serviceA"
    assert apply("BOOKING_CORE_URL", "identifier", seed_matchers) == "SERVICE_A_URL"


# -- compound tokens ----------------------------------------------------

def test_two_entities_in_one_compound_token(seed_matchers):
    assert apply("northwind-skyroute-connector", "string", seed_matchers) == \
        "client-a-vendor-a-connector"


def test_name_shaped_literal_keeps_prose_casing(seed_matchers):
    assert apply("Northwind Airlines", "string", seed_matchers) == "Client A"


# -- tie-breaks -------------------------------------------------------

def test_longest_span_wins():
    cfg = make_config([
        ent(id="dom", real="api.example.internal", kind="domain",
            level="confidential", strategy="synthetic_endpoint", ghost="host-a.example"),
        ent(id="word", real="example", kind="vendor", level="internal", ghost="vendor-a"),
    ])
    m = build_matchers(cfg)
    assert apply("see api.example.internal now", "comment", m) == "see host-a.example now"


def test_restricted_beats_internal_on_equal_span():
    cfg = make_config([
        ent(id="low", real="Acme", level="internal", ghost="vendor-a"),
        ent(id="high", real="Acme", level="restricted", ghost="vendor-b"),
    ])
    out, hits = transform_text("Acme", "string", build_matchers(cfg))
    assert out == "VendorB" and [h.entity_id for h in hits] == ["high"]


def test_remove_beats_alias_on_equal_span():
    cfg = make_config([
        ent(id="alias", real="Acme", level="restricted", ghost="vendor-a"),
        ent(id="drop", real="Acme", kind="secret", level="restricted",
            strategy="remove", ghost=""),
    ])
    out, hits = transform_text("Acme", "string", build_matchers(cfg))
    assert out == "" and [h.entity_id for h in hits] == ["drop"]


def test_secret_removal_covers_inner_stem(seed_matchers):
    # the API key literal spans the whole token and outranks the inner "northwind" stem
    assert apply("sk_live_northwind_9f3ab7c21e5d4088", "string", seed_matchers) == ""


def test_no_candidates_returns_text_unchanged(seed_matchers):
    text = "const users = getUsers();"
    assert apply(text, "identifier", seed_matchers) == text
    assert transform_text(text, "string", seed_matchers)[1] == []
