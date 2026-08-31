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
| `consultancy_agent/` | external agent; `sim.py` (Phase-B stand-in), `agent.py` (Phase C stub — **no runtime boundary self-check**; isolation is infra) | `bridge` only — **never** `ghostc`/`client_agent` (enforced by `tests/test_boundary.py`) |

Entrypoints: `ghostc` (compiler), `ghostc-agent run-task | print-graph`, `ghostc-mcp`.
Extras: `[agents]` = langgraph/langsmith/anthropic; `[mcp]` = `mcp>=2.0` (v2: `MCPServer`,
not `FastMCP`). `compile-spec` stays on the `ghostc` CLI (deterministic, no LLM).

## Env config (`bridge/env.py` + per-agent keys in `bridge/llm.py`, added 2026-08-31)

One source: a gitignored `.env` at the repo root (template `.env.example`). `bridge.env.load_env()`
— a thin wrapper over `python-dotenv` (`[agents]` extra) keeping our explicit search path +
no-override + applied-keys return — is called by `client_agent/cli.py::main()` and
`client_agent/graph.py::run_task()` before anything reads `os.environ`. **Never overrides a
var already set** in the real environment, so shell export / CI secret / `docker run -e` win;
`.env` is only the local default. `$GHOSTC_ENV_FILE` overrides the path (used exclusively, no
fallback). `ghostc` core reads none of these. Phase E `docker compose` passes the same `.env`
to each agent service via `env_file:`. Tests: `tests/test_env.py` (5).

**Per-agent credentials** (`bridge/llm.py`, `role` ∈ `client` | `consultancy`).
`resolve_secret(name, role)` reads `{ROLE}_{name}` then bare `{name}`, so one shared key
still works but the two agents can be split for separate billing / trace orgs / blast radius:

| resolved | falls back to |
|---|---|
| `CLIENT_ANTHROPIC_API_KEY` / `CONSULTANCY_ANTHROPIC_API_KEY` | `ANTHROPIC_API_KEY` |
| `CLIENT_LANGSMITH_API_KEY` / `CONSULTANCY_LANGSMITH_API_KEY` | `LANGSMITH_API_KEY` |
| `{ROLE}_LANGSMITH_PROJECT` | `LANGSMITH_PROJECT` → `ghostc-<role>` |
| `{ROLE}_LANGSMITH_ENDPOINT` | `LANGSMITH_ENDPOINT` (EU tenant → `https://eu.api.smith.langchain.com`; US default + EU key = 403) |

`get_llm(backend, role=...)` passes the resolved Anthropic key straight to
`anthropic.Anthropic(api_key=...)`; `configure_langsmith(role=...)` sets `LANGSMITH_API_KEY`
/ `LANGSMITH_PROJECT` / `LANGSMITH_ENDPOINT` in the env for the wrapped client. Client side
wired (`role="client"`); consultancy uses `role="consultancy"` when C2 adds its Claude loop.
**In-process limit:** `configure_langsmith` sets a process-wide `LANGSMITH_PROJECT`, so
before the Phase-E process split the last call wins. `GHOSTC_AGENT_MODEL` (`claude-opus-5`)
and `GHOSTC_AGENT_BACKEND` (auto|claude|stub) stay shared. Tests: `tests/test_llm_roles.py` (11).

**Tracing spans.** `bridge/trace.py` re-exports `langsmith.traceable`, or a no-op passthrough
without the `[agents]` extra (so decorated modules import in a `[dev]`-only checkout).
`@traceable` is on `client.run_task`, each graph node (`node:<name>`, wrapped at
`add_node`), `claude.complete` / `stub.complete` (`run_type="llm"`), and `consultancy:sim`.
Tests: `tests/test_trace.py` (3).

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

## Reduced hook-triggered E2E — shipped session 4 (2026-08-31), reworked to real repos

