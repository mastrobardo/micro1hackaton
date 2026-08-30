"""bridge.env — the .env loader (python-dotenv wrapper, [agents] extra)."""
from __future__ import annotations

import os

import pytest

pytest.importorskip("dotenv", reason="needs the [agents] extra (python-dotenv)")

from bridge.env import load_env, parse_env  # noqa: E402


def test_parse_basic_and_comments():
    text = (
        "# a comment\n"
        "\n"
        "ANTHROPIC_API_KEY=sk-abc123\n"
        "  GHOSTC_AGENT_BACKEND = auto  \n"
        "export LANGSMITH_TRACING=true\n"
        "QUOTED=\"with spaces\"\n"
        "SINGLE='x y'\n"
        "NOT_A_PAIR\n"
    )
    got = parse_env(text)
    assert got == {
        "ANTHROPIC_API_KEY": "sk-abc123",
        "GHOSTC_AGENT_BACKEND": "auto",
        "LANGSMITH_TRACING": "true",
        "QUOTED": "with spaces",
        "SINGLE": "x y",
    }


def test_load_env_applies_missing_keys(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("GHOSTC_TEST_ONE=alpha\nGHOSTC_TEST_TWO=beta\n", encoding="utf-8")
    monkeypatch.setenv("GHOSTC_ENV_FILE", str(env_file))
    monkeypatch.delenv("GHOSTC_TEST_ONE", raising=False)
    monkeypatch.delenv("GHOSTC_TEST_TWO", raising=False)

    applied = load_env(force=True)

    assert applied == {"GHOSTC_TEST_ONE": "alpha", "GHOSTC_TEST_TWO": "beta"}
    assert os.environ["GHOSTC_TEST_ONE"] == "alpha"


def test_load_env_never_overrides_real_environment(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("GHOSTC_TEST_ONE=from-file\n", encoding="utf-8")
    monkeypatch.setenv("GHOSTC_ENV_FILE", str(env_file))
    monkeypatch.setenv("GHOSTC_TEST_ONE", "from-shell")

    applied = load_env(force=True)

    assert "GHOSTC_TEST_ONE" not in applied
    assert os.environ["GHOSTC_TEST_ONE"] == "from-shell"


def test_load_env_missing_file_is_noop(tmp_path, monkeypatch):
    # an explicit GHOSTC_ENV_FILE is used exclusively — no fallback to repo .env
    monkeypatch.setenv("GHOSTC_ENV_FILE", str(tmp_path / "does-not-exist"))
    assert load_env(force=True) == {}


def test_repo_env_example_documents_the_known_keys():
    from pathlib import Path

    example = Path(__file__).resolve().parents[1] / ".env.example"
    body = example.read_text(encoding="utf-8")
    for key in ("ANTHROPIC_API_KEY", "GHOSTC_AGENT_BACKEND", "GHOSTC_AGENT_MODEL",
                "LANGSMITH_API_KEY", "LANGSMITH_PROJECT", "LANGSMITH_TRACING",
                "LANGSMITH_ENDPOINT",
                "CLIENT_ANTHROPIC_API_KEY", "CONSULTANCY_ANTHROPIC_API_KEY",
                "CLIENT_LANGSMITH_PROJECT", "CONSULTANCY_LANGSMITH_PROJECT"):
        assert f"{key}=" in body, key
