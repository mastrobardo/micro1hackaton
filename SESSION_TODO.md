# Session TODO — handoff (updated 2026-08-30)

Start-here checklist for the next session. Long-term plan: `TODO.md`. Running status +
decision log: `PROGRESS.md` (read it first). Memory index: `memory/MEMORY.md`.

## State

- `pytest` → **109 passed, 1 skipped** (fixture built) / green from a clean checkout.
- Implemented: `validate-config`, `compile`, `verify`. Stubs: `discover`, `apply-patch`, `eval`.
- Working tree is **uncommitted** (user commits each iteration as a CHANGELOG entry). Untracked:
  `ghostc/scanning.py`, `ghostc/verify.py`, `tests/`, `memory/verify-and-leak-scan.md`.
- Boundary layout is live: `workspace/ghost/` + sibling `workspace/ghost-spec.md` cross;
  `workspace/private/{mapping.json,audit.jsonl}` never cross.
- One leak-scan implementation: `ghostc/scanning.anchored_scan` (reuse it everywhere).

## NEXT (in order)

### 1. Baseline keyword-`sed` redaction path
The hackathon is scored on beating a **fair baseline**. Baseline = dumb keyword redaction:
for every entity, replace each `real` + `match[]` spelling with the ghost alias (or `REDACTED`
for `remove`) as a plain case-sensitive global string replace — **no AST, no casing engine, no
compound-token splice, no graph**. Same downstream (same external agent, same eval cases).

- Add `ghostc baseline --repo … --out workspace/baseline-ghost/ --config privacy.yaml`
  (or `scripts/baseline.sh`) producing a tree the same shape `compile` produces, so `eval`
  runs both through identical steps.
- Deterministic; write a `baseline-spec.md` sibling if useful; no mapping store needed
  (baseline is not reversible — that's part of the point).
- It **will** leak: `bookingCore` when the keyword is `booking-core`, `SKYROUTE_API_KEY`,
  `northwind-skyroute-connector`, prose casing. That gap vs `compile` is the measured win.
- Test: `tests/test_baseline.py` — runs, deterministic, and `verify`/`anchored_scan` finds
  **>0** leaks on the baseline ghost (asserting the baseline is genuinely weaker).

### 2. `ghostc eval`
- 10 cases + 1 hard — see `PROGRESS.md` → "Eval cases". **Review them with the user first**
  (open question 3 below).
- MVP metric without the agent: compile the fixture via `compile` and via `baseline`, run
  `anchored_scan` (seed values from `tests/expected/groundtruth.json`) on each → leak count
  per approach. That alone fills the primary-metric row.
- Full metric: run the external agent on each ghost for each case → task pass rate, human
  approvals, wall-clock, token cost. Emit `workspace/eval-report.md` + `.csv`.
- Audit: `eval` events under component `eval`.

### 3. `ghostc apply-patch`
Ghost diff → real diff via the mapping store. Reject: unmapped ghost-alias-shaped tokens,
unexpected real entities, mapping-version mismatch, ambiguous resolution. Reuse `anchored_scan`
for the ambiguity/leak checks. Audit: `patch.parsed` / `patch.entity_resolved` /
`patch.applied` / `patch.rejected`.

### 4. `CHANGELOG.md`
Start the evidence-linked Improvement Changelog: baseline row → each iteration → final, every
row linked to an audit-log slice or a test.

## THEN: detection overhaul (own iteration, after the loop above closes)

Measured vs `tests/expected/groundtruth.json` (precision/recall/F1 per layer):
1. **Candidate scoring model** — replace binary `Hit` with `Candidate{span, entity_id|None,
   score, signals[], level, action}`. `transform_text` applies only `action=="auto"`;
   `review` + unconfigured proposals → `workspace/private/candidates.jsonl` + `discover`
   output + `discover.entity_proposed` audit events. Maps to `auto`/`auto_if_unambiguous`/`human`.
2. **Reference graph** — tree-sitter def→use + value-flow (`const X = <expr>`, props, returns)
   + cross-file exports/imports + `.env var ↔ process.env.VAR ↔ default literal`; decaying
   taint (×0.85/hop, 2–3 hop floor) from configured occurrences → catches aliases.
3. **Bounded fuzzy + shapes** — Levenshtein ≤1 (len≥6)/≤2 (len≥10) vs entity names; entity
   token embedded in an opaque token; structural shapes (RFC1918 IP, 12-digit AWS acct,
   `sk_live_*`/`AKIA*`/JWT, `*.internal`, email). Shapes review-only, never auto.
4. **Token model for `scoped.py`** — real lexer for `.env`/`.json`/`.yaml`/`.md` instead of
   whole-file text; matching/fuzzy/n-gram over token streams (multi-token names first-class).

## Open questions for the user

1. Ghost prose casing inconsistency (`client-a` / `Client A` / `ClientA`) — leave as-is
   (reversible, cosmetic) or add a normalisation pass? Tests currently pin current behaviour.
2. File renaming in `compile` (sensitive path components + git baseline in `workspace/ghost/`)
   — keep? `test_compile.py` encodes "keep" as the spec.
3. The 10 eval tasks (`PROGRESS.md` → "Eval cases") — review before `eval` is built.
