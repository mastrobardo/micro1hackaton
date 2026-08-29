# Progress — Privacy Agent (hackathon slice)

Running status board. Skim this first.

---

## Snapshot

| | |
|---|---|
| **Phase** | Scaffold + discovery done → awaiting entity-list sign-off, then build `compile` |
| **Last updated** | 2026-08-29 |
| **Base fixture** | `hagopj13/node-express-boilerplate` (MIT) cloned at `../node-express-boilerplate` |
| **Blocked on** | Your approval of the discovery result (`SESSION_TODO.md` → "Discovery result") |
| **Next action** | Implement `ghostc compile` (tree-sitter JS/TS + HCL, node-scoped, stable aliases) |

## How to run today

```bash
python -m venv .venv && . .venv/bin/activate && pip install -e .
ghostc --help
ghostc validate-config --config privacy.yaml   # WORKS: validates + summarises (13 seed entities)
./fixtures/apply.sh                             # WORKS: builds workspace/real/ (base repo + synthetic layer)
```

`discover` / `compile` / `verify` / `apply-patch` / `eval` are stubs — they print a pointer and exit.

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
| 2026-08-29 | Discovery: base repo has no sensitive surface; ground truth = 13 seed entities only | Base repo third-party refs are all OSS libs / localhost / placeholders -> `public` |

## In scope (hackathon)

one-shot privacy compiler (JS/TS + HCL) · stable entity/mapping model + 4 levels · entity-discovery agent · verification agent (leak + build gate) · reverse patch compiler · evaluation harness · audit/monitoring (first-class)

## Out of scope (future work — see `TODO.md`)

incremental/persistent sync (Ph4) · GitHub/Jira integration (Ph10) · separate internal-LLM infra (Ph3) · languages beyond JS/TS/HCL · encryption / credential-isolation infra (Ph11) · adaptive task-specific projection (Ph15)

---

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
