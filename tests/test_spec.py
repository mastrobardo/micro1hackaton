"""Spec compiler: deterministic entity substitution + fail-closed leak gate."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from ghostc.spec import Rejection, compile_spec
from ghostc.mapping import MappingStore
from tests.conftest import load_jsonl

AUDIT_SCHEMA = json.loads(
    (Path(__file__).resolve().parents[1] / "schemas" / "audit-event.schema.json").read_text()
)

REAL_SPELLINGS = ["Northwind Airlines", "Northwind", "SkyRoute Data Ltd", "SkyRoute",
                  "booking-core", "Meridian"]


@pytest.fixture
def mapping(tmp_path) -> Path:
    """A frozen store with three seed entities + one mapping-only (discovered) entity."""
    store = MappingStore(tmp_path / "private" / "mapping.json")
    store.upsert(entity_id="client_northwind", real="Northwind Airlines", ghost="client-a",
                 kind="client", level="restricted", strategy="synthetic_id")
    store.upsert(entity_id="vendor_skyroute", real="SkyRoute Data Ltd", ghost="vendor-a",
                 kind="vendor", level="confidential", strategy="semantic_alias")
    store.upsert(entity_id="svc_booking_core", real="booking-core", ghost="service-a",
                 kind="internal_service", level="confidential", strategy="semantic_alias")
    # only in the store — as if `discover` proposed it and `compile --auto_alias` froze it
    store.upsert(entity_id="vendor_meridian", real="Meridian", ghost="vendor-e",
                 kind="vendor", level="internal", strategy="semantic_alias")
    store.save()
    return store.path


def _run(task, privacy_yaml, mapping, tmp_path, **kw):
    return compile_spec(
        task, config_path=str(privacy_yaml), mapping_path=str(mapping),
        audit_path=str(tmp_path / "audit.jsonl"),
        out_path=str(tmp_path / "ghost-task.md"), **kw)


def _norm(s: str) -> str:
    """Collapse the casing engine's context-varying spellings ('Client A' / 'client-a')."""
    return s.lower().replace(" ", "-")


def test_substitutes_seed_entities(privacy_yaml, mapping, tmp_path):
    task = ("Add a GET /fares endpoint for Northwind Airlines that calls the "
            "booking-core service via the SkyRoute Data Ltd provider.")
    spec = _run(task, privacy_yaml, mapping, tmp_path)

    for real in ("Northwind", "booking-core", "SkyRoute"):
        assert real not in spec.ghost_task
    for ghost in ("client-a", "service-a", "vendor-a"):
        assert ghost in _norm(spec.ghost_task)
    assert {"client_northwind", "svc_booking_core", "vendor_skyroute"} <= {
        s.entity_id for s in spec.substitutions}


def test_substitutes_mapping_only_discovered_entity(privacy_yaml, mapping, tmp_path):
    spec = _run("Add a new endpoint from Meridian.", privacy_yaml, mapping, tmp_path)

    assert "eridian" not in spec.ghost_task            # 'Meridian' / 'meridian'
    assert "vendor" in spec.ghost_task.lower()
    assert "vendor_meridian" in {s.entity_id for s in spec.substitutions}


def test_leak_gate_fails_closed(monkeypatch, privacy_yaml, mapping, tmp_path):
    # simulate the substitution engine missing a spelling
    monkeypatch.setattr("ghostc.spec.transform_text",
                        lambda text, kind, matchers, base=0: (text, []))
    out = tmp_path / "ghost-task.md"
    audit = tmp_path / "audit.jsonl"

    with pytest.raises(Rejection):
        compile_spec("Endpoint for Northwind Airlines.", config_path=str(privacy_yaml),
                     mapping_path=str(mapping), audit_path=str(audit), out_path=str(out))

    assert not out.exists()                            # nothing written
    events = [r["event"] for r in load_jsonl(audit)]
    assert "spec.rejected" in events and "spec.compiled" not in events
    assert "Northwind" not in audit.read_text()        # no cleartext in the audit


def test_audit_is_schema_valid_and_carries_no_cleartext(privacy_yaml, mapping, tmp_path):
    task = ("Rewire booking-core to talk to Meridian instead of SkyRoute Data Ltd "
            "for Northwind Airlines.")
    _run(task, privacy_yaml, mapping, tmp_path)

    blob = (tmp_path / "audit.jsonl").read_text()
    v = jsonschema.Draft202012Validator(AUDIT_SCHEMA)
    for rec in load_jsonl(tmp_path / "audit.jsonl"):
        v.validate(rec)
    for spelling in REAL_SPELLINGS:
        assert spelling not in blob


def test_deterministic(privacy_yaml, mapping, tmp_path):
    task = "Add a health check to booking-core for Northwind Airlines."
    a = _run(task, privacy_yaml, mapping, tmp_path, operation_id="op_fixed")
    b = _run(task, privacy_yaml, mapping, tmp_path, operation_id="op_fixed")
    assert a.ghost_task == b.ghost_task
    assert [s.to_dict() for s in a.substitutions] == [s.to_dict() for s in b.substitutions]


def test_task_md_has_no_real_values_but_object_keeps_real_task(privacy_yaml, mapping, tmp_path):
    task = "Add pricing to booking-core for Northwind Airlines and SkyRoute Data Ltd."
    spec = _run(task, privacy_yaml, mapping, tmp_path)

    md = (tmp_path / "ghost-task.md").read_text()
    for spelling in REAL_SPELLINGS:
        assert spelling not in md
    assert spec.real_task == task                      # kept in memory, never on disk ghost-side


def test_task_with_no_known_entity_is_not_an_error(privacy_yaml, mapping, tmp_path):
    spec = _run("Bump the default rate-limit window from 15 to 20 minutes.",
                privacy_yaml, mapping, tmp_path)
    assert spec.substitutions == []
    assert (tmp_path / "ghost-task.md").exists()
    assert "spec.compiled" in [r["event"] for r in load_jsonl(tmp_path / "audit.jsonl")]
