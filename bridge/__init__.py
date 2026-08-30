"""Boundary-neutral shared plumbing for the agent workflow.

``bridge`` imports neither ``ghostc`` nor ``client_agent``/``consultancy_agent``.
Both sides may import it.

- :mod:`bridge.forge` — a minimal git "forge" (local bare repos + PR records)
- :mod:`bridge.llm`   — the Claude client wrapper + a deterministic stub
"""
