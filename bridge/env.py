"""One place to configure the agent workflow's environment.

Thin wrapper over ``python-dotenv``. ``load_env()`` reads a ``.env`` file and puts
anything not already in ``os.environ`` there, so a real shell export, a CI secret,
or ``docker run -e`` always wins over the file.

Search order:

* ``$GHOSTC_ENV_FILE`` if set — used exclusively (a no-op if it does not exist;
  no fallback, so the override is predictable)
* otherwise the first that exists of ``<repo-root>/.env`` then ``./.env``

The same file is what a Phase-E ``docker compose`` passes to each agent service
via ``env_file:``, so local runs and containers read one source.

Recognised keys (see ``.env.example``): ``ANTHROPIC_API_KEY`` /
``{CLIENT,CONSULTANCY}_ANTHROPIC_API_KEY``, ``GHOSTC_AGENT_BACKEND``,
``GHOSTC_AGENT_MODEL``, ``LANGSMITH_API_KEY`` /
``{CLIENT,CONSULTANCY}_LANGSMITH_API_KEY``, ``LANGSMITH_PROJECT`` /
``{CLIENT,CONSULTANCY}_LANGSMITH_PROJECT``, ``LANGSMITH_TRACING``.
"""
from __future__ import annotations

import io
import os
from pathlib import Path

from dotenv import dotenv_values

_REPO_ROOT = Path(__file__).resolve().parents[1]
_LOADED: dict[str, str] | None = None


def _candidate_paths() -> list[Path]:
    override = os.environ.get("GHOSTC_ENV_FILE")
    if override:
        return [Path(override).expanduser()]
    paths = [_REPO_ROOT / ".env", Path.cwd() / ".env"]
    seen: set[Path] = set()
    out: list[Path] = []
    for p in paths:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            out.append(p)
    return out


def parse_env(text: str) -> dict[str, str]:
    """Parse ``KEY=value`` env text via python-dotenv. Drops keys with no value."""
    return {k: v for k, v in dotenv_values(stream=io.StringIO(text)).items() if v is not None}


def load_env(*, force: bool = False) -> dict[str, str]:
    """Load the first ``.env`` found into ``os.environ`` without overriding existing
    values. Idempotent — a no-op after the first call unless *force*. Returns the
    key/value pairs that were applied (empty if no file / all preset).
    """
    global _LOADED
    if _LOADED is not None and not force:
        return _LOADED

    applied: dict[str, str] = {}
    for path in _candidate_paths():
        if not path.is_file():
            continue
        for key, value in dotenv_values(path).items():
            if value is not None and key not in os.environ:
                os.environ[key] = value
                applied[key] = value
        break

    _LOADED = applied
    return applied
