# Session TODO — handoff (updated 2026-08-31, end of session 5)

Start-here checklist for the next session. Running status + decision log: **`PROGRESS.md`
(read first)**. Durable notes: `memory/` (index `memory/MEMORY.md`). Long-term plan:
`TODO.md`. Conventions + "memory stays in-repo": `CLAUDE.md`.

`pytest` → **268 passed, 1 skipped**. Working tree uncommitted (user commits per iteration).
Branch: `feat/006_reverse-pr-and-metrics`.

---

## DONE session 5 — `client-agent open-real-pr` + per-run metrics

Code complete + green; **not yet run live** against `../ghostc-demo/`.

- **`client-agent open-real-pr <spec>`** (`client_agent/reverse_pr.py`) — the SEPARATE
  reverse-compile "webhook", run *after* `client-agent start`. `git diff
  <handoff>..origin/ghostc/task/<id>` (consultancy impl, minus `TASK.md`/`IMPL_NOTES.md`) →
  `ghostc.patch.reverse_patch` → decoded `ghostc/real/<name>` branch on `../ghostc-demo/real`
  (+ `PR_BODY.md`, commit as `ghostc-client`). Branch name = spec **filename** run through
  `decode_slug` (ghost alias → `kebab(real)`). Client-side only (needs the cleartext mapping
  + `ghostc`). Fail-closed on `Rejection`. `--real-branch/--base/--task-id/--metrics-file`.
- **`bridge/metrics.py`** — `record_run(row, *, path=None)` appends one JSON line to
  `metrics/agent-runs.jsonl` (`$GHOSTC_METRICS_FILE` / `--metrics-file` override). Gitignored
  (`metrics/*.jsonl`); `metrics/README.md` + `.gitkeep` tracked. Rows: `role=client` from
  `emit_metrics` (`start`/`run-task`) + `open-real-pr`; `role=consultancy` from `agent.run()`.
  The `post-receive` hook exports `GHOSTC_METRICS_FILE` (threaded `run_task` →
  `ensure_ghost_origin` → `_install_post_receive`) so the consultancy writes the same sink.
- Tests: `tests/test_metrics.py` (4), `tests/test_reverse_pr.py` (4); `test_agentic_e2e.py`
  asserts both roles' rows; `conftest::_hermetic_agent_env` redirects `GHOSTC_METRICS_FILE`
  to a per-test tmp file.
- `_resolve_spec` now returns `(text, spec_id, stem)`.

**Next for this slice:** live demo — `./fixtures/webapp/apply.sh` → `ghostc compile` →
`client-agent start 001-add-companyx-integration --consultancy-backend claude` →
`client-agent open-real-pr 001-add-companyx-integration` → check
`git -C ../ghostc-demo/real log --stat ghostc/real/001-add-companyx-integration` +
`cat metrics/agent-runs.jsonl`. Optional: a `scripts/dashboard.*` that renders the JSONL
(the "GitHub Action like tests/sonar" idea) — deferred, user said "later".

---

## Where we are

