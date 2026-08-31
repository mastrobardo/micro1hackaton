# Progress — Privacy Agent (hackathon slice)

Running status board. Skim this first.

---

## Snapshot

| | |
|---|---|
| **Phase** | Full slice shipped (`compile`/`verify`/`baseline`/`eval`/`apply-patch`/`discover`). **Agentic harness in progress:** Phase A (`compile-spec`) + Phase B (`ghostc-agent run-task` — full LangGraph loop to a real-repo PR) shipped; agent code reorganised into `bridge`/`client_agent`/`consultancy_agent` + a `ghostc-mcp` server. **Phase C0 (runnable webapp fixture) shipped.** **Reduced hook-triggered E2E shipped — on the real repos, no synthesized forge:** `client-agent start <spec>` idempotently makes a bare origin `../ghostc-demo/ghost.git` (+ `post-receive` hook) beside the ghost repo and a consultancy clone `../ghostc-demo/ghost-consultancy`; `handoff` commits the sanitized `TASK.md` on `ghostc/task/<id>` in `../ghostc-demo/ghost` as `ghostc-client` and `git push -f origin` → hook runs `consultancy-agent start` against its clone, which commits as `Consultancy Dev` and pushes → `await_consultancy` fetches the branch back → emit_metrics. No PR. Two git identities on the branch; inspect with `git -C ../ghostc-demo/ghost log ghostc/task/<id>`. `consultancy_agent/agent.py` real (Claude JSON-action loop `role="consultancy"` + `--backend stub` fallback); `client_agent/localgit.py` new; `client-agent` / `consultancy-agent` console scripts; `specs/001-add-companyx-integration.md` seeded (`CompanyX`→`partner-a`). Verified live: Claude ran the consultancy loop (partial impl — step budget). Agent env unified in `bridge/env.py` + per-agent keys + `@traceable`. **Session 5: `client-agent open-real-pr <spec>` (`client_agent/reverse_pr.py`) — a SEPARATE reverse-compile "webhook" run after `start`: `git diff <handoff>..origin/ghostc/task/<id>` → `reverse_patch` → a decoded `ghostc/real/<name>` branch on `../ghostc-demo/real` (+ `PR_BODY.md`, `ghostc-client` commit); branch name = spec filename via `decode_slug`; client-side only; fail-closed. Per-run metrics: `bridge/metrics.py::record_run` → `metrics/agent-runs.jsonl` (gitignored; CI/dashboard artifact), one row per agent run (`role` client/consultancy), hook exports `GHOSTC_METRICS_FILE` so the consultancy shares the sink.** `tests/` 268 pass / 1 skip. |
| **Last updated** | 2026-08-31 (session 9 — human review board + process dashboard) |
| **Base fixture** | static: `hagopj13/node-express-boilerplate` (MIT) at `../node-express-boilerplate` → `workspace/real/`. runnable: `fixtures/webapp/app` (zero-dep Node) → `../ghostc-demo/{real,ghost}`. |
| **Blocked on** | Nothing. (Known: `ghostc/patch.py` audit events use `component: "reverse-compiler"`, not the schema's `reverse_compiler` — pre-existing, fix in Phase F.) |
| **Next action** | **Human review board shipped (session 9): `ghostc/review/` — `store.py` (`DecisionStore` over append-only `decisions.jsonl`, latest-wins + history, `summarize()` scorer-vs-human agreement, emits `review.decision_recorded`), `model.py` (streamlit-free: candidates→rows, apply decision, `privacy.yaml` delta), `app.py` (`ghostc-review` Streamlit, `[review]` extra — Review tab + Process-data dashboard tab). `ghostc compile --decisions` / `discover --decisions` consume the file (restricted clearances + accepted proposals → `source: human` entities; no file = today's behaviour). `fixtures/decisions.example.jsonl` seeded (accept Meridian→vendor-e, ignore Contoso) — `compile --decisions` reproduces the reviewed ghost with no Streamlit. Schema: `review.decision_recorded` event + `review` component. `pytest` ~302/1 (+22: test_review_{store,model,decisions,app}). Next: nothing queued — polish / submission.** Prior (session 8 — CI): `.github/workflows/agent-workflow.yml` — job `checks` (compile/verify/eval/pytest + `scripts/ci/check_leak_gate.py` leak-regression gate, eval report + metrics as artifacts); job `roundtrip` runs the reduced flow (stub consultancy) and `scripts/ci/publish-prs.sh` opens the ghost PR + reverse-compiled real PR on two throwaway public GitHub repos under `mastrobardo`. `consultancy_agent/agent.py::_scripted_impl` now writes a small real file (not just `IMPL_NOTES.md`) so the OFFLINE reverse works. New: `client_agent/publish.py` (stdlib PR-body/branch resolver), `scripts/ci/{common,init-demo-repos,publish-prs,run-local}.sh`, `scripts/ci/check_leak_gate.py`, `tests/test_ci_publish.py` (13). `pytest` 281/1. Manual one-time: `scripts/ci/init-demo-repos.sh` + repo secrets `GH_PAT` / `ANTHROPIC_API_KEY`. Verified locally end-to-end against bare-repo stand-ins (both PRs get minimal diffs, real names restored). Prior (session 7): submission docs — New: `GETTING_STARTED.md` (reproduction guide — clean env → baseline → solution → eval → agent workflow; expected output/runtime/cost), `OVERVIEW.md` (one-page intro), `VIDEO_SCRIPT.md` (≤5-min two-column script), `ARCHITECTURE.md` restructured (POC-framing intro + "Where a production integration differs" table: forge/PRs, webhook vs hook, Jira, CI eval gate, human approval, secrets). No code touched; `pytest` still 268/1. **CI session plan is in `SESSION_TODO.md` → "NEXT SESSION — wire the workflow into CI"**: GitHub Actions runs `compile`/`start`/`open-real-pr` (`--consultancy-backend stub` for the deterministic path), swap `LocalBareForge` → GitHub backend behind the `Forge` seam so ghost/real branches become real PRs, publish eval-report + metrics as artifacts, fail on leak regression. **Then (own session, confirmed session 7): a Streamlit human-review board MVP** — reviewer approves/revises `discover` candidates + clears `restricted` proposals, decisions land in an append-only `decisions.jsonl` that `compile --decisions` consumes (seeded example keeps repro Streamlit-free); the same log feeds a scorer-vs-human agreement stat ("process generates data that improves the process"). Detail: `SESSION_TODO.md` → "SESSION AFTER CI". Prior context (session 6, full loop verified live): spec → ghost `TASK.md` → consultancy (real Claude, 8 files, 7/7 ghost tests+build green) → `open-real-pr` → `ghostc/real/001-...` 8 files/13 hunks, leak-scan clean, real names restored, 7/7 real tests+build green, 0 fallbacks. |
| **Measured win** | `ghostc eval` on the fixture: baseline keyword redaction leaves **28** residual real-entity occurrences (casing-aware detector); `compile` leaves **0**. `ghostc discover` re-finds **13/13** configured entities from code alone and proposes the two unconfigured entities in `adversary.js` (**Meridian 0.99**, **Contoso 0.83**) with **0** OSS-library false positives. Round-trips through `apply-patch` onto a real branch. `CHANGELOG.md` records it. |

## How to run the runnable webapp fixture (Phase C0)

```bash
./scripts/demo-webapp.sh          # stage real -> compile ghost -> verify -> npm test both -> serve
# real  http://localhost:3000  → Northwind Airlines / SkyRoute Data Ltd / booking-core / Priya Nair
# ghost http://localhost:3001  → Client A / Vendor A / service-a / Person A   (same UI, same tests)
```

`fixtures/webapp/app/` is the version-controlled template (zero runtime deps: built-in
`http` + `node:test`). `apply.sh` stages it to `$GHOSTC_DEMO_ROOT/real` (default
`../ghostc-demo/real`, a sibling of this repo — **real + ghost live outside the tool repo**);
`ghostc compile --config fixtures/webapp/privacy.webapp.yaml` writes `../ghostc-demo/ghost` +
`ghost-spec.md`; boundary-internal artifacts stay in-repo at `workspace/webapp-private/`.
Tests: `tests/test_webapp_fixture.py` (node-gated) — real + ghost both `npm test` + `build`
green, ghost leak-free. `DEMO_NO_SERVE=1` / `REAL_PORT` / `GHOST_PORT` on the demo script.

## How to run today

Full walkthrough with expected output: **`cli.md`**.

```bash
python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
ghostc validate-config --config privacy.yaml   # WORKS: 14 entities  confidential=8 internal=2 restricted=4
./fixtures/apply.sh                             # WORKS: builds workspace/real/
ghostc compile --repo workspace/real --dry-run # WORKS: 85 scanned, 8 changed, 3 renamed, 13 entities
ghostc compile --repo workspace/real           # WORKS: workspace/ghost/ + ghost-spec.md (cross) ; workspace/private/{mapping.json,audit.jsonl} (never cross)
ghostc verify  --ghost workspace/ghost --mapping workspace/private/mapping.json   # WORKS: PASS/BLOCK, exit 0/1, fail closed
ghostc baseline --repo workspace/real                                            # WORKS: workspace/baseline-ghost/ + baseline-spec.md (keyword redaction, not privacy-safe)
ghostc eval    --real workspace/real                                            # WORKS: workspace/eval-report.{md,csv}; baseline residual 28 vs compile 0
ghostc apply-patch --ghost-diff <d> --mapping workspace/private/mapping.json     # WORKS: ghost PR diff -> real PR diff on stdout; --apply lands it on a branch; fail-closed rejects
pytest -q                                       # WORKS: 205 passed, 1 skipped (fixture built); parity from a clean checkout (more skips, 0 fails)
```

Fixture-dependent tests skip cleanly when `workspace/real/` is absent, so `pytest -q` is
green from a fresh checkout. `python -m tests.gen_groundtruth` regenerates
`tests/expected/groundtruth.json` (the leak-metric baseline) if the injected layer changes.

All seven commands are implemented — no stubs left.

### compile-spec / run-task — what it does (agentic harness, in progress)

**`ghostc compile-spec`** (Phase A, shipped): a real implementation task → a sanitized ghost
`TASK.md`. Deterministic entity substitution via `matching.transform_text` (the *same* engine
as `compile`), sourced from `privacy.yaml` entities **plus every mapping-store entry** — so a
task that names *Meridian* becomes a task that names `vendor-e` once `compile --config
privacy.autoalias.yaml` has frozen that alias. The output is leak-scanned with `anchored_scan`;
any residual real value is a fail-closed `Rejection` (nothing written, `spec.rejected` audit).
An LLM may later rephrase the ghost task for fluency but never performs the redaction.
Modules: `ghostc/agents/spec.py` · `ghostc/agents/state.py`.

**`ghostc-agent run-task`** (Phase B, shipped): the client-side orchestrator as a LangGraph
`StateGraph` — `plan → compile_spec → [leak gate] → handoff (ghost branch + TASK.md) →
await_ghost_pr → reverse_patch → verify → consistency → open_real_pr → emit_metrics` (diagram:
`client_agent/graph.md`, regen with `ghostc-agent print-graph`). `compile_spec` and
`reverse_patch` are the fail-closed gates; on a `Rejection` the run short-circuits to
`emit_metrics` and **no real PR is opened**. The client↔consultancy handoff is git-based: the
client commits `TASK.md` on a `ghostc/task/<id>` branch of a **ghost git remote**; the
consultancy branches `ghostc/impl/<id>` off it, implements, and opens a **ghost PR** (auth to
the ghost remote only); that PR's diff is reverse-compiled to a real diff and opened as a
**real-repo PR** flagged for human review. Remotes are **local bare repos**
(`bridge.forge.LocalBareForge`, offline/reproducible) behind a `Forge` seam a GitHub `gh`
backend can slot into; a "PR" is a JSON record + a pushed `refs/ghostc/pr/<id>`. Every node
emits an audit event (`agent.task_started` … `agent.task_completed`, `agent.metrics`) and the
metrics row is derived from the log. The consistency gate uses Claude via the `anthropic` SDK
(`[agents]` extra, `ANTHROPIC_API_KEY`); `--backend stub` (or no key) uses a deterministic stub
so `pytest` and the eval suite stay offline and reproducible. The Phase B consultancy is a
deterministic simulator (`consultancy_agent/sim.py`); the real Claude tool-loop + boundary
guard is Phase C.

**Package split** (2026-08-31): the agent code left `ghostc/`. `ghostc/` = the deterministic
compiler + `ghostc/spec.py` (`compile_spec`) + `ghostc/mcp_server.py`. `bridge/` = the git
forge + LLM client (imports neither side). `client_agent/` = the orchestrator (`ghostc-agent`),
imports `ghostc` + `bridge`. `consultancy_agent/` = the external agent, **may not import
`ghostc`/`client_agent`** (enforced by `tests/test_boundary.py`). **`ghostc-mcp`**
(`ghostc/mcp_server.py`) exposes `compile_spec` / `discover` / `verify` / `apply_patch` as MCP
tools for the LLM-driven planning/consistency steps and external reuse — the graph's fixed
nodes still call `ghostc.*` in-process. Extras: `[agents]`, `[mcp]`.

### discover — what it does
Candidate-scoring detection over the real repo. Two channels per file: a **phrase** scan
(`anchored_scan` over full name/alias spellings) and a **token** scan
(`ghostc/detect/tokenize.py` — splits `- _ . : / @` + camelCase). Each surface accrues
independent **signals** — `exact` / `stem` / `import_ref` / `fuzzy` (`rapidfuzz`) / `acronym`
/ `shape` (`ghostc/detect/shapes.py`, generic secret / contract-id / tenant / internal-host /
scoped-npm families) / `semantic` (`sentence-transformers` if the `[semantic]` extra is
installed, else a stdlib char-3-gram cosine) — combined by **noisy-OR** (`1 − Π(1 − wᵢ)`;
`exact` short-circuits to 1.0). A **reference graph** (`networkx`, `ghostc/detect/graph.py`:
`const a = b` aliases, `require` destructuring, `obj.prop = x`, call args, `module.exports`,
`process.env.X ↔ default literal`) propagates decaying taint (×0.85/hop) from strong
occurrences, lifting laundered aliases (`flightProvider` → Meridian). A **decode** pass folds
`'a' + 'b'`, `[…].join()` and base64 and re-scans. Each candidate gets `score` ∈ `[0,1]` and
an `action`: `auto` (≥ `auto_threshold` **and** a hard structural signal; `restricted` never
auto), `review`, or `ignore`. **Unconfigured entities are anchor-driven** — a proposal needs a
scoped `@company/pkg`, a declared "known as: …" alias list, an `*.internal` host, a decoded
name, or graph taint; weaker mentions only *attach* to an anchor by stem, so OSS libraries
(`helmet`, `moment`, `swagger-jsdoc`) never propose. Output: ranked table + surface →
`workspace/private/candidates.jsonl` + `discover.candidate_scored` / `discover.entity_proposed`
audit events (surfaces hashed) + precision/recall vs `tests/expected/discover-groundtruth.json`.
Modules: `ghostc/detect/{candidate,settings,tokenize,shapes,decode,graph,semantic,signals,scan}.py`
· `ghostc/discover.py`. Config: the optional `detection:` block in `privacy.yaml`.

`compile` now runs the same scan: with `detection.auto_alias: false` (default) the ghost tree
is byte-identical to the matcher-only output and `review` candidates are written to the queue
+ `compile.candidate_review` audit; with `auto_alias: true` each unconfigured `auto` candidate
gets a minted flat alias and is transformed (a `restricted` proposal blocks the run).

### baseline — what it does
Dumb keyword redaction: plain case-sensitive global string replace of every `real` + every
`match[]` literal/identifier spelling → the kebab ghost alias (`REDACTED` for `strategy:
remove`), longest spelling first. **No AST, no casing engine, no compound splice, no graph, no
mapping store** (not reversible — that's the point). Deterministic; fresh `git init` + baseline
commit; `baseline-spec.md` sibling. It corrupts identifiers (`initDatadog` → `initvendor-c`)
and leaks every casing variant it was not literally configured with (`SKYROUTE_API_KEY`,
`bookingCore`, `BOOKING_CORE_URL`). Module: `ghostc/baseline.py`.

### apply-patch — what it does
Reverse patch compiler: ghost PR diff → real PR diff. Two-pass per diff line — exact
`ghost`→`real` literal (token-boundary anchored, longest first), then segment splicing for the
remaining casings via `ghostc/aliasing.splice_span` (`vendorA`→`skyRoute`,
`VENDOR_A_URL`→`SKYROUTE_URL`, `vendorAClient.js`→`skyRouteClient.js`); the reversible real
"core" per entity is the identifier match spelling that segments into the most pieces, else a
clean `real` token, else the whitespace-split words. Context lines are translated too so the
diff applies. **Fail closed** (`Rejection`, exit 1, `patch.rejected` audit, nothing written):
unmapped ghost-alias-shaped token · a real value present in the ghost diff (reported by entity
id, never cleartext) · `--mapping-version` mismatch · duplicate ghost alias in the store.
`--apply` runs `git apply --3way` onto `--branch` in `--real`. Audit: `patch.parsed` /
`patch.entity_resolved` (per entity: `real_sha256`, `lossy`) / `patch.applied` /
`patch.rejected`. Lossy: multi-word display names round-trip approximately in prose (code
tokens are exact) and are flagged for the human review gate. Modules: `ghostc/patch.py`.

### eval — what it does
Builds both comparators from `--real`, then counts residual real-entity occurrences in each:
**casing-aware** (`compile_repo(tree, dry_run=True)` in detector mode — the compiler's own
matchers, the **primary metric**) and **strict** (`anchored_scan` over configured spellings —
the `verify` / `groundtruth.json` method). MVP: no external agent, so task pass rate /
approvals / wall-clock / tokens are `n/a`. Emits `workspace/eval-report.{md,csv}` + `eval.*`
audit events. On the fixture: baseline **28** residual, compile **0**; strict reads 0/0 (every
configured spelling is an exact keyword, so a keyword `sed` neutralises all of them — the blind
spot the casing-aware detector exists to cover). Module: `ghostc/eval.py`.

### verify — what it does
Three fail-closed checks over the ghost tree: **leak_scan** (`ghostc/scanning.anchored_scan` —
non-overlapping, `[^A-Za-z0-9_]`-bounded, longest-needle-first — over every mapping `real`
value + every seed spelling in `privacy.yaml`), **mapping_leak** (`looks_like_mapping`: any
mapping store / entry / `real_sha256` mention under the ghost), **build** (`yarn lint`;
`skipped` without the toolchain unless `--require-build`). Emits `verify.scan` +
`verify.pass`/`verify.block`; exits 1 on BLOCK. Modules: `ghostc/verify.py` · `ghostc/scanning.py`.

### compile — what it does
tree-sitter (JS/TS/TSX/HCL) + a scoped fallback (`.env*`/`.json`/`.yml`/`.md`/…). Node-scoped edits
only (identifier / string-content / comment). One canonical kebab alias per entity, re-cased per
occurrence by `ghostc/aliasing.py` (segment engine). Renames sensitive path components
(`skyRouteClient.js` → `vendorAClient.js`). Fresh `git init` + one baseline commit in `workspace/ghost/`,
never copies `.git`. Deterministic. Blocks if a `restricted` entity from `discover`/`human` lacks `approved_by`.

**Import specifiers are kept, not aliased.** A `require('@vendor/sdk')` / `import … from '@vendor/sdk'`
package specifier (and the same key in `package.json` `dependencies` etc.) matched by an entity is
left verbatim — a renamed dependency does not resolve in the ghost environment. First-party
specifiers (`./x`, `../x`) still rewrite (the target file is renamed too, so it stays consistent).
Kept specifiers → `CompileResult.kept_specifiers` + `compile.import_specifier_kept` audit + a
"Dependency names left un-aliased" section in `ghost-spec.md`; if a *seed* entity is involved,
`compile` prints a stderr WARNING that `verify` will BLOCK. Override per entity with
`rewrite_imports: true`.

Modules: `ghostc/aliasing.py` · `ghostc/matching.py` · `ghostc/parsers/{treesitter,scoped}.py` · `ghostc/compile.py`

---

## Decision log

| Date | Decision | Why |
|---|---|---|
| 2026-08-29 | Anonymizer written in **Python** (targets TS/JS + HCL via tree-sitter) | Standalone process, not bound to target repo language; matches roadmap Phase 1 |
| 2026-08-29 | Base fixture = **node-express-boilerplate**, not Sharetribe | Sharetribe FE needs a paid API subscription → not reproducible by judges |
| 2026-08-29 | Add a **synthetic sensitive-entity layer** to the fixture | Real OSS has no NDA'd client names; we need ground truth for the leak metric (ground rule 07: synthetic data) |
| 2026-08-29 | Scope = one-shot compiler + verify + reverse patch + eval + audit | Full roadmap (16 phases) too big for the hackathon window |
| 2026-08-29 | **Audit log doubles as the measurement instrument** for the Improvement Changelog | "Monitoring and improving the process is paramount" |
| 2026-08-29 | Privacy levels: public / internal / confidential / restricted, with a decision test | See `THREAT_MODEL.md`; `restricted` blocks sync + needs human approval |
| 2026-08-29 | Discovery: base repo has no sensitive surface; ground truth = seed entities only | Base repo third-party refs are all OSS libs / localhost / placeholders -> `public` |
| 2026-08-30 | Added `person` seed entity (`Priya Nair`); seed set now spans internal+confidential+restricted. `public` deferred to `discover` | User asked for coverage of most levels; a `public` seed would need a fake strategy/ghost and pollute the leak ground truth |
| 2026-08-30 | **Flat alias scheme** (`vendor-a`, `service-a`, `region-a`, `ip-a`, `client-a`) not descriptive (`FlightDataProviderA`) | User preference; shorter, uniform, simpler `\b`-anchored leak-scan regex |
| 2026-08-30 | **Segment-based casing engine** (`aliasing.py`): one canonical kebab alias, re-cased per occurrence; sub-span splice so several entities in one compound token are each rewritten | Fixture has the same entity as `booking-core` / `bookingCore` / `BOOKING_CORE_URL` / `booking-core.internal` |
| 2026-08-30 | `tree-sitter-language-pack` (not `tree-sitter-languages`) | Latter has no Python 3.14 wheel (caps at 3.11) |
| 2026-08-30 | `compile` renames sensitive path components + writes a git baseline commit in `workspace/ghost/` | Filenames leak brands (`skyRouteClient.js`); the ghost PR needs a diff base. Working-agreement "never commit" is about the submission repo, not the throwaway ghost workspace |
| 2026-08-30 | `tests/` suite added; `load_config` now rejects duplicate entity ids | Green `pytest` from a clean env is the Reproducibility signal. Dup ids can't be caught by JSON Schema and would silently shadow in `MappingStore.by_entity_id` — small hardening in `config.py`, covered by `test_config.py` |
| 2026-08-30 | Leak scan (tests + future `verify`) uses non-overlapping `(?<![A-Za-z0-9_])…(?![A-Za-z0-9_])` matching, longest spelling first | `grep -F` substrings give false positives (`ip-a` in `strip-ansi`) and double-count nested spellings (`Northwind` inside `Northwind Airlines`) |
| 2026-08-30 | Explicit boundary layout: `workspace/ghost/` + sibling `ghost-spec.md` cross; `workspace/private/{mapping,audit}` never cross. `compile` guards both directions (paths inside `--out` rejected; ghost tree re-scanned pre-commit) | Old layout put `mapping.json` (cleartext real values) one `ls` from the ghost, separated only by convention and an implicit `out_p.parent` trick. Structure now carries the boundary; guards + tests enforce it |
| 2026-08-30 | Detection roadmap agreed: candidate **scoring** model (`Candidate{score, signals, action}`) → reference **graph** taint (alias propagation) → bounded **fuzzy** + structural shapes → token model for `scoped.py`. Feeds the human-review queue; measured vs `groundtruth.json` (precision/recall per layer) | Pure lexical matcher can't see aliases, near-misses, or unconfigured secrets. Scoring is the backbone the graph/fuzzy/token layers hang off and maps 1:1 to the `auto`/`auto_if_unambiguous`/`human` gates. Sequenced AFTER `verify` |
| 2026-08-30 | `verify` build gate (`yarn lint`) is **best-effort**: `skipped` when `yarn`/`node_modules` absent, and that alone does not block. `--require-build` makes a skip a block | The MIT fixture ships no `node_modules`; a purist fail-closed would make local verification impossible. Leak + mapping checks are always hard gates; production/CI passes `--require-build` |
| 2026-08-30 | One leak-scan implementation: `ghostc/scanning.anchored_scan`, reused by `verify` and by the test suite (`conftest.scan_entity_hits` now delegates) | Was duplicated as a regex in `conftest.py`; drift between the tested scanner and the shipped one would be a silent hole |
| 2026-08-30 | `baseline` reuses `compile`'s file-walk helpers (`_excluded`, `_git_baseline`, `_rmtree`, `_boundary_internal`) rather than re-deriving them | Same "one implementation" principle as `anchored_scan`; the two paths must walk the tree identically for `eval` to be a fair comparison |
| 2026-08-30 | `eval` primary metric = **casing-aware residual** via `compile_repo(tree, dry_run=True)` in detector mode, not strict `anchored_scan` | On this fixture every configured spelling is an exact keyword, so a keyword `sed` drives the strict scan to 0 for both approaches — it can't measure the win. The compiler's own matchers (which know every casing) applied symmetrically to both trees do. Zero new detection code; reuses the shipped pipeline |
| 2026-08-30 | `eval` MVP stops at the leak metric; the 10+1 tasks + agent-run metrics deferred to the external-agent iteration | The primary metric (leak count) is what the changelog's baseline row needs and needs no agent. Wiring an external coding agent + reviewing the task list (open question 3) is its own slice |
| 2026-08-30 | `apply-patch` reverses via **the identifier match spelling with the most segments** (`skyRoute`→`[sky,route]`, not `skyroute`→`[skyroute]`), plus an exact `ghost`→`real` literal pass first | Code identifiers and file paths then round-trip exactly (`vendorAClient.js`→`skyRouteClient.js`); the cost is env-var underscoring can differ (`VENDOR_A_URL`→`SKY_ROUTE_URL`) — still a valid token, caught by the human review gate |
| 2026-08-30 | `apply-patch` is **lossy for multi-word display names** by design (`Northwind Airlines`, `SkyRoute Data Ltd`) and flags them rather than trying to be clever | Forward is many-to-one (`Northwind Airlines` / `Northwind` / `NWA` → `client-a`); reverse can't recover which. The pipeline already has a human review gate (PR-consistency agent) downstream — same limitation as open question 1 |
| 2026-08-30 | `apply-patch` rejections name the **entity id**, never the cleartext real value, in both the audit event and the CLI message | Audit contract: no real sensitive value in the log. `test_rejection_audit_carries_no_cleartext` enforces it |
| 2026-08-30 | `CHANGELOG.md` rows are capability milestones (baseline / compiler / verify / reverse+eval / next), not git SHAs | The user owns iteration boundaries / commits; the changelog stays stable as commits are squashed or reordered. Each row still links a test + an audit-event family |
| 2026-08-30 | Candidate score = **noisy-OR** over independent signal weights (`1 − Π(1 − wᵢ)`), `exact` short-circuits to 1.0; `action` needs score ≥ `auto_threshold` **and** a hard structural signal (exact/stem/import/graph≥0.9) — fuzzy/semantic/shape alone stay `review` | Additive evidence should raise confidence without any one weak signal dominating; the hard-signal gate keeps a high fuzzy score from auto-transforming and keeps the fixture ghost byte-identical when `auto_alias` is off |
| 2026-08-30 | Unconfigured proposals are **anchor-driven**: a new entity needs a scoped `@company/pkg`, a "known as: …" alias list, an `*.internal` host, a decoded name, or reference-graph taint; weak mentions only *attach* to an anchor by stem | Structural "distinctive identifier" heuristics can't tell a vendor from a library — an early version proposed `helmet` / `moment` / `swagger-jsdoc`. Anchors give precision (0 OSS false positives on the fixture) at the cost of missing a truly context-free brand mention |
| 2026-08-30 | Semantic signal is an **optional** `[semantic]` extra (`sentence-transformers`); absent, it falls back to a stdlib char-3-gram cosine and is capped low + review-only either way | `sentence-transformers` pulls ~2 GB of torch; the project's "green pytest from a clean env" reproducibility signal outweighs a stronger semantic tier that is the weakest evidence class anyway |
| 2026-08-30 | New adversarial fixture `fixtures/inject/src/integrations/adversary.js` (fictional *Meridian* / *Contoso*, **unconfigured**); excluded from the `node --check`/`yarn lint` gate | The base repo has no laundered brands; the detection layer needs a corpus of real evasions (alias lists, `@scope/pkg`, env-var laundering, `x = y` chains, base64, split strings). Left unconfigured so `discover` recall is measured "from code alone". It is deliberately not lint-clean |
| 2026-08-30 | `compile` is threshold-driven via the same scan; `detection.auto_alias` (config flag, default **off**) gates minting aliases for unconfigured `auto` candidates. Off → matcher output byte-identical + a review queue; on → mint + transform, `restricted` proposal blocks | User asked for the compiler to "compile whatever hits a certain threshold", configurable on/off. Off-by-default keeps every existing test and the eval number unchanged; on-by-choice neutralises `discover`'s proposals (Meridian → `vendor-e`) |
| 2026-08-30 | Audit schema gains `discover.candidate_scored` / `compile.candidate_review`; discover/compile hash the surface into `subject.real_sha256` (schema's only free string key) | `discover` runs on the *real* repo, so its events must carry no cleartext — same contract as `compile.entity_detected`. `test_discover.py` asserts no seed real value in the audit file |
| 2026-08-30 | **`compile` keeps package import specifiers verbatim** (`require`/`import`/`jest.mock` args + `package.json` dependency keys); rewrites only first-party (`./`, `../`, `~`) specifiers. Per-entity `rewrite_imports: true` forces the old behaviour | A renamed dependency (`@vendor-e/flight-sdk`) does not exist on any registry → the ghost fails `yarn install` / throws `MODULE_NOT_FOUND`. Any *resolvable* rewrite (`npm:` alias, `file:` shim) has to name the real package somewhere the ghost can read, which re-leaks it. So: keep it, record it in the ghost spec + audit, let the human decide. Surfaced by the `auto_alias` Meridian run (its whole detection signal is the scoped package) |
| 2026-08-31 | **Agentic harness = LangGraph client orchestrator + git-based handoff to a separate consultancy process.** Client commits a sanitized `TASK.md` on a `ghostc/task/<id>` branch of a **ghost git remote**; consultancy (ghost-remote auth only) branches off it, implements, opens a **ghost PR**; the client reverse-compiles that PR's diff and opens a **real-repo PR** for human review. Deterministic entity substitution in the spec (`ghostc/agents/spec.py`) reuses `matching.transform_text` + the mapping store; leak-scanned + fail-closed (`spec.rejected`). Remotes are **local bare repos** (`LocalBareForge`) behind a `Forge` seam; a GitHub `gh` backend can replace it without touching the graph | User's design: "a branch and a todo on the ghost branch, todo already sanitized; a hook starts the consultancy dev phase; agent opens a PR to the sanitized repo it has auth for; a real PR with the reversed input opens for real devs". Git-as-the-handoff keeps the two agents in genuinely separate processes/containers with the privacy boundary on the wire, not in one shared function call. Local bare repos keep the whole loop offline + reproducible (green `pytest` from a clean env) |
| 2026-08-31 | **Agents call Claude through the `anthropic` SDK directly (not `langchain-anthropic`); LangGraph only orchestrates.** New deps (`langgraph`, `langsmith`, `anthropic`) live in an `[agents]` extra; the consistency gate + (Phase C) consultancy agent use Claude when `ANTHROPIC_API_KEY` is set, else a deterministic `StubLLM`. `pytest` for the graph uses `importorskip("langgraph")` + `--backend stub` | `claude-api` skill: use the official SDK, not a wrapper. Keeping the LLM out of the core install + defaulting to a stub off the eval path preserves the reproducibility signal; the eval-suite numbers must not swing run-to-run on model sampling |
| 2026-08-31 | **Agent code split into top-level packages `bridge` / `client_agent` / `consultancy_agent` (out of `ghostc/agents/`).** `client_agent` imports `ghostc`; `consultancy_agent` may import **only** `bridge` — a `tests/test_boundary.py` static + subprocess check fails if it reaches `ghostc`/`client_agent`. `bridge` (git forge + LLM client) imports neither. `compile_spec` moved to `ghostc/spec.py` (a deterministic `ghostc` capability); `run-task` moved to the `ghostc-agent` entrypoint so `ghostc` proper stays LLM-/langgraph-free | User: name them client/consultancy, not internal/external, and keep them out of `ghostc`. The privacy boundary is the point of the project — making "external can't see the mapping" a module-import rule (matching the Phase-E container split) catches regressions at test time, not in review |
| 2026-08-31 | **`ghostc` also ships as an MCP server (`ghostc-mcp`, `[mcp]` extra) — hybrid, not full MCP.** Tools `compile_spec` / `discover` / `verify` / `apply_patch`; fail-closed paths return `{"ok": false, ...}`, never a partial ghost. The graph's fixed pipeline nodes keep calling `ghostc.*` in-process | MCP earns its cost where an LLM *chooses* tools (planning / consistency / external reuse — Claude Desktop, Claude Code), not for deterministic orchestration steps that would just gain RPC latency + a server process per test. `mcp` 2.x renamed `FastMCP` → `MCPServer` |
| 2026-08-31 | **Phase C adds a runnable fullstack fixture; the demo proves real + ghost both build & test, not just leak count.** New `fixtures/webapp/` (keep `node-express-boilerplate` for the static eval), a realistic "add CompanyX integration" seed task (AC: env vars, apiClient, wrapper, config, test), and ghost/real `npm test && npm run build` results in `agent.metrics`. Git stays local (`LocalBareForge`) — permissioned per-agent git is later | User: "a key aspect is the real and ghost version will work, so we need to test it… something more demoable". A green build/test on both sides is the end-to-end proof the leak metric alone can't give; a real ticket-shaped task is what the external-agent eval needs anyway |
| 2026-08-31 | **Agent-workflow env unified in one gitignored root `.env`** (`bridge/env.py`, thin wrapper over `python-dotenv` in the `[agents]` extra). `load_env()` runs in `ghostc-agent`'s CLI + `run_task()`; **never overrides an already-set var** (shell / CI / `docker run -e` win). Template `.env.example`; `$GHOSTC_ENV_FILE` overrides the path. Keys: `ANTHROPIC_API_KEY`, `GHOSTC_AGENT_BACKEND/MODEL`, `LANGSMITH_*`. `ghostc` core untouched. `tests/test_env.py` (5) | User: "I need to be able to change env variables… also passed to agents docker later". One file both local runs and Phase-E compose (`env_file: .env`) read; not-override keeps real secrets authoritative; `bridge/` placement lets both client + consultancy containers call it without crossing the import boundary |
| 2026-08-31 | **Per-agent credentials: `bridge/llm.py` resolves `{ROLE}_{SECRET}` → bare `{SECRET}`** for `role` ∈ `client`/`consultancy` (`resolve_secret`). `get_llm(backend, role=)` passes the role's key to `anthropic.Anthropic(api_key=)`; `configure_langsmith(role=)` picks project `{ROLE}_LANGSMITH_PROJECT` → `LANGSMITH_PROJECT` → `ghostc-<role>`. Client wired; consultancy on C2. `tests/test_llm_roles.py` (8) | User: "should we use 2 keys / 2 langsmiths? better for monitoring". Yes — separate LangSmith projects give per-agent trajectories (a deliverable) + token attribution; separate Anthropic keys give billing split + blast-radius isolation and, in Phase E, a credential-level boundary (consultancy container gets only `CONSULTANCY_*`). Fallback keeps single-key working with zero config. Known: pre-Phase-E in-process runs share one `LANGSMITH_PROJECT` (last writer wins) |
| 2026-08-31 | **First integration milestone = a reduced, hook-triggered flow: spec file → ghost feature branch (`TASK.md` at repo root + initial commit + push) → `post-receive` hook → consultancy develops the same branch, STOP before any PR.** `client-agent start specs/NNN.md`; `run_task(stop_after="develop")`; `sim.run_consultancy(open_pr=False)` commits on the feature branch, no `forge.open_pr` / no impl branch. Ghost PR / `reverse_patch` / real PR / consistency gate stay only in the full `run-task`. `tests/test_agentic_e2e.py` proves branch + consultancy commit + hook fired + audit + metrics | User: "start testing the whole agentic flow… client agent reads specs from an md file… `client_agent start specs001.md`… PR opening not in scope: only a new branch on ghost, developed by the consultancy… consultancy runs on a git hook: client creates a ghost feature branch, an md at repo root, an initial commit, then consultancy starts". Runnable happy path end-to-end now > the last third of the pipeline; cut points are reused by the full flow. Server-side hook = `post-receive` on the bare ghost repo (not `post-commit`). |
| 2026-08-31 | **`assert_boundary_clean` removed from `consultancy_agent/agent.py`** — no runtime filesystem self-check. Isolation is infrastructure: ghost-only git auth, a process/container never handed a mapping path or client key, and the static import boundary (`tests/test_boundary.py`, kept). `BoundaryViolation` / `_MAPPING_MARKERS` gone | User: "no assertions on consultancy_agent about assert_boundary_clean — unlikely it will have it in real life". A real external coding agent (Codex/Copilot/Claude) does not audit its own sandbox; a self-check is theatre that a compromised agent ignores anyway. The boundary belongs at the infra seam |
| 2026-08-31 | **`@traceable` spans + LangSmith EU endpoint.** `bridge/trace.py` re-exports `langsmith.traceable` (no-op without `[agents]`); decorates `client.run_task`, every graph node (`node:<name>`), `claude/stub.complete` (`run_type=llm`), `consultancy:sim`. `configure_langsmith` now also resolves `{ROLE}_LANGSMITH_ENDPOINT` → `LANGSMITH_ENDPOINT`. `.env` switched to `python-dotenv` (`[agents]` extra); autouse `tests/conftest.py::_hermetic_agent_env` strips all agent env vars so the suite ignores the dev's real `.env`. C2 stays a hand-rolled Claude tool-loop — **not** `deepagents` | User: "use @traceable pls" + pasted LangSmith EU tracing snippet (`LANGSMITH_ENDPOINT=https://eu.…`). US default + EU key was the 403 in the test run. `deepagents` in the snippet was just the onboarding's framework pick; our framework is LangGraph (already a dep) |
| 2026-08-31 | **Reduced hook-triggered E2E runs on the real demo repos — no synthesized forge.** `client_agent/localgit.py::ensure_ghost_origin` idempotently makes a bare "origin" `../ghostc-demo/ghost.git` beside the ghost repo (git-server stand-in), wires `origin`, installs a `post-receive` hook, and clones a **persistent** consultancy checkout `../ghostc-demo/ghost-consultancy`. `handoff` works in `../ghostc-demo/ghost` directly: `checkout -B ghostc/task/<id> origin/main`, commit the sanitized `TASK.md` as `ghostc-client <client@ghostc.local>`, `git push -f origin` (fires the hook), `checkout main`. The hook runs `consultancy-agent start --repo ../ghostc-demo/ghost-consultancy --branch <ref>` (no mapping/client path); the consultancy commits as `Consultancy Dev <dev@consultancy.example>` (override `CONSULTANCY_GIT_NAME/EMAIL`) and pushes. `await_consultancy` fetches the branch back into the ghost repo (+ `git branch -f` so it is checkoutable). `bridge.forge` is now used **only** by the full `run-task` pipeline. | User: "all git operations are on external branches… as close to real life as possible… if a branch is created I need to check it on the target repo; a workspace or any tmp is of no value" + "could we simulate another user in the consultancy repo?". A bare origin + real clones + branches on the real repo is the real-life shape; two git identities make `git log` show the company opening the task and an external dev implementing it. The synthesized forge was a fake git server that hid the result in a throwaway dir. |
| 2026-08-31 | **`CompanyX`→`partner-a` added to `privacy.webapp.yaml` as a `[ticket:…]`-noted entity**; `test_webapp_config_covers_the_apps_entities` skips ticket-noted entities | The spec (`specs/001-add-companyx-integration.md`) names a vendor the fixture app does not contain yet — it is the thing the ticket asks to add. It still must be a *known* entity so `compile-spec` aliases it (else `CompanyX` leaks into the ghost `TASK.md`). The note marker keeps the "config covers the app" invariant honest |
| 2026-08-31 | **Reverse-compile to the real repo is a SEPARATE client subcommand (`client-agent open-real-pr <spec>`), not a node in the reduced graph.** It runs after `start`, reads the developed `ghostc/task/<id>` branch, `reverse_patch`es the consultancy's diff, and opens a decoded `ghostc/real/<name>` branch on `../ghostc-demo/real`. Branch name from the spec *filename* via `decode_slug` (ghost alias → `kebab(real)`); `task-id:` stays the boundary-neutral ghost id. Every agent run (`start`, `open-real-pr`, consultancy) appends one row to `metrics/agent-runs.jsonl` via `bridge/metrics.py` (gitignored; the hook forwards `GHOSTC_METRICS_FILE`). | User: "the consultancy already creates the code changes on the PR opened by the client agent; we need another command, in the ghost agent, to open a clear branch on the real repo — simulate a webhook". Must be client-side: reversing needs the cleartext mapping + `ghostc`, which `consultancy_agent` cannot import (`test_boundary.py`). Keeping it out of the graph matches a real forge webhook = a separate event into the boundary. Metrics as a first-class per-run file feeds a later dashboard / GH-Action ("like tests or sonar reports"). |
| 2026-08-31 | **Reverse compile onto the real repo now applies cleanly (session 6): `reverse_apply` anchors on the handoff/base pre-images instead of translating context.** `reverse_patch` rebuilt the real diff by token-translating every line incl. context, but forward `compile` isn't a perfect token-level involution (`SKYROUTE_API_KEY`→`VENDOR_A_API_KEY`→reverse `SKY_ROUTE_API_KEY`), so `git apply` rejected `config.js`/`server.js`/`.env.example`. Fix: forward `compile` is line-preserving, so ghost line N @ handoff ≡ real line N @ base — `ghostc.patch.reverse_apply(ghost_diff, …, ghost_at, real_at)` replays the consultancy's hunks onto the real pre-image (context/`-` verbatim from real by position, only `+` lines translated), returns file **contents**, and `reverse_pr.py` writes them straight into `ghostc/real/<name>` (no `git apply`). New files translated wholesale; line-count mismatch → wholesale fallback flagged in `fallbacks`. `_translate` pass 1b: `Vendor A`/`VENDOR A` display forms → real (segment splice can't cross a space). `reverse_patch` (textual) kept for the full `run-task` graph | Chose "build the tree, don't patch it" — a reverse that always applies beats one that's textually pretty but rejects on real projects. Judges get ~2-3 min: the return leg must not fail. Anchoring on the real pre-image also means the reverse is robust to *any* line-preserving consultancy diff, not just this run's |
| 2026-08-31 | **C2/C3 hardening (session 6): the consultancy Claude loop is gated on green tests+build, not on the model's say-so.** `_agent_loop` tracks `tests_green`/`build_green` (reset on every `write_file`), refuses `done:true` until both are `exit=0`, nudges with what's missing, accepts a partial only after 3 refusals or the 40-step budget. `_SYSTEM` rewritten as an ordered method (enumerate ACs → mirror the sibling files → write → verify → done); `_acceptance_criteria` pins the AC block in the prompt; `_parse_action` tolerates fences/prose; prompt trimmed to header + last 30 turns. C3: `agent.run()` records an authoritative `ghost_tests`/`ghost_build` on the developed checkout into the per-run metrics row + `RunResult`; `await_consultancy` merges them into `state["metrics"]`. Kept the hand-rolled text loop (chose the "bigger budget + nudge + green-gate" option over native Anthropic tool-use) — smaller blast radius under the deadline; the stub path and every test are untouched | Live run had stopped at `_MAX_STEPS=24` with ~4/6 ACs and no test run because `done:true` was taken at face value. Making "done" mean "CI is green on this checkout" is the cheap structural fix. Native tool-use in `bridge/llm.py` is the cleaner follow-up (still noted in `SESSION_TODO.md`) but touches the shared LLM client + the `StubLLM` contract — not a deadline change |
| 2026-08-31 | **C0 shipped: fixture = hand-authored zero-dependency Node app; real + ghost checkouts live OUTSIDE the tool repo** (`../ghostc-demo/{real,ghost}`, `$GHOSTC_DEMO_ROOT` override). Template `fixtures/webapp/app/` (built-in `http` + `node:test`, no `npm install`); `scripts/demo-webapp.sh` serves both on :3000/:3001; `privacy.webapp.yaml` = 6-entity subset of the root config, same aliases; `workspace/webapp-private/` holds mapping/audit/candidates; `tests/test_webapp_fixture.py` (node-gated, +6) | User picked "lightweight" over a Yeoman/Vite scaffold and "real + ghost should live outside this folder". Zero deps keeps reproducibility (offline, instant, green from a clean checkout); siblings-of-the-repo matches how `../node-express-boilerplate` already sits. UI values come from the API so the two browser windows visibly differ (`Northwind Airlines`↔`Client A`, `SkyRoute Data Ltd`↔`Vendor A`) |
| 2026-08-31 | **Session 7: submission docs + sharpened thesis; no code.** New `GETTING_STARTED.md` (reproduction guide), `OVERVIEW.md` (one-page intro), `VIDEO_SCRIPT.md` (≤5-min two-column script); `ARCHITECTURE.md` restructured with a "reproducibility-first POC" intro + a "Where a production integration differs" table (forge/PRs, webhook vs hook, Jira, CI eval gate, PR-review approval, per-service secrets). Thesis stated across the framing docs: **reduce the surface for *unintentional* leaks + prove third-party models work on private code without disclosure** — scoped (accidental disclosure, measurable; not adversarial correlation). | Hackathon deliverables 02/03 + judged on Reproducibility (15) and End-to-End finish (20). Two-architecture-docs would hurt a submission, so the POC framing folded into the existing `ARCHITECTURE.md`. `THREAT_MODEL.md` already scoped it honestly (line ~49) — the thesis just wasn't in the headline. |
| 2026-08-31 | **Queued (own sessions, in order): (1) CI — workflow runs in GitHub Actions, judges see opened ghost + real PRs without running anything; (2) Streamlit human-review board MVP — reviewer approves/revises `discover` candidates + clears `restricted` proposals into an append-only `decisions.jsonl` that `compile --decisions` consumes; same log → scorer-vs-human agreement.** | User: "try on CI — they won't run the actions but see the opened PRs" and "a board simulating a human gate approval at discover/compile … the whole process should generate data that will improve the process later". Board is MVP scope, after CI (confirmed). Decisions as a consumed FILE (not just a viz) keeps the ghost reproducible without the UI. |
| 2026-08-31 | **Session 9: human approval is a consumed FILE (`decisions.jsonl`), the Streamlit board only writes it.** `ghostc/review/store.py` `DecisionStore` — append-only, one record per surface/entity, latest-wins + full history; key = `entity_id` or `sha256:<surface>`; `escalate` ⇒ `level: restricted`; `cleared_restricted()` = latest `accept` + `approved_by`; `summarize()` = scorer-vs-human agreement (scorer flagged ∧ human kept, or both ignore). `ghostc compile --decisions` (new `_augment_with_decisions`) injects accepted proposals as `source: human` entities + sets `approved_by` on cleared restricted entities; CLI `pending` filter subtracts `cleared_restricted()`. `discover --decisions` annotates proposals + prints the agreement stat. `ghostc-review` Streamlit (`[review]` extra, `ghostc/review/app.py` re-execs `streamlit run`): Review tab (accept/ignore/escalate → `decisions.jsonl`, live `privacy.yaml` delta) + Process-data dashboard (metrics / eval-report / audit counts / agreement, read-only). `fixtures/decisions.example.jsonl` seeded (accept *Meridian*→`vendor-e`, ignore *Contoso*). Audit: `review.decision_recorded` event + `review` component (hash-only). | User (session 7): "a board simulating a human gate approval … the whole process should generate data that will improve the process later." Consumed-file-not-UI keeps the reviewed ghost reproducible offline (a judge runs `compile --decisions fixtures/decisions.example.jsonl`, no Streamlit). `model.py` split out so the decision logic is unit-tested without a Streamlit runtime. Reused the existing `_augment_with_auto_candidates` synthetic-entity pattern so the matcher pipeline does the actual work. |
| 2026-08-31 | **Session 8: CI as a "publish step" on the verified reduced flow, NOT a rebuild on the `Forge` seam.** `agent-workflow.yml` job `checks` = the offline gate (`compile`/`verify`/`eval`/`pytest` + `check_leak_gate.py`, artifacts). Job `roundtrip` = `client-agent start` + `open-real-pr` (stub) then `scripts/ci/publish-prs.sh` force-pushes `main` + the two branches to two **public throwaway** repos under `mastrobardo` and `gh pr create`s the ghost + real PRs. `_scripted_impl` now writes one small real file so the offline reverse produces a non-empty real PR. `client_agent/publish.py` is stdlib-only (no `[agents]`) so the shell can call it. Real-Claude consultancy only via `workflow_dispatch` + `ANTHROPIC_API_KEY`. | User picked "publish step" + "mastrobardo, public". The reduced flow (the demo path) never used `bridge.forge` — rebuilding it on the seam to satisfy the old SESSION_TODO note would touch verified code and the simulator path, not the live-Claude path. Force-pushing `main` is because `ghostc compile` mints a fresh root each run; the repos are disposable so that's fine. Cross-repo PR creation needs a PAT (`GITHUB_TOKEN` is single-repo), hence the `GH_PAT` secret. |

## In scope (hackathon)

one-shot privacy compiler (JS/TS + HCL) · stable entity/mapping model + 4 levels · entity-discovery agent · verification agent (leak + build gate) · reverse patch compiler · evaluation harness · audit/monitoring (first-class)

## Out of scope (future work — see `TODO.md`)

incremental/persistent sync (Ph4) · GitHub/Jira integration (Ph10) · separate internal-LLM infra (Ph3) · languages beyond JS/TS/HCL · encryption / credential-isolation infra (Ph11) · adaptive task-specific projection (Ph15)

---

## Known limits (compile, v1)

- **Ghost prose casing varies by context**: `client-a` (kebab tokens) / `Client A` (from
  "Northwind Airlines") / `ClientA` (from bare "Northwind" in a comment). Reversible via the
  occurrence log; cosmetic only (comments/strings, not identifiers). Could add a normalisation pass.
- No transform inside HCL string interpolations (`"${var.x}"`) — none in the fixture.
- Single-segment stems (`skyroute`, `northwind`, `nwa`, `datadog`, …) could false-positive in
  free prose; multi-segment stems (`booking-core`) are safe. Acceptable for the fixture.
- `verify`'s leak scan must use `\b`-anchored matching (short aliases like `ip-a` substring-hit
  `strip-ansi`, though only inside the excluded `yarn.lock`).

## Known limits (discover, v1)

- **Anchor-or-nothing for proposals**: a genuinely context-free brand mention (a vendor named
  only once in prose, no package / alias list / host / graph edge) is not proposed. This is the
  deliberate trade for zero OSS-library false positives.
- **Graph is scope-insensitive** (node id = bare identifier name); two locals with the same
  name in different files share taint. Decays fast and never auto-transforms on the graph
  signal alone unless already ≥ 0.9, so the blast radius is small.
- **Decode pass is shallow**: folds literal `+` / `[...].join()` / base64, but not values that
  flow through variables first (`const p = 'meri'; const q = 'dianaero'; p + q`). Review-only.
- **`adversary.js` Contoso lands at 0.83 → `review`, not `auto`** even with `auto_alias` on —
  the internal-host anchor plus env/string mentions don't reach `auto_threshold` (0.90). Raise
  `detection.auto_threshold` down or add a `match[]` seed to compile it automatically.
- Semantic n-gram fallback is weak; the "semantic only" tier rarely clears `review_threshold`
  without the `[semantic]` extra installed.
- **Kept import specifiers still reveal the dependency.** `compile` leaves a package name like
  `@meridianaero/flight-sdk` verbatim (so the ghost resolves) and flags it in the ghost spec —
  it does not hide it. Only *inline* dep maps in `.js` (e.g. `adversary.js`'s `vendorDependencies`
  object, not a real `package.json`) and dynamically-built specifiers still get aliased.
- `rewrite_imports: true` on a seed makes the ghost internally consistent but the renamed
  package still won't `yarn install` — use it only when the private registry is reachable.

## Workflow (target)

```
task text
   -> [Entity Discovery agent]  --memory--> mapping store (stable real<->ghost, versioned)
        (human approval gate on new `restricted` entities)
   -> [Privacy Compiler]  deterministic tree-sitter JS/TS + HCL  -> ghost repo + ghost spec
   -> [Verification agent]  leak scan + `yarn lint`/build  -> PASS / BLOCK (fail closed)
   -> [External coding agent]  normal, ghost only (no real repo / mapping / creds)
   -> ghost PR
   -> [Reverse Patch Compiler]  ghost diff -> real diff (+ ambiguity rejection)
   -> [PR-consistency agent]  real diff matches task? new real entities?  -> HUMAN REVIEW
   -> real PR
   [Orchestrator] enforces gates + writes audit log at every step
```

## Metrics (fill after eval runs)

Now measured by `ghostc eval` (`workspace/eval-report.{md,csv}`, derived from the audit log).
Also enforced by `tests/test_compile.py` + `tests/test_fixture_groundtruth.py` +
`tests/test_baseline.py` + `tests/test_eval.py` + `tests/test_scoring.py` + `tests/test_discover.py`. `pytest`: 205 passed / 1 skipped.

Groundtruth: 67 configured-spelling occurrences in the real repo (adversary.js adds one `northwind` hit).

| Metric | Baseline (`sed` redaction) | Solution (`compile`) | Change |
|---|---|---|---|
| Residual entity occurrences, casing-aware (exposed to external agent) — target 0 | **28** | **0** | −28 (100%) |
| Strict token leaks (`verify` / groundtruth method) — target 0 | 0 | 0 | can't distinguish on this fixture |
| Reversible (ghost PR → real PR) | no | yes (mapping store) | — |
| Task pass rate (real PR applies + `yarn lint` + `yarn test` + acceptance) | n/a — needs agent harness | n/a | — |
| Human approvals per task | n/a | n/a | — |
| Wall-clock per task | n/a | n/a | — |
| Token cost per task | n/a | n/a | — |

`node --check` passes on all 3 ghost JS files; the baseline ghost corrupts JS identifiers
(`initDatadog` → `initvendor-c`) — redaction breaking code is part of what the baseline shows.

## Eval cases (10 + 1 hard, on the fixture)

1. Add `data-testid` / test hook to the user routes layer
2. Change a default value in `src/config` (e.g. rate-limit window)
3. Add a new optional field to the user model + validation
4. Rename an internal service call in the injected integration layer
5. Add a structured-logging line to `auth.service`
6. Add a supported locale/currency to a config list
7. Extract a duplicated helper into `src/utils`
8. Add an env-var-driven feature flag guarding an endpoint
9. Fix a validation message / error copy
10. **HARD:** rewire the `SkyRoute` flight-data integration to a second provider across code + config + `.env` + `infra/*.tf`

## Artifacts produced by a run

| File | Location | Boundary |
|---|---|---|
| ghost repo | `workspace/ghost/` | crosses (external agent sees it) — mirrors real, nothing else |
| ghost spec | `workspace/ghost-spec.md` | crosses (sibling of the ghost, never written inside it) |
| mapping store | `workspace/private/mapping.json` | **never crosses** (contains real values) |
| audit log | `workspace/private/audit.jsonl` | never crosses (hashes only, no secrets) |
| baseline repo | `workspace/baseline-ghost/` + `workspace/baseline-spec.md` | eval comparator only — **not** privacy-safe, never handed to an agent |
| eval report | `workspace/eval-report.md` / `.csv` | submission artifact (derived from the audit log) |

`compile` refuses to run if any of `--spec` / `--mapping` / `--audit` resolves inside `--out`,
and re-scans the ghost tree for stray metadata before the baseline commit (fail closed).
