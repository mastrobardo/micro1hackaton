"""AuditLog: schema-valid JSONL, deterministic hashing, no cleartext secrets."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from ghostc.audit import AuditLog, hash_real, new_operation_id
from tests.conftest import entity_spellings, load_jsonl

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[1] / "schemas" / "audit-event.schema.json").read_text()
)


def test_hash_real_is_deterministic_and_sha256():
    h = hash_real("Northwind Airlines")
    assert h == hash_real("Northwind Airlines")
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)
    assert h != hash_real("Northwind Airline")


def test_operation_id_shape_and_uniqueness():
    ids = {new_operation_id() for _ in range(50)}
    assert len(ids) == 50
    assert all(i.startswith("op_") for i in ids)


def test_emit_appends_schema_valid_jsonl(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    log.emit("run.start", "compiler", details={"repo": "workspace/real"})
    log.emit("approval.requested", "orchestrator", actor="human:reviewer",
             level="restricted", subject={"entity_id": "client_a"})
    log.emit("run.end", "compiler", details={"entities": 3})

    recs = load_jsonl(log.path)
    assert [r["event"] for r in recs] == ["run.start", "approval.requested", "run.end"]
    assert {r["operation_id"] for r in recs} == {log.operation_id}
    for r in recs:
        jsonschema.Draft202012Validator(SCHEMA).validate(r)


def test_no_seed_real_value_appears_in_compiled_audit(compiled, seed_entities):
    # entity ids are config-chosen and safe (they also appear in the shared ghost spec);
    # what must never appear is a real *value* spelling.
    forbidden = {s for e in seed_entities for s in entity_spellings(e)}
    for rec in load_jsonl(compiled.audit):
        rec.get("subject", {}).pop("entity_id", None)
        blob = json.dumps(rec)
        for spelling in forbidden:
            assert spelling not in blob, f"{spelling!r} leaked into audit event {rec['event']}"


def test_every_detected_entity_carries_only_a_hash(compiled):
    for rec in load_jsonl(compiled.audit):
        if rec["event"] == "compile.entity_detected":
            subj = rec["subject"]
            assert set(subj) == {"entity_id", "real_sha256"}
            assert len(subj["real_sha256"]) == 64


def test_compiled_audit_brackets_the_run(compiled):
    recs = load_jsonl(compiled.audit)
    assert recs[0]["event"] == "run.start"
    assert recs[-1]["event"] == "run.end"
    assert len({r["operation_id"] for r in recs}) == 1
