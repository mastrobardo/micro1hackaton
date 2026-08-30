# Session TODO — handoff (updated 2026-08-31, end of session 2)

Start-here checklist for the next session. Long-term plan: `TODO.md`. Running status +
decision log: `PROGRESS.md` (read it first). Memory index: `memory/MEMORY.md`.
Project conventions + "memory stays in-repo": `CLAUDE.md`.

> **Next session = Phase C1/C2.** C0 (runnable fixture) is **done** — see
> `## C0 — demoable fixture` below and `memory/demoable-fixture.md`. Fixture decision
> was settled: hand-authored zero-dep Node app, real+ghost live outside the repo at
> `../ghostc-demo/{real,ghost}`. Start at C1 (wire the CompanyX seed task through
> `compile-spec`) then C2 (real consultancy coding agent).

## State — agentic harness Phases A + B shipped (branch `feat/004_agentic_harness`)

Confirmed 6-phase plan for the LangGraph agent workflow (client rewrites a real task into a
sanitized ghost `TASK.md` → git handoff → consultancy opens a ghost PR → reverse-patch → real
PR for human review). Two agents, two processes; docker-compose (2 services, LangGraph in the
client image) is Phase E.

- **Phase A — `ghostc compile-spec`** (`ghostc/spec.py`): real task → sanitized ghost
  `TASK.md`. Deterministic substitution (reuses `matching.transform_text` + the mapping
  store), leak-scanned, fail-closed (`spec.rejected`). Tests: `test_spec.py` (7).
- **Phase B — `ghostc-agent run-task`** (`client_agent/graph.py` + `bridge/{forge,llm}.py` +
  `consultancy_agent/sim.py`): LangGraph `StateGraph`, `LocalBareForge` (bare-repo remotes +
  `refs/ghostc/pr/<id>`), Claude-or-stub consistency gate, `agent.*` audit + a metrics row.
  End-to-end on the fixture opens a real-repo PR with `Northwind Airlines`/`booking-core`
  restored from the sanitized ghost PR. Diagram: `client_agent/graph.md`.
  Tests: `test_client_graph.py` (4), `test_forge.py` (6).
- **Reorg (2026-08-31):** agent code split into `bridge/` (neutral plumbing) +
  `client_agent/` (imports `ghostc`) + `consultancy_agent/` (**may not** import
  `ghostc`/`client_agent` — `test_boundary.py`). Entrypoints `ghostc-agent` (run-task,
  print-graph) + `ghostc-mcp` (MCP tools: compile_spec/discover/verify/apply_patch).
  Extras `[agents]`, `[mcp]` (`mcp>=2.0`). Working memory is in-repo (`./memory/`,
  `./CLAUDE.md`) — not `~/.agent/memory.md`.
- `pytest` → **229 passed, 1 skipped**.

## NEXT SESSION — Phase C: real consultancy coding agent + a demoable, runnable fixture

### Why the scope grew (user direction, 2026-08-31)

> "A key aspect of the project is that the real AND the ghost version will **work**, so we
> need to test it. The fixture we had is fine for static analysis; we want something more
> demoable. E.g. scaffold a web fullstack project with Yeoman. In real life the first commit
> could be 'add CompanyX integration', with AC points like env vars, wrapper, apiClient, etc.
> Simulate the flow from step 1: a repo and a ghost one. Manage agent git permissions later;
> for now keep it local."

So the win we demonstrate is no longer only **leak count = 0** — it is **the ghost repo
builds + tests pass after the external agent's change, and the real repo builds + tests pass
after reverse-patch.** That needs a fixture that actually runs.

### C0 — demoable fixture — ✅ DONE (2026-08-31)

Settled: **hand-authored zero-dependency Node app** (not Yeoman/Vite). Real + ghost
checkouts live **outside** the tool repo.

