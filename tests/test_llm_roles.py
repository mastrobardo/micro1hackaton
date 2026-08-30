"""Per-agent credential resolution in bridge.llm."""
from __future__ import annotations

import pytest

from bridge.llm import (
    StubLLM,
    configure_langsmith,
    get_llm,
    resolve_secret,
)

_VARS = [
    "ANTHROPIC_API_KEY", "CLIENT_ANTHROPIC_API_KEY", "CONSULTANCY_ANTHROPIC_API_KEY",
    "LANGSMITH_API_KEY", "CLIENT_LANGSMITH_API_KEY", "CONSULTANCY_LANGSMITH_API_KEY",
    "LANGSMITH_PROJECT", "CLIENT_LANGSMITH_PROJECT", "CONSULTANCY_LANGSMITH_PROJECT",
    "LANGSMITH_ENDPOINT", "CLIENT_LANGSMITH_ENDPOINT", "CONSULTANCY_LANGSMITH_ENDPOINT",
    "LANGSMITH_TRACING", "GHOSTC_AGENT_BACKEND", "GHOSTC_ENV_FILE",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for v in _VARS:
        monkeypatch.delenv(v, raising=False)
    # keep bridge.env from loading the repo .env during these tests
    monkeypatch.setenv("GHOSTC_ENV_FILE", "/nonexistent/.env")


def test_resolve_secret_prefers_role_prefix_then_bare(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "shared")
    assert resolve_secret("ANTHROPIC_API_KEY", "client") == "shared"
    assert resolve_secret("ANTHROPIC_API_KEY", "consultancy") == "shared"

    monkeypatch.setenv("CONSULTANCY_ANTHROPIC_API_KEY", "consultancy-only")
    assert resolve_secret("ANTHROPIC_API_KEY", "client") == "shared"
    assert resolve_secret("ANTHROPIC_API_KEY", "consultancy") == "consultancy-only"


def test_resolve_secret_missing_is_none():
    assert resolve_secret("ANTHROPIC_API_KEY", "client") is None


def test_resolve_secret_rejects_unknown_role():
    with pytest.raises(ValueError):
        resolve_secret("ANTHROPIC_API_KEY", "vendor")


def test_get_llm_role_without_key_is_stub(monkeypatch):
    # consultancy has no key, client does -> only consultancy falls back to stub
    monkeypatch.setenv("CLIENT_ANTHROPIC_API_KEY", "x")
    assert isinstance(get_llm("auto", role="consultancy"), StubLLM)


def test_get_llm_stub_backend_ignores_role():
    assert isinstance(get_llm("stub", role="client"), StubLLM)
    assert isinstance(get_llm("stub", role="consultancy"), StubLLM)


def test_configure_langsmith_off_without_key():
    assert configure_langsmith(role="client") is False


def test_configure_langsmith_role_project_naming(monkeypatch):
    monkeypatch.setenv("CONSULTANCY_LANGSMITH_API_KEY", "ls-consultancy")
    assert configure_langsmith(role="consultancy") is True
    import os
    assert os.environ["LANGSMITH_API_KEY"] == "ls-consultancy"
    assert os.environ["LANGSMITH_PROJECT"] == "ghostc-consultancy"
    assert os.environ["LANGSMITH_TRACING"] == "true"


def test_configure_langsmith_explicit_project_wins(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "ls")
    monkeypatch.setenv("CLIENT_LANGSMITH_PROJECT", "my-client-proj")
    assert configure_langsmith(role="client") is True
    import os
    assert os.environ["LANGSMITH_PROJECT"] == "my-client-proj"


def test_configure_langsmith_sets_endpoint_when_present(monkeypatch):
    import os
    monkeypatch.setenv("LANGSMITH_API_KEY", "ls")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "https://eu.api.smith.langchain.com")
    assert configure_langsmith(role="client") is True
    assert os.environ["LANGSMITH_ENDPOINT"] == "https://eu.api.smith.langchain.com"

    # role-prefixed wins for the consultancy
    monkeypatch.setenv("CONSULTANCY_LANGSMITH_ENDPOINT", "https://us.example")
    assert configure_langsmith(role="consultancy") is True
    assert os.environ["LANGSMITH_ENDPOINT"] == "https://us.example"


def test_configure_langsmith_no_endpoint_leaves_it_unset(monkeypatch):
    import os
    monkeypatch.setenv("LANGSMITH_API_KEY", "ls")
    assert configure_langsmith(role="client") is True
    assert "LANGSMITH_ENDPOINT" not in os.environ
