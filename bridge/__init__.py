"""Boundary-neutral shared plumbing for the agent workflow.

``bridge`` imports neither ``ghostc`` nor ``client_agent``/``consultancy_agent``.
Both sides may import it.

- :mod:`bridge.env`     — the ``.env`` loader (python-dotenv; one config source, container-ready)
- :mod:`bridge.forge`   — a minimal git "forge" (local bare repos + PR records)
- :mod:`bridge.llm`     — the Claude client wrapper + a deterministic stub
- :mod:`bridge.metrics` — append-only per-run metrics sink (JSONL, one row per agent run)
- :mod:`bridge.trace`   — ``@traceable`` (langsmith when present, else a no-op)
"""