The **reduced hook-triggered agentic E2E works end to end on real git repos.**
`client-agent start <spec>` → sanitized `TASK.md` on a `ghostc/task/<id>` branch in the real
ghost repo → `post-receive` hook on a real bare origin → consultancy agent (its own clone,
own git identity) implements + pushes → client fetches the branch back. **No PR, no
synthesized forge, nothing in a workspace/tmp.** Verified live once with
`--consultancy-backend claude` (Claude ran the loop; impl was partial — see gap #1).

Full model + file-by-file changes: **`memory/agent-harness.md`** → "Reduced hook-triggered
E2E … reworked to real repos". Layout:

```
../ghostc-demo/
  ghost.git/           bare "origin" (git-server stand-in) + post-receive hook   ← auto-created on first run
  ghost/               the company ghost repo (ghostc compile output); origin → ../ghost.git
  ghost-consultancy/   the consultancy's own persistent clone of ghost.git       ← auto-created on first run
.ghostc/               scratch TASK.md + mapping/audit — gitignored, NO git.  (workspace/ is deprecated)
```

Two git identities on the branch: `ghostc-client <client@ghostc.local>` (handoff commit) and
`Consultancy Dev <dev@consultancy.example>` (impl commit; override `CONSULTANCY_GIT_NAME/EMAIL`).

---

## NEXT SESSION — C2 finish + C3 (the "it works" proof)

### 1. Harden the consultancy loop so it actually completes the ticket  ← main task

`consultancy_agent/agent.py::_agent_loop` drives Claude through `bridge.llm.complete()` text
("reply with ONE json action per turn") — weak. The live run hit `_MAX_STEPS=24` with ~4 of 6
ACs done (env vars + `partnerAClient` class; **missing** the `companyXStatusService` wrapper,
the `config.providers` entry, `test/companyx.test.js`, and it never ran `npm test`/`build`).

Options (pick one, or combine):
- Bigger `_MAX_STEPS` + a per-turn "AC checklist / you are not done — run the tests, keep
  going" nudge in the transcript; only accept `done:true` after `run_tests` + `run_build`
  came back green.
- Switch to **real Anthropic tool-use**: add a `complete_with_tools(system, messages, tools)`
  method to `bridge/llm.py` (`ClaudeLLM` → `messages.create(tools=…)`, loop on `tool_use`
  blocks), keep `StubLLM` returning the scripted actions. Cleaner than the text protocol.

Success bar: `../ghostc-demo/ghost` on `ghostc/task/001-add-second-provider` passes
`node --test` and `node scripts/build.js` after the consultancy runs.

### 2. C3 — record the real build/test result

- After the consultancy pushes, `await_consultancy` (or a new `test_check` node) runs
  `node --test` + `node scripts/build.js` in a checkout of the task branch; `agent.metrics`
  gains `ghost_tests` / `ghost_build` (pass/fail + counts). (Reverse-patch → real-repo
  build/test is the **full** pipeline's job — see "deferred" below.)
- `scripts/demo-companyx.sh` (or extend `scripts/demo-webapp.sh`): stage real → `ghostc
  compile` → `client-agent start … --consultancy-backend claude` → show the branch + the
  green test run.

### 3. Eyeball LangSmith (5 min)

Confirm `ghostc-consultancy` shows the `consultancy:agent` chain + per-turn `claude.complete`
spans. The **reduced** flow has **no client-side LLM call** (all deterministic nodes), so
`ghostc-client` only gets chain spans — run `client-agent start … --full` to exercise the
client's `consistency` gate (`role="client"`), or accept it and move on.

---

## How to resume

`.env` needs `ANTHROPIC_API_KEY` (or `CLIENT_`/`CONSULTANCY_` variants), `LANGSMITH_API_KEY`
(+ `*_LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com` if EU keys — US default + EU key = 403).

```bash
pip install -e ".[agents]"                     # console scripts: client-agent, consultancy-agent
./fixtures/webapp/apply.sh                      # -> ../ghostc-demo/real
ghostc compile --repo ../ghostc-demo/real --config fixtures/webapp/privacy.webapp.yaml \
  --out ../ghostc-demo/ghost --spec ../ghostc-demo/ghost-spec.md \
  --mapping .ghostc/webapp-private/mapping.json --audit .ghostc/webapp-private/audit.jsonl \
  --candidates .ghostc/webapp-private/candidates.jsonl
client-agent start 001-add-companyx-integration --consultancy-backend claude
git -C ../ghostc-demo/ghost log --stat ghostc/task/001-add-second-provider   # inspect (two actors)

client-agent open-real-pr 001-add-companyx-integration                        # session-5: the "webhook"
git -C ../ghostc-demo/real log --stat ghostc/real/001-add-companyx-integration
cat metrics/agent-runs.jsonl                                                  # one row per agent run
```

Bare origin + consultancy clone are created on first run; re-runs are idempotent
(`handoff` does `checkout -B … origin/main` + `push -f`). `--consultancy-backend stub` is the
offline/deterministic path (writes `IMPL_NOTES.md`). Clean slate:
`rm -rf ../ghostc-demo/ghost.git ../ghostc-demo/ghost-consultancy .ghostc && git -C ../ghostc-demo/ghost branch -D ghostc/task/001-add-second-provider`.

---

## Watch for

- **Don't re-introduce a synthesized forge / workspace for the reduced flow.** All git
  operations happen on the real repos under `../ghostc-demo/`. `bridge.forge.LocalBareForge`
  is now used **only** by the full `ghostc-agent run-task` pipeline.
- `consultancy_agent/` may import **`bridge` only** (`_hook.py` is stdlib-only) — never
  `ghostc` / `client_agent` (`tests/test_boundary.py`).
- No runtime boundary self-check in `consultancy_agent` (removed session 3) — isolation is
  infra (its clone only reaches the ghost origin; no mapping path / `CLIENT_*` key handed in).
- Spec `task-id:` (header of `specs/*.md`) **becomes the git branch name** the consultancy
  sees — keep it boundary-neutral (no real names). `001-…` uses `task-id: 001-add-second-provider`.
- `GHOSTC_AGENT_BACKEND` in `.env` only fills in for `backend="auto"`; an explicit
  `--consultancy-backend stub/claude` wins (fixed this session).
- `tests/conftest.py::_hermetic_agent_env` strips all agent env vars so the suite ignores the
  dev's real `.env`. `test_agentic_e2e.py` / graph tests `importorskip("langgraph")` + `"dotenv"`.

---

## Deferred / carry-forward

- **Full pipeline (`ghostc-agent run-task`) still uses `LocalBareForge`** over throwaway bare
  repos under `.ghostc/agent` (+ `sim.run_consultancy` opening a ghost PR in-process).
  Migrating it to the same real-repo model (real `ghost.git` + `real.git` origins, consultancy
  opens a real ghost PR, reverse-patch → real-repo PR branch) is the next structural step —
  matches Phase D.
- **`workspace/` deprecation not finished** ([[workspace-deprecated]]): `ghostc/cli.py`
  defaults, `fixtures/apply.sh`, `scripts/*.sh`, `README.md`/`ARCHITECTURE.md`/`THREAT_MODEL.md`
  still say `workspace/`. Reduced flow is clean; the rest is a mechanical sweep + a decision
  on where the deterministic `ghostc compile` boundary artifacts should live.
- **D → E → F** (from the 6-phase plan): D — hook posts an event, client graph
  `interrupt()`/resumes (vs. today's synchronous hook). E — docker-compose, 2 services;
  give the consultancy container only `CONSULTANCY_*` + `GHOSTC_AGENT_*` (credential boundary
  at the container). F — `ghostc run-eval-suite` (10+1 tasks + pass-rate/approval/wall-clock/
  token rows), full ARCHITECTURE/CHANGELOG writeup, and fix `ghostc/patch.py`'s audit
  `component: "reverse-compiler"` → `reverse_compiler` (schema enum mismatch, pre-existing).

### Known small stuff

- `ghostc/patch.py` emits `component: "reverse-compiler"` (hyphen) ≠ schema `reverse_compiler`.
- Prose casing `client-a` / `Client A` / `ClientA` varies by context; reverse-patch is lossy
  for multi-word display names (flagged `lossy`, feeds the human gate). Documented, fine.
- `reverse_patch` mints its own `operation_id`; events correlate via `task_id` in `details`.
- `ghostc-mcp` tool results return as text content (`structured_content` null) — add
  return-type hints if the Inspector UX needs structured output.

---

## Open questions for the user (unchanged from session 3)

1. Ghost prose casing (`client-a` / `Client A` / `ClientA`) — leave as-is (reversible,
   cosmetic) or add a normalisation pass? Tests pin current behaviour.
2. `discover` default thresholds (`auto_threshold` 0.90 / `review_threshold` 0.45) and
   whether `detection.auto_alias` should ship on. Contoso (0.83) needs a human; Meridian
   (0.99) auto-compiles when on.
3. The 10 eval tasks (`PROGRESS.md` → "Eval cases") — review before the eval harness (Phase F).
