"""MappingStore: roundtrip, lookups, and the frozen-identity invariant."""
from __future__ import annotations

import hashlib

import pytest

from ghostc.mapping import MappingStore

KW = dict(kind="vendor", level="internal", strategy="semantic_alias")


def test_upsert_save_reload_roundtrip(tmp_path):
    path = tmp_path / "mapping.json"
    s = MappingStore(path)
    s.upsert(entity_id="vendor_a", real="SkyRoute Data Ltd", ghost="vendor-a", **KW)
    s.save()

    reloaded = MappingStore(path)
    e = reloaded.by_entity_id("vendor_a")
    assert e["real"] == "SkyRoute Data Ltd"
    assert e["ghost"] == "vendor-a"
    assert e["frozen"] is True
    assert e["real_sha256"] == hashlib.sha256(b"SkyRoute Data Ltd").hexdigest()


def test_lookups(tmp_path):
    s = MappingStore(tmp_path / "m.json")
    s.upsert(entity_id="vendor_a", real="SkyRoute", ghost="vendor-a", **KW)
    assert s.by_ghost("vendor-a")["entity_id"] == "vendor_a"
    assert s.by_entity_id("nope") is None
    assert s.by_ghost("nope") is None


def test_frozen_ghost_change_raises(tmp_path):
    s = MappingStore(tmp_path / "m.json")
    s.upsert(entity_id="vendor_a", real="SkyRoute", ghost="vendor-a", **KW)
    with pytest.raises(ValueError, match="frozen"):
        s.upsert(entity_id="vendor_a", real="SkyRoute", ghost="vendor-b", **KW)


def test_frozen_allows_same_ghost_and_updates_metadata(tmp_path):
    s = MappingStore(tmp_path / "m.json")
    s.upsert(entity_id="vendor_a", real="SkyRoute", ghost="vendor-a", **KW)
    s.upsert(entity_id="vendor_a", real="SkyRoute Data Ltd", ghost="vendor-a", **KW)
    e = s.by_entity_id("vendor_a")
    assert e["real"] == "SkyRoute Data Ltd"
    assert len(s.data["entries"]) == 1


def test_ghost_identity_stable_across_instances(tmp_path):
    path = tmp_path / "m.json"
    ck = dict(kind="client", level="restricted", strategy="synthetic_id")

    s1 = MappingStore(path)
    s1.upsert(entity_id="c", real="Northwind Airlines", ghost="client-a", **ck)
    s1.save()

    s2 = MappingStore(path)
    assert s2.by_entity_id("c")["ghost"] == "client-a"
    s2.upsert(entity_id="c", real="Northwind Airlines", ghost="client-a", **ck)  # accepted
    with pytest.raises(ValueError):
        s2.upsert(entity_id="c", real="Northwind Airlines", ghost="client-x", **ck)
