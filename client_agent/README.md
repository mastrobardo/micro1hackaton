# `client_agent/` — company-side orchestrator

Runs **inside** the trust boundary. Imports `ghostc` (deterministic privacy
compiler) and `bridge` (git forge + LLM client). Never runs consultancy code —
the handoff is a git push to a ghost remote.

Entrypoints (`client_agent/cli.py`, same Click group under two console names):

- **`client-agent start <spec>`** — reduced, hook-triggered flow, **on the real repos**
  (no synthesized forge). Resolves `<spec>` (bare name → `specs/<name>.md`, a path, or `-`
  for stdin), derives the task id from a `task-id:` marker (else the filename stem — keep it
  boundary-neutral, it becomes the branch name). First run creates a bare origin
  `../ghostc-demo/ghost.git` beside the ghost repo + a `post-receive` hook + the
  consultancy's own clone `../ghostc-demo/ghost-consultancy`. Then: `plan → compile_spec →
  handoff` (in `../ghostc-demo/ghost`: branch `ghostc/task/<id>`, commit the sanitized
  `TASK.md` as `ghostc-client`, `git push -f origin` → fires the hook) → the hook runs
  `consultancy-agent start` against the consultancy clone, which commits as `Consultancy Dev`
  and pushes → `await_consultancy` fetches the branch back → `emit_metrics`. **No PR.**
  Inspect: `git -C ../ghostc-demo/ghost log --stat ghostc/task/<id>` (two actors). `--full`
  runs the whole pipeline below instead (still `LocalBareForge`).
- **`client-agent open-real-pr <spec>`** — the **separate** reverse-compile "webhook"
  (`client_agent/reverse_pr.py`), run *after* `start`. Simulates a forge webhook firing into
  the company boundary: `git diff <handoff>..origin/ghostc/task/<id>` (the consultancy's impl,
  minus `TASK.md`/`IMPL_NOTES.md`) → `ghostc.patch.reverse_patch` → a **decoded** branch
  `ghostc/real/<name>` on `../ghostc-demo/real` (+ `PR_BODY.md`, commit as `ghostc-client`).
  The real branch name comes from the spec *filename* reverse-compiled through the mapping
  (`decode_slug`: `add-partner-a-integration` → `add-companyx-integration`); `--real-branch`
  overrides. Client-side only — reversing needs the cleartext mapping + `ghostc`, which the
  consultancy cannot import. Fail-closed: a `reverse_patch` `Rejection` writes nothing to the
  real repo. Inspect: `git -C ../ghostc-demo/real log --stat ghostc/real/<name>`.
- **`ghostc-agent run-task --task <file>`** — the full pipeline (ghost PR, reverse-patch,
  verify, consistency, real-repo PR).
- `ghostc-agent print-graph` — regenerate `graph.md` (both shapes).

## Per-run metrics

Every agent run appends one JSON line to `metrics/agent-runs.jsonl` (gitignored;
`metrics/README.md` has the schema) via `bridge.metrics.record_run` — `start` /
`open-real-pr` (`role: client`) and the consultancy agent (`role: consultancy`, its row
routed to the same file because the `post-receive` hook exports `GHOSTC_METRICS_FILE`).
Override with `--metrics-file` or `$GHOSTC_METRICS_FILE`. Intended to be charted later
(dashboard / GitHub Action step, the way CI consumes a test or coverage report).

## Node contracts

| node | in | out | rule |
|---|---|---|---|
| `compile_spec` | real task, `privacy.yaml`, mapping store | `GhostSpec` + sanitized `TASK.md` | deterministic substitution (`ghostc.spec`); residual real value → fail-closed `Rejection`, `spec.rejected` audited, nothing written |
| `handoff` | ghost tree, `TASK.md` | `ghostc/task/<id>` branch | *reduced:* in `../ghostc-demo/ghost` — `checkout -B` the branch off `origin/main`, commit the sanitized `TASK.md` as `ghostc-client`, `git push -f origin` (fires the bare's `post-receive`), `checkout main`. *full:* via `LocalBareForge`. |
| `await_consultancy` *(reduced)* | bare origin | recorded consultancy commit + authors | `git fetch origin`; confirm a commit landed on top of the `TASK.md` commit (the hook ran the consultancy synchronously); `git branch -f` so it is checkoutable; `agent.consultancy_developed`. No PR |
| `await_ghost_pr` *(full)* | ghost remote | ghost PR record | calls `consultancy_agent.sim` in-process (opens a ghost PR). Phase D: `interrupt()` resumed by a git hook |
| `reverse_patch` | ghost PR diff, mapping store | real diff | `ghostc.patch.reverse_patch`; unmapped alias / real value in ghost diff / version mismatch → fail-closed `Rejection` |
| `verify` | real diff, real repo | pass / block | `git apply --check` (Phase F: full build gate over an applied tree) |
| `consistency` | real task, real diff | `consistent` / `flagged` + flags | LLM (`bridge.llm`) or stub; advisory, feeds the human gate |
| `open_real_pr` | real diff | real-repo PR (branch + PR record) | applies the diff; PR body flags **HUMAN REVIEW REQUIRED**; `approval.requested` audited |
| `emit_metrics` | all of the above | metrics row + `agent.metrics` / `agent.task_completed` | also the sink for both fail-closed short-circuits |

`compile_spec` and `reverse_patch` are the fail-closed gates: a `Rejection`
routes straight to `emit_metrics` and **no real PR is opened**.
