"""ghostc MCP server: tools registered, thin wrappers work, fail-closed holds."""
from __future__ import annotations

import pytest

pytest.importorskip("mcp")

from ghostc import mcp_server as m  # noqa: E402
from ghostc.mapping import MappingStore  # noqa: E402


def test_server_registers_the_four_tools():
    assert m.server.name == "ghostc"
    names = set(m.server._tool_manager._tools) if hasattr(m.server, "_tool_manager") else None
    if names is None:  # API shape differs across mcp versions — fall back to attributes
        names = {n for n in ("compile_spec", "discover", "verify", "apply_patch")
                 if callable(getattr(m, n, None))}
    assert {"compile_spec", "discover", "verify", "apply_patch"} <= names


def test_compile_spec_tool_sanitizes(tmp_path, privacy_yaml):
    store = MappingStore(tmp_path / "mapping.json")
    store.upsert(entity_id="svc_booking_core", real="booking-core", ghost="service-a",
                 kind="internal_service", level="confidential", strategy="semantic_alias")
    store.save()

    out = m.compile_spec("Add a healthcheck to booking-core.",
                         config_path=str(privacy_yaml),
                         mapping_path=str(tmp_path / "mapping.json"),
                         audit_path=str(tmp_path / "audit.jsonl"))
    assert out["ok"] is True
    assert "booking-core" not in out["ghost_task"]
    assert "service-a" in out["ghost_task"]
    assert out["substitutions"][0]["entity_id"] == "svc_booking_core"


def test_compile_spec_tool_fails_closed(tmp_path, privacy_yaml, monkeypatch):
    monkeypatch.setattr("ghostc.spec.transform_text",
                        lambda text, kind, matchers, base=0: (text, []))
    (tmp_path / "mapping.json").write_text('{"mapping_version":1,"entries":[]}',
                                           encoding="utf-8")
    out = m.compile_spec("Endpoint for Northwind Airlines.",
                         config_path=str(privacy_yaml),
                         mapping_path=str(tmp_path / "mapping.json"),
                         audit_path=str(tmp_path / "audit.jsonl"))
    assert out["ok"] is False and out.get("rejected") is True
    assert "ghost_task" not in out
