"""``@traceable`` for the agent workflow.

Re-exports ``langsmith.traceable`` when ``langsmith`` is installed (the ``[agents]``
extra); otherwise a no-op passthrough, so decorated modules stay importable in a
clean ``[dev]``-only checkout. Supports both ``@traceable`` and
``@traceable(run_type=..., name=...)``.
"""
from __future__ import annotations

from typing import Any, Callable, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])

try:
    from langsmith import traceable as traceable  # noqa: F401  (re-export)
except Exception:  # pragma: no cover - exercised only without the [agents] extra
    def traceable(*d_args: Any, **d_kwargs: Any):  # type: ignore[misc]
        if len(d_args) == 1 and callable(d_args[0]) and not d_kwargs:
            return d_args[0]

        def deco(fn: _F) -> _F:
            return fn

        return deco
