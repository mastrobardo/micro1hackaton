"""Client-side orchestrator — runs INSIDE the company trust boundary.

Imports ``ghostc`` (the deterministic privacy compiler) and ``bridge`` (git forge
+ LLM client). Drives one task through:

    plan → compile_spec → [leak gate] → handoff (ghost branch + TASK.md)
         → await_ghost_pr → reverse_patch → verify → consistency
         → open_real_pr → emit_metrics

The consultancy side never runs here — the handoff is a git push to a ghost
remote. See :mod:`client_agent.graph` and ``client_agent/graph.md``.
"""