- `fixtures/webapp/app/` — the version-controlled template. Built-in `http` + `node:test`,
  **no runtime deps** → `npm ci` installs nothing, fully offline. ~12 files: `src/server.js`,
  `src/config.js`, `src/integrations/{skyRouteClient,internalServices}.js`, `public/*`,
  `test/api.test.js`, `scripts/build.js`.
- `fixtures/webapp/apply.sh` → `$GHOSTC_DEMO_ROOT/real` (default `../ghostc-demo/real`,
  sibling of the repo). `ghostc compile --config fixtures/webapp/privacy.webapp.yaml`
  → `../ghostc-demo/ghost` + `ghost-spec.md`. Boundary-internal artifacts stay in-repo at
  `workspace/webapp-private/`.
- `scripts/demo-webapp.sh` — stage → compile → verify → `npm test` both → serve real :3000
  + ghost :3001. `REAL_PORT`/`GHOST_PORT`/`DEMO_NO_SERVE` env knobs.
- `fixtures/webapp/privacy.webapp.yaml` — 6-entity subset of the root config, same aliases
  (`Northwind Airlines`→`client-a`, `SkyRoute Data Ltd`→`vendor-a`, `booking-core`→`service-a`,
  `api.northwind-internal.net`→`host-a.example`, `Priya Nair`→`person-a`, key removed).
- `tests/test_webapp_fixture.py` — node-gated (+6, suite now 235/1). Real + ghost both
  `npm test` + `node scripts/build.js` green; ghost `anchored_scan` leak-free.
- **Kept** `node-express-boilerplate` → `workspace/real/` for the static `ghostc eval`.

### C1 — wire the seed task through `compile-spec` (start here)

`fixtures/webapp/tasks/add-companyx-integration.md` **is written** (ticket FLIGHT-142, names
the real `CompanyX`; AC: `COMPANYX_*` env vars + `.env.example`, `companyXClient` apiClient,
`companyXStatusService` wrapper, `config.providers` entry, `test/companyx.test.js`).
**`CompanyX` is not in `privacy.webapp.yaml` yet** — add it (kind `vendor` → `partner-a` /
`PartnerA`) then confirm `ghostc compile-spec` rewrites the ticket to name `PartnerA` and
leak-scans clean.

### C2 — consultancy coding agent  (`consultancy_agent/agent.py`)

- **Hand-rolled** Claude tool-loop via `bridge.llm` (decided 2026-08-31 — *not* `deepagents`) —
  tools `list_files` / `read_file` / `write_file` / `run_tests` / `run_build`, scoped to the
  ghost checkout only. Use `get_llm(backend, role="consultancy")` +
  `configure_langsmith(role="consultancy")` (already supported) so its key/billing/traces are
  separate from the client's. Decorate the loop entry with `@traceable` (`bridge.trace`),
  matching `consultancy:sim`.
- Call `assert_boundary_clean(workdir)` (already stubbed in `agent.py`) **before the loop** —
  refuse if a mapping-shaped file / `privacy.yaml` / real-repo marker is reachable.
- Loop until AC met (tests+build green) or budget exhausted; commit on `ghostc/impl/<id>`;
  open the ghost PR via `bridge.forge`.
- **Deterministic scripted fallback** keyed by task id (`--backend stub` / no
  `ANTHROPIC_API_KEY`) that writes the known-good implementation, so the graph tests + a
  reproducible demo run offline. `consultancy_agent/sim.py` is the current stand-in — extend
  or replace it.
- Wire it into `client_agent/graph.py::await_ghost_pr` (swap the `consultancy_fn` default;
  keep it injectable for tests).

### C3 — real "it works" verification

- Upgrade the graph's `verify` node (or add `build_check` / `test_check` nodes): after
  reverse-patch, `npm ci && npm test && npm run build` in a **real** checkout of the applied
  diff; also record the ghost-side build/test result the consultancy agent last saw.
- `agent.metrics` gains `ghost_build`, `ghost_tests`, `real_build`, `real_tests` (pass/fail
  + counts). This is the row the CHANGELOG needs alongside leak count.
