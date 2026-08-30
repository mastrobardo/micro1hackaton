# Progress — Privacy Agent (hackathon slice)

Running status board. Skim this first.

---

## Snapshot

| | |
|---|---|
| **Phase** | `compile` implemented + CLI-wired (0 leaks on fixture). Next = `tests/`, then `verify` + baseline |
| **Last updated** | 2026-08-30 |
| **Base fixture** | `hagopj13/node-express-boilerplate` (MIT) cloned at `../node-express-boilerplate` |
| **Blocked on** | Nothing. (Optional review: ghost prose-casing inconsistency — cosmetic, see Known limits) |
| **Next action** | Write `tests/` suite (`test_aliasing` / `test_matching` / `test_compile` + backfill scaffold suite) |

## How to run today

Full walkthrough with expected output: **`cli.md`**.

```bash
python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
ghostc validate-config --config privacy.yaml   # WORKS: 14 entities  confidential=8 internal=2 restricted=4
./fixtures/apply.sh                             # WORKS: builds workspace/real/
ghostc compile --repo workspace/real --dry-run # WORKS: 84 scanned, 7 changed, 3 renamed, 13 entities
ghostc compile --repo workspace/real           # WORKS: writes workspace/ghost/ + ghost-spec.md + mapping.json + audit.jsonl
```

`discover` / `verify` / `apply-patch` / `eval` are stubs — they print a pointer and exit non-zero.

### compile — what it does
tree-sitter (JS/TS/TSX/HCL) + a scoped fallback (`.env*`/`.json`/`.yml`/`.md`/…). Node-scoped edits
only (identifier / string-content / comment). One canonical kebab alias per entity, re-cased per
occurrence by `ghostc/aliasing.py` (segment engine). Renames sensitive path components
(`skyRouteClient.js` → `vendorAClient.js`). Fresh `git init` + one baseline commit in `workspace/ghost/`,
never copies `.git`. Deterministic. Blocks if a `restricted` entity from `discover`/`human` lacks `approved_by`.

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

Ad-hoc check (not the eval harness): `compile` leak scan over `workspace/ghost` for 16 real
tokens → **0** occurrences. `node --check` passes on all 3 ghost JS files. Baseline not yet run.

| Metric | Baseline (`sed` redaction) | Solution | Change |
|---|---|---|---|
| Leak count (real sensitive values exposed to external agent) — target 0 | — | — | — |
| Task pass rate (real PR applies + `yarn lint` + `yarn test` + acceptance) | — | — | — |
| Human approvals per task | — | — | — |
| Wall-clock per task | — | — | — |
| Token cost per task | — | — | — |

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
| ghost repo | `workspace/ghost/` | crosses (external agent sees it) |
| ghost spec | `workspace/ghost-spec.md` | crosses |
| mapping store | `workspace/mapping.json` | **never crosses** (contains real values) |
| audit log | `workspace/audit.jsonl` | never crosses (hashes only, no secrets) |
| eval report | `workspace/eval-report.md` / `.csv` | submission artifact |
