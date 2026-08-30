# Session TODO — handoff (updated 2026-08-30)

Start-here checklist for the next session. Long-term plan: `TODO.md`. Running status +
decision log: `PROGRESS.md` (read it first). Memory index: `memory/MEMORY.md`.

## State — the full slice is shipped

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
