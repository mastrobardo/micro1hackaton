# Agentic harness (`ghostc compile-spec` + `ghostc-agent run-task`)

The LangGraph agent workflow on top of the deterministic slice. Branch:
`feat/004_agentic_harness`. Confirmed 6-phase plan (A→F); A + B shipped 2026-08-31.

## Design (user's, from the Phase-B kickoff)

Two agents, **two processes**, one on client infra, one on consultancy infra. Handoff is
**git-based**, not a function call:

1. Client planning agent rewrites a real task → a **sanitized `TASK.md`**, commits it on a
   `ghostc/task/<id>` branch of a **ghost git remote**, pushes.
2. A hook (Phase D) starts the consultancy dev phase. The consultancy agent has auth to the
   **ghost remote only** — branches `ghostc/impl/<id>` off the task branch, implements, opens
   a **ghost PR**.
3. The ghost PR's diff is reverse-compiled (`ghostc/patch.reverse_patch`) to a real diff and
   opened as a **real-repo PR** flagged for human review.

Topology: docker-compose, 2 services, LangGraph in the client image (Phase E). Agents call
**Claude via the `anthropic` SDK directly** (not `langchain-anthropic`); LangGraph only
orchestrates. LangSmith tracing when `LANGSMITH_API_KEY` is set.

## Package layout (reorg 2026-08-31 — the agent code left `ghostc/`)

| package | role | may import |
|---|---|---|
| `ghostc/` | deterministic privacy compiler + `ghostc` CLI + `ghostc/spec.py` (compile_spec, was `agents/spec.py`) + `ghostc/mcp_server.py` | stdlib + tree-sitter etc. |
| `bridge/` | boundary-neutral plumbing: `forge.py` (git `LocalBareForge`), `llm.py` (Claude/stub) | stdlib, `anthropic`, `langsmith` — **not** ghostc/client_agent/consultancy_agent |
| `client_agent/` | company-side LangGraph orchestrator; `graph.py` (was `agents/client_graph.py`), `state.py`, `cli.py` (`ghostc-agent`), `graph.md` (mermaid) | `ghostc`, `bridge`, `consultancy_agent` |
| `consultancy_agent/` | external agent; `sim.py` (Phase-B stand-in), `agent.py` (Phase C stub + `assert_boundary_clean`) | `bridge` only — **never** `ghostc`/`client_agent` (enforced by `tests/test_boundary.py`) |

Entrypoints: `ghostc` (compiler), `ghostc-agent run-task | print-graph`, `ghostc-mcp`.
Extras: `[agents]` = langgraph/langsmith/anthropic; `[mcp]` = `mcp>=2.0` (v2: `MCPServer`,
not `FastMCP`). `compile-spec` stays on the `ghostc` CLI (deterministic, no LLM).

## MCP server (`ghostc/mcp_server.py`, `ghostc-mcp`) — hybrid, chosen 2026-08-31

The graph's fixed pipeline nodes still call `ghostc.*` in-process. The MCP server is the
LLM-driven surface + external reuse: tools `compile_spec` / `discover` / `verify` /
`apply_patch`, thin wrappers, every fail-closed path returns `{"ok": false, "error": ...}`
(never a partial ghost). `mcp` 2.x API: `from mcp.server.mcpserver import MCPServer`,
`@server.tool()`, `server.run("stdio")`.

## Phase A — `ghostc compile-spec` (shipped)

`ghostc/spec.py::compile_spec(real_task, ...) -> GhostSpec{ghost_task, substitutions}`.
Deterministic entity substitution via `matching.transform_text` (**same engine as
`compile`**), sourced from `privacy.yaml` entities **+ every mapping-store entry** — so a task
naming *Meridian* → a task naming `vendor-e` once `compile --config privacy.autoalias.yaml`
has frozen it. Output leak-scanned with `anchored_scan`; residual real value → fail-closed
`Rejection` (nothing written, `spec.rejected` audit). LLM may rephrase later, never redacts.
`client_agent/state.py` holds `TaskState` (langgraph-free TypedDict); `render_task_md()`
lives in `ghostc/spec.py` next to `compile_spec`.

## Phase B — `ghostc run-task` (shipped)

`client_agent/graph.py`: LangGraph `StateGraph` —
`plan → compile_spec → [leak gate] → handoff → await_ghost_pr → reverse_patch → verify →
consistency → open_real_pr → emit_metrics`. `compile_spec` + `reverse_patch` are the
fail-closed gates; a `Rejection` short-circuits to `emit_metrics` and **no real PR opens**.

- `bridge/forge.py`: `Forge` protocol + `LocalBareForge` — real git subprocess, one
  bare repo per side under a `remotes/` root + working clones; a "PR" = a JSON record +
  a pushed `refs/ghostc/pr/<id>`. `ensure_repo/seed_from/create_branch/commit_file/push/
  apply_diff/checkout/open_pr/get_pr/pr_diff/list_prs`. A GitHub `gh` backend can replace it
  without touching the graph.
- `bridge/llm.py`: `get_llm(backend)` → `ClaudeLLM` (anthropic SDK, model
  `claude-opus-5`, env `GHOSTC_AGENT_MODEL`/`GHOSTC_AGENT_BACKEND`) or deterministic
  `StubLLM`. `auto` = Claude iff `ANTHROPIC_API_KEY` set + SDK importable, else stub.
- `consultancy_agent/sim.py`: deterministic Phase-B stand-in for the consultancy
  agent (branch off the task branch, tiny edit, open ghost PR). **Phase C** replaces it with
  a real Claude tool-loop + a boundary guard (refuse if mapping/real-repo reachable).
- Audit: `agent.task_started / spec_handoff / ghost_pr_opened / real_pr_opened /
  task_completed / metrics` + `consistency.verdict` + `approval.requested`. Metrics row (wall
  clock, entities resolved, lossy entities, consistency verdict, LLM tokens) is derived from
  the log.
- Deps: `[agents]` extra = `langgraph`, `langsmith`, `anthropic`. Graph tests
  `importorskip("langgraph")` + `--backend stub`; core `ghostc` + `pytest` from a clean
  checkout unaffected.

Verified end-to-end on the built fixture: ghost PR carries `client-a`/`service-a`/`vendor-a`;
real PR carries `Northwind Airlines`/`booking-core`/`SkyRoute Data Ltd` (restored), with
`client_northwind` + `vendor_skyroute` flagged `lossy` (multi-word display names).

## Known / deferred

- `ghostc/patch.py` audit events use `component: "reverse-compiler"` (hyphen) — **not** the
  schema enum's `reverse_compiler`. Pre-existing; fix in Phase F.
- Phase B `verify` node is a lightweight `git apply --check` of the real diff; the full
  build/lint gate over an applied tree is Phase F.
- `reverse_patch` mints its own `operation_id` (no param to pass the run's); events correlate
  by `task_id` in `details` for now.

Related: [[compiler-and-alias-model]], [[reverse-patch-compiler]], [[detection-scoring]],
[[testing-approach]], [[project-goal-and-status]].