- A `scripts/demo-companyx.sh` (or extend `scripts/e2e.sh`) that runs the whole thing:
  bootstrap real → `ghostc compile` → `ghostc-agent run-task` on the CompanyX task →
  show the real PR + both build/test results.

### Constraints / keep in mind

- **Git stays local** — `bridge.forge.LocalBareForge` (bare repos + `refs/ghostc/pr/<id>`).
  Permissioned/remote git (GitHub `gh`, scoped tokens per agent) is a later phase.
- The consultancy agent must not gain a `ghostc`/`client_agent` import — `tests/test_boundary.py`
  will fail the build if it does.
- MCP Inspector for poking `ghostc-mcp`: `npx @modelcontextprotocol/inspector ghostc-mcp`
  (README has it). No change needed there.

### Then (unchanged): D → E → F

D — git `post-receive` hooks driving the handoff as a real cross-process event (interrupt/
resume the client graph). E — docker-compose (2 services, LangGraph in the client image) +
entrypoints + `scripts/agent-e2e.sh`. **Env is ready for this**: `bridge/env.py` loads a
root `.env`; each compose service just needs `env_file: .env` (+ `GHOSTC_ENV_FILE` if the
container path differs). Give the **consultancy** service only `CONSULTANCY_*` +
`GHOSTC_AGENT_*` (not `CLIENT_*` / bare `ANTHROPIC_API_KEY` / bare `LANGSMITH_API_KEY`) so
the credential boundary is enforced at the container, not just in code. F — `ghostc run-eval-suite` (the 10+1 tasks +
task-pass/approval/wall-clock/token rows), full ARCHITECTURE/CHANGELOG/cli.md writeup, and
**fix `ghostc/patch.py`'s audit `component: "reverse-compiler"` → `reverse_compiler`** to
match the schema enum.

### Known small stuff to carry

- `ghostc/patch.py` emits `component: "reverse-compiler"` (hyphen) ≠ schema `reverse_compiler`.
- Prose casing: `client-a` vs `Client A` vs `ClientA` varies by context; reverse-patch is
  **lossy for multi-word display names** (`Northwind Airlines`) — flagged `lossy`, feeds the
  human gate. Fine, documented.
