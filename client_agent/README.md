# `client_agent/` — company-side orchestrator

Runs **inside** the trust boundary. Imports `ghostc` (deterministic privacy
compiler) and `bridge` (git forge + LLM client). Never runs consultancy code —
the handoff is a git push to a ghost remote.

Entrypoint: `ghostc-agent run-task` (`client_agent/cli.py`). Graph: `graph.py`
(diagram: `graph.md`, regenerate with `ghostc-agent print-graph`).

## Node contracts

| node | in | out | rule |
|---|---|---|---|
| `compile_spec` | real task, `privacy.yaml`, mapping store | `GhostSpec` + sanitized `TASK.md` | deterministic substitution (`ghostc.spec`); residual real value → fail-closed `Rejection`, `spec.rejected` audited, nothing written |
| `handoff` | ghost tree, `TASK.md` | `ghostc/task/<id>` branch on the ghost remote | commits only the sanitized `TASK.md`; pushes |
| `await_ghost_pr` | ghost remote | ghost PR record | Phase B: calls `consultancy_agent.sim`. Phase D: `interrupt()` resumed by a git hook |
| `reverse_patch` | ghost PR diff, mapping store | real diff | `ghostc.patch.reverse_patch`; unmapped alias / real value in ghost diff / version mismatch → fail-closed `Rejection` |
| `verify` | real diff, real repo | pass / block | `git apply --check` (Phase F: full build gate over an applied tree) |
| `consistency` | real task, real diff | `consistent` / `flagged` + flags | LLM (`bridge.llm`) or stub; advisory, feeds the human gate |
| `open_real_pr` | real diff | real-repo PR (branch + PR record) | applies the diff; PR body flags **HUMAN REVIEW REQUIRED**; `approval.requested` audited |
| `emit_metrics` | all of the above | metrics row + `agent.metrics` / `agent.task_completed` | also the sink for both fail-closed short-circuits |

`compile_spec` and `reverse_patch` are the fail-closed gates: a `Rejection`
routes straight to `emit_metrics` and **no real PR is opened**.