**No synthesized forge. All git operations happen on the actual demo repos** (user
directive: "as close to real life as possible; if a branch is created I need to check it on
the target repo; a workspace/tmp is of no value"). Layout under `$GHOSTC_DEMO_ROOT`
(default `../ghostc-demo`):

```
ghost.git/            bare "origin" — the git-server stand-in; post-receive hook lives here
ghost/                the company ghost repo (ghostc compile output); remote origin → ../ghost.git
ghost-consultancy/    the consultancy's OWN persistent clone of ghost.git (its working copy)
ghost_task_<id>.consultancy.log   the hook's captured consultancy output (beside ghost-consultancy)
```

```
client-agent start 001-add-companyx-integration --consultancy-backend claude
  → plan → compile_spec → [leak gate]
  → handoff  (in ../ghostc-demo/ghost:  fetch origin · checkout -B ghostc/task/<id> origin/main ·
              write TASK.md at the root · commit as `ghostc-client <client@ghostc.local>` ·
              `git push -f origin` ── fires ../ghostc-demo/ghost.git/hooks/post-receive ──
              · checkout main)
        post-receive → `python -m consultancy_agent._hook <backend> <ghost-consultancy>`
                     → `consultancy-agent start --repo ../ghostc-demo/ghost-consultancy --branch <ref> --backend <b>`
  → consultancy (own clone, ghost-only): fetch · checkout -B <ref> origin/<ref> · implement ·
      commit as `Consultancy Dev <dev@consultancy.example>` (override CONSULTANCY_GIT_NAME/EMAIL) ·
      `git push origin <ref>` (GHOSTC_NO_HOOK=1 → no re-trigger).  NO PR.
  → await_consultancy  (in ghost/: fetch origin · read log origin/<ref> vs handoff_sha ·
      `git branch -f <ref> origin/<ref>` so it is checkoutable · record authors + commit)
  → emit_metrics   (STOP — no ghost PR, reverse_patch, verify, consistency, real PR)
```

You inspect it where you'd expect: `git -C ../ghostc-demo/ghost log --stat ghostc/task/<id>`
— two actors: `ghostc-client` (the `task:` handoff commit) and `Consultancy Dev` (the `impl:`
commit).

- **`client_agent/localgit.py`** (new) — `git(cwd, *args, ident=)` + `ensure_ghost_origin(
  ghost_repo, consultancy_repo, *, hook_backend, python)`: idempotently makes the bare origin
  beside `ghost_repo`, wires `origin`, `push -u origin main`, installs `post-receive`
  (`exec <py> -m consultancy_agent._hook <backend> <consultancy_repo>` — **no** mapping/client
  path), and clones (or `fetch`es) the persistent `ghost-consultancy`. `CLIENT_IDENT` =
  `ghostc-client <client@ghostc.local>`.
- **`consultancy_agent/_hook.py`** — stdlib only now (no `bridge` import). Reads pushed
  `refs/heads/ghostc/task/*` from stdin, runs `consultancy-agent start --repo <consultancy_repo>
  --branch <ref>`, writes combined output to `<consultancy_repo>/../<ref>.consultancy.log`,
  sets `GHOSTC_NO_HOOK=1` for the child. No cloning — the consultancy checkout is persistent.
- **`consultancy_agent/agent.py`** — `_git` pins the consultancy identity
  (`CONSULTANCY_GIT_NAME`/`CONSULTANCY_GIT_EMAIL`, default `Consultancy Dev <dev@consultancy.example>`),
  strips `GIT_*`. `run()` does `fetch` → `checkout -B <branch> origin/<branch>` → implement →
  commit → `push origin <branch>`. No `bridge.forge` import. Still: StubLLM → `_scripted_impl`
  (deterministic `IMPL_NOTES.md`); real LLM → `_agent_loop` (JSON-action loop, `_MAX_STEPS=24`,
  `@traceable("consultancy:agent")`, `role="consultancy"`).
- **`client_agent/graph.py`** — `run_task(..., stop_after="develop", consultancy_backend=,
  consultancy_repo=None, scratch_dir=".ghostc/scratch")`. Reduced path calls
  `localgit.ensure_ghost_origin` then builds the graph with `forge=None`. `handoff` /
  `await_consultancy` use `localgit` against `ghost_tree` (reduced) — the full path still uses
  `LocalBareForge`. `state.py`: `handoff_sha` / `consultancy_pushed` / `consultancy_commit` /
  `ghost_branch_in`; metrics gain `consultancy_authors`.
- **`bridge/forge.py`** — reverted the session-4 additions (`install_consultancy_hook`,
  `fetch`, `log_shas`, `bare_path`, `GIT_ENV`). Still used **only** by the full `run-task`
  pipeline. `__init__` keeps `Path(root).resolve()`.
- **Entrypoints:** `pyproject.toml` `[project.scripts]` += `client-agent` (= `ghostc-agent`,
  same group) + `consultancy-agent`. Re-run `pip install -e .` for the console names; the hook
  uses `python -m consultancy_agent` so it works without the re-install.
- **`sim.py`** gained `open_pr: bool = True` (False → commit on the feature branch) — the
  in-process stand-in the **full** graph still uses; the reduced flow no longer touches it.
- **Spec:** `specs/001-add-companyx-integration.md` (ticket FLIGHT-142). Header
  `task-id: 001-add-second-provider` is **boundary-neutral on purpose** — the id becomes the
  `ghostc/task/<id>` branch name, visible to the consultancy side, so it must not carry a
  real name. `CompanyX`→`partner-a` added to `privacy.webapp.yaml` (`[ticket:…]` note so
  `test_webapp_config_covers_the_apps_entities` skips it — it is not in the app yet).
- **Tests:** `tests/test_agentic_e2e.py` (2 — real-repo reduced flow on stub: branch on the
  bare origin, two git identities, idempotent re-run, worktree left on main),
  `tests/test_boundary.py` (also `consultancy_agent.cli` / `._hook`). `bridge/forge.py`'s
  session-4 additions + their 2 tests removed. 260 pass / 1 skip.
- **Still `assert_boundary_clean`-free** (removed session 3) — isolation is infra, not a
  self-check.
- **Idempotency:** reduced flow re-runs cleanly — `handoff` does `checkout -B <branch>
  origin/main` + `push -f`, so a stale task branch on the bare is just force-updated. No
  workspace to wipe (the full pipeline still wipes `--workspace`).

**Follow-up fixes (after the first real invocations):**
- **`workspace/` deprecated** ([[workspace-deprecated]]). The reduced flow now uses **no**
  workspace at all (real repos under `../ghostc-demo/` + `.ghostc/{scratch,webapp-private}`
  for the sanitized TASK.md + mapping/audit, gitignored, no git). The **full** pipeline still
  uses `.ghostc/agent` for its synthesized forge. `ghostc/cli.py` defaults + scripts + docs
  still say `workspace/` — pending migration.
- `bridge/llm.py::get_llm` — an explicit `backend="stub"/"claude"` (e.g. `--consultancy-backend`)
  now beats `GHOSTC_AGENT_BACKEND`; the env var only fills in for `backend="auto"`, and an
  empty value is ignored. Before, `.env`'s `GHOSTC_AGENT_BACKEND=auto` silently overrode the flag.
- **`_agent_loop` under-implements on real Claude** — an early run edited only `.env.example`
  then stopped. The text-protocol ReAct loop over `bridge.llm.complete()` needs hardening
  (or native Anthropic tool-use). C2/C3 work.
- **Resilience (after a `529 Overloaded` killed a run):** `ClaudeLLM` now sets
  `anthropic.Anthropic(max_retries=5)`; `_agent_loop._complete` adds an outer backoff on
  transient errors (`overloaded`/`rate limit`/`timeout`/`5xx`/`529` in the message) and, if
  it still fails, **returns the partial work** with a `stopped …: LLM error` summary instead
  of raising — so `run()` still commits + pushes and the branch is never left empty. The
  hook (`_hook.py`) writes the consultancy subprocess's combined output to
  `<workdir>/<task_id>.consultancy.log` (a post-receive hook's stderr is swallowed by a
  successful `git push`); `await_consultancy` tails that file into the `rejected` message +
  the `agent.consultancy_developed` audit when no commit landed.

**Not yet done:** a *complete* run with a real Anthropic key (loop hardening above). Next
action = live-verify Claude + LangSmith for `role="client"` **and** `role="consultancy"` (two
projects, two keys), then C3 (`npm test`/`build` metrics). Full checklist: `SESSION_TODO.md`
→ `## DONE session 4`.

## `client-agent open-real-pr` + per-run metrics — shipped session 5 (2026-08-31)

Branch `feat/006_reverse-pr-and-metrics`. `pytest` **268 pass / 1 skip**. Docs/live-demo
pending (see `SESSION_TODO.md`).

**The reverse-compile "webhook" is a SEPARATE client subcommand, not wired into `start`.**
User's steer: the consultancy already puts its code on the ghost task branch opened by the
client; we need *another* command, on the client/ghost agent, to open a decoded ("clear")
branch on the **real** repo — simulating a forge webhook that fires *into* the company
boundary. It **must** be client-side: reversing needs the cleartext mapping + `ghostc`, both
of which `consultancy_agent` is walled off from (`tests/test_boundary.py`).

- **`client_agent/reverse_pr.py`** (new) — `open_real_pr(*, task_id, spec_slug, config_path,
  ghost_tree, real_repo, mapping_path, audit_path, ghost_branch=None, real_branch=None,
  base=None, metrics_file=None, scratch_dir=".ghostc/scratch") -> dict` (the metrics row).
  `@traceable("client.open_real_pr")`, `role="client"`.
  1. `git -C <ghost> fetch origin`; `_handoff_commit` = the commit that ADDED `TASK.md` on
     `origin/ghostc/task/<id>` (`git log --diff-filter=A -- TASK.md`, oldest).
  2. `git diff <handoff>..origin/<branch> -- . :(exclude)TASK.md :(exclude)IMPL_NOTES.md`
     = the consultancy's ghost impl delta (workflow artifacts excluded). Empty → `NotReady`.
  3. `ghostc.patch.reverse_patch(..., do_apply=False)` → real diff. **Fail-closed**: on
     `Rejection` → `agent.real_pr_blocked` audit + `outcome="rejected"` metrics row, re-raise
     (nothing on the real repo). `reverse_patch` also renames sensitive path components
     (`src/serviceAProbe.js` → `src/bookingCoreProbe.js`).
  4. On `<real_repo>`: `checkout -B ghostc/real/<decoded> <base>`, `git apply --check` (`--3way`
     then plain), apply, write `PR_BODY.md` (entities resolved / lossy / "HUMAN REVIEW
     REQUIRED"), commit as `ghostc-client` (`localgit.CLIENT_IDENT`), `checkout <base>`.
     Emits `agent.real_pr_opened` + `approval.requested`.
- **Decoded branch name** = `ghostc/real/<decode_slug(spec_filename_stem, mapping)>`.
  `decode_slug` token-replaces each ghost kebab alias → `kebab(real)` (longest alias first,
  `(?<![a-z0-9])…(?![a-z0-9])`). `add-partner-a-integration` → `add-companyx-integration`;
  a slug with no alias is unchanged. `--real-branch` overrides. **Note:** the spec header
  `task-id:` is the boundary-neutral *ghost* branch id; the real branch is derived from the
  descriptive *filename* instead (`_resolve_spec` now returns `(text, spec_id, stem)`).
- **CLI**: `client-agent open-real-pr <spec>` in `client_agent/cli.py` — webapp defaults
  (`../ghostc-demo/{ghost,real}`, `fixtures/webapp/privacy.webapp.yaml`,
  `.ghostc/webapp-private/mapping.json`); `--task-id/--real-branch/--base/--metrics-file`.
  `NotReady` → "run `client-agent start <spec>` first"; `Rejection` → exit 1, nothing written.

**Per-run metrics sink — `bridge/metrics.py`** (stdlib only → both agents may import it).
`record_run(row, *, path=None)` appends one JSON line `{schema:1, ts, **row}` to
`metrics(path)` = `path` arg → `$GHOSTC_METRICS_FILE` → `metrics/agent-runs.jsonl`.
Gitignored (`metrics/*.jsonl`); `metrics/README.md` + `.gitkeep` tracked — consumed as a
CI/dashboard artifact "like tests or sonar reports" (dashboard is later, maybe a GH Action).

- **Who writes a row** (`role`): `client` — `emit_metrics` node (`command` `start` reduced /
  `run-task` full) **and** `open-real-pr`; `consultancy` — `agent.run()` at the end
  (`task_branch`, `backend`, `steps`, `files_changed`, `wall_clock_s`).
- **Hook forwarding**: `run_task` resolves `metrics_path(metrics_file).resolve()` to an
  absolute path and passes it to `localgit.ensure_ghost_origin(..., metrics_file=)`, which
  bakes `GHOSTC_METRICS_FILE=…; export …` into the `post-receive` script — so the consultancy
  (cwd = bare repo, spawned by the hook) writes into the **same** file as the client.
- **Tests**: `tests/test_metrics.py` (4), `tests/test_reverse_pr.py` (4 — decode_slug,
  happy-path decoded branch on the real repo, `NotReady`, fail-closed on a real value in the
  ghost diff). `tests/conftest.py::_hermetic_agent_env` now `setenv`s `GHOSTC_METRICS_FILE`
  to a per-test tmp file (no repo pollution; tests read it from `os.environ`).
  `tests/test_agentic_e2e.py` asserts a `client` + a `consultancy` row in the shared sink.
- Threaded `metrics_file` param: `run_task` / `build_client_graph` / `_install_post_receive`
  / `ensure_ghost_origin` (all default `None`/`""` → no behaviour change when unset).

## C2/C3 consultancy-loop hardening — session 6 (2026-08-31)

The Claude path of `consultancy_agent/agent.py` (`--backend stub` untouched, so `pytest` +
`test_agentic_e2e.py` stay deterministic and offline):

- **`done:true` is now gated on green CI, not the model's word.** `_agent_loop` tracks
  `tests_green` / `build_green` — reset on every `write_file`, set on an `exit=0` from
  `run_tests` / `run_build`. A `done` with either flag false is refused with a nudge naming
  what's missing; after `_MAX_DONE_NUDGES` (3) refusals or the step budget the partial is
  accepted so the run still commits.
- `_MAX_STEPS` 24 → **40**; `_complete` `max_tokens` 4096 → 8000.
- `_SYSTEM` rewritten as an ordered method (list files → enumerate the ACs → read the
  sibling client/service/config/test the ticket says to mirror → write → run tests+build →
  fix → only then `done`), "one json object, no markdown fences".
- `_acceptance_criteria(task)` slices the `## Acceptance criteria` block out of TASK.md and
  pins it in the prompt header (survives transcript trimming).
- `_parse_action(text)` strips a ```json fence and tolerates prose around the object.
- Prompt each turn = header (TASK + ACs) + last `_TRANSCRIPT_TAIL` (30) exchanges + a
  compact `[status] step n/40 · tests_green=… · build_green=… · files_written=…` line, so a
  long run doesn't grow the prompt without bound.

**C3 — the "it works" number.** `agent.run()` runs one authoritative `npm test` +
`npm run build` on the developed checkout (skipped on the stub path) and records
`ghost_tests` (`{ok, pass, fail, tests}` parsed from the `node --test` TAP tail via
`_test_counts`) + `ghost_build` (`{ok}`) into **both** the `metrics/agent-runs.jsonl`
consultancy row and `RunResult`. `client_agent/graph.py::await_consultancy` reads the newest
`role=consultancy` row for the task branch (via `bridge.metrics.metrics_path()`) and merges
those two keys into `state["metrics"]` → they flow through `emit_metrics`. No-op on stub
(fields are `None`, filtered out).

Chose "bigger budget + nudge + green-gate" over adding native Anthropic tool-use to
`bridge/llm.py` — smaller blast radius before the deadline. Native `messages.create(tools=)`
+ a `tool_use` loop (keeping `StubLLM` scripted) is the noted cleaner follow-up.

## Known / deferred

- **Native Anthropic tool-use** for the consultancy loop (replace the hand-rolled JSON-text
  protocol): `complete_with_tools(system, messages, tools)` on `ClaudeLLM`, loop on
  `tool_use` blocks, `StubLLM` returns the scripted actions. Post-hackathon.
- `ghostc/patch.py` audit events use `component: "reverse-compiler"` (hyphen) — **not** the
  schema enum's `reverse_compiler`. Pre-existing; fix in Phase F.
- Phase B `verify` node is a lightweight `git apply --check` of the real diff; the full
  build/lint gate over an applied tree is Phase F.
- `reverse_patch` mints its own `operation_id` (no param to pass the run's); events correlate
  by `task_id` in `details` for now.

Related: [[compiler-and-alias-model]], [[reverse-patch-compiler]], [[detection-scoring]],
[[testing-approach]], [[project-goal-and-status]].