- `reverse_patch` mints its own `operation_id` (no param to thread the run's through); events
  correlate via `task_id` in `details`.
- `ghostc-mcp` tool results currently return as text content (`structured_content` is null) —
  add return-type hints on the tool fns if structured output matters for the Inspector UX.

### How to run what exists today

```bash
pip install -e ".[dev,agents,mcp]"
pytest -q                                   # 235 passed, 1 skipped
./scripts/demo-webapp.sh                     # C0: real :3000 + ghost :3001, both npm test green
ghostc-agent run-task --task <file> --backend stub \
  --real-repo workspace/real --ghost-tree workspace/ghost   # needs `ghostc compile` first
ghostc-agent print-graph                     # regen client_agent/graph.md
npx @modelcontextprotocol/inspector ghostc-mcp
```

---

## Earlier state — the full deterministic slice is shipped

- `pytest` → **205 passed, 1 skipped** (fixture built) / green from a clean checkout.
- **The anonymizer is `ghostc compile`** — deterministic tree-sitter, node-scoped edits
  (identifier / string / comment only), one canonical alias per entity re-cased per occurrence
  by a segment engine, compound-token splice, sensitive path renames, frozen `real ↔ ghost`
  mapping store. **Not `sed`.** Now also **threshold-driven**: it runs the `discover` scan and,
  with `detection.auto_alias: true`, neutralises unconfigured `auto` candidates too.
- `ghostc baseline` is the **`sed` comparator only** — dumb keyword redaction, not the product.
- **All seven commands implemented** — `validate-config`, `discover`, `compile`, `verify`,
  `baseline`, `apply-patch`, `eval`. No stubs.
- **Measured (`ghostc eval`, fixture):** baseline **28** residual vs `compile` **0**.
  **`ghostc discover`:** 13/13 configured entities re-found from code alone; unconfigured
  *Meridian* (0.99) + *Contoso* (0.83) proposed; 0 OSS-library false positives. Reports:
  `workspace/eval-report.{md,csv}`, `workspace/private/candidates.jsonl`. Evidence: `CHANGELOG.md`.
- Pipeline round-trips: `compile` → `verify` → (agent) → `apply-patch` → real branch.
- Boundary layout is live: `workspace/ghost/` + sibling `workspace/ghost-spec.md` cross;
  `workspace/private/{mapping.json,audit.jsonl,candidates.jsonl}` never cross.
- One leak-scan implementation: `ghostc/scanning.anchored_scan` (reuse it everywhere).
- Detection layer: `ghostc/detect/` (candidate · settings · tokenize · shapes · decode · graph
  · semantic · signals · scan) + `ghostc/discover.py`. Config: the optional `detection:` block.
- Working tree is **uncommitted** (user commits each iteration as a CHANGELOG entry). New
  untracked: `ghostc/detect/`, `ghostc/discover.py`, `tests/test_scoring.py`,
  `tests/test_discover.py`, `tests/expected/discover-groundtruth.json`,
  `fixtures/inject/src/integrations/adversary.js`.

---

## Done this session — Iteration 6: detection overhaul (`ghostc discover`)

Candidate scoring model (noisy-OR signals) → reference-graph taint → bounded fuzzy + shapes →
decode pass → anchor-driven proposals. `compile` is threshold-driven (`detection.auto_alias`
on/off). See `PROGRESS.md` → "discover — what it does" + the 2026-08-30 decision-log rows +
"Known limits (discover, v1)". Details also in `memory/detection-scoring.md`.

Deferred from the plan (not needed for the fixture, carries golden-drift risk): making
`compile` auto-transform *fuzzy/graph-found spellings of already-configured entities* that the
matchers miss. Today `auto` candidates for configured entities are all exact/stem, which the
matchers already handle.

---

## NEXT SESSION: external-agent eval harness

- The 10 + 1 eval tasks (`PROGRESS.md` → "Eval cases") + the agent-run metrics (task pass rate,
  human approvals, wall-clock, token cost). `ghostc eval` currently fills the primary-metric
  (leak count) row only. Review the task list (open question 3) before building.
- Optional follow-ups: (a) tune `detection.auto_threshold` / add `match[]` seeds so `compile`
  auto-neutralises Contoso; (b) scope-aware graph node ids; (c) the deferred
  configured-entity fuzzy/graph widening above.

## Completed — MVP + detection iterations (2026-08-30)

`compile` · `verify` · `baseline` (`sed` comparator) · `eval` (28 vs 0) · `apply-patch`
(ghost PR diff → real PR diff, fail-closed) · `discover` (candidate scoring, 13/13 recall,
Meridian+Contoso proposed, 0 OSS FPs) · threshold-driven `compile` · `CHANGELOG.md`. Details
in `PROGRESS.md` ("what it does" sections + decision log) and
`memory/{compiler-and-alias-model,verify-and-leak-scan,baseline-and-eval,
reverse-patch-compiler,detection-scoring}.md`.

## Open questions for the user

1. Ghost prose casing inconsistency (`client-a` / `Client A` / `ClientA`) — leave as-is
   (reversible, cosmetic) or add a normalisation pass? Tests currently pin current behaviour.
   (`apply-patch` inherits this as its `lossy` flag.)
2. File renaming in `compile` (sensitive path components + git baseline in `workspace/ghost/`)
   — keep? `test_compile.py` encodes "keep" as the spec.
3. The 10 eval tasks (`PROGRESS.md` → "Eval cases") — review before the external-agent harness.
4. `discover` default thresholds (`detection.auto_threshold` 0.90 / `review_threshold` 0.45)
   and whether `auto_alias` should ship on. Contoso (0.83) currently needs a human; Meridian
   (0.99) auto-compiles when `auto_alias: true`.
