"""The three JSON schemas are well-formed Draft 2020-12 and the live artifacts validate."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from tests.conftest import load_jsonl

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"
SCHEMAS = ["privacy-config.schema.json", "mapping.schema.json", "audit-event.schema.json"]


@pytest.mark.parametrize("name", SCHEMAS)
def test_schema_is_valid_draft202012(name):
    schema = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)


def _validator(name):
    return jsonschema.Draft202012Validator(
        json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    )


def test_privacy_yaml_validates(repo_root):
    import yaml

    cfg = yaml.safe_load((repo_root / "privacy.yaml").read_text(encoding="utf-8"))
    _validator("privacy-config.schema.json").validate(cfg)


def test_sample_mapping_validates(tmp_path):
    from ghostc.mapping import MappingStore

    store = MappingStore(tmp_path / "mapping.json")
    store.upsert(entity_id="vendor_x", real="Acme Corp", ghost="vendor-a",
                kind="vendor", level="internal", strategy="semantic_alias")
    store.upsert(entity_id="secret_x", real="sk_live_zzz", ghost="",
                kind="secret", level="restricted", strategy="remove")
    store.save()
    _validator("mapping.schema.json").validate(json.loads(store.path.read_text()))


def test_sample_audit_validates(tmp_path):
    from ghostc.audit import AuditLog

    log = AuditLog(tmp_path / "audit.jsonl")
    log.emit("run.start", "compiler", details={"repo": "x"})
    log.emit("compile.entity_detected", "compiler", level="restricted",
             subject={"entity_id": "client_a", "real_sha256": "a" * 64})
    log.emit("run.end", "compiler", details={"entities": 1})
    v = _validator("audit-event.schema.json")
    for rec in load_jsonl(log.path):
        v.validate(rec)


def test_compiled_mapping_and_audit_validate(compiled):
    _validator("mapping.schema.json").validate(json.loads(compiled.mapping.read_text()))
    v = _validator("audit-event.schema.json")
    for rec in load_jsonl(compiled.audit):
        v.validate(rec)
