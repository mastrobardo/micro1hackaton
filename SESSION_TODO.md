# Session TODO — handoff (updated 2026-08-30)

Start-here checklist for the next session. Long-term plan: `TODO.md`. Running status +
decision log: `PROGRESS.md` (read it first). Memory index: `memory/MEMORY.md`.

## State

- `pytest` → **131 passed, 1 skipped** (fixture built) / green from a clean checkout.
- Implemented: `validate-config`, `compile`, `verify`, `baseline`, `eval`, `apply-patch`.
  Stub: `discover` (only).
- Working tree is **uncommitted** (user commits each iteration as a CHANGELOG entry). Untracked:
  `ghostc/{scanning,verify,baseline,eval,patch}.py`, `tests/`, `CHANGELOG.md`,
  `memory/{verify-and-leak-scan,baseline-and-eval,reverse-patch-compiler}.md`.
- Boundary layout is live: `workspace/ghost/` + sibling `workspace/ghost-spec.md` cross;
  `workspace/private/{mapping.json,audit.jsonl}` never cross.
- One leak-scan implementation: `ghostc/scanning.anchored_scan` (reuse it everywhere).
- **Measured (`ghostc eval`, fixture):** baseline keyword redaction leaves **28** residual
  real-entity occurrences (casing-aware detector); `compile` leaves **0**. Strict exact-spelling
  scan reads 0/0 — it can't see the difference on this fixture, which is why the casing-aware
  detector is the primary metric. Report: `workspace/eval-report.{md,csv}`. Changelog:
  `CHANGELOG.md`.
- The whole pipeline round-trips: `compile` → `verify` → (agent) → `apply-patch` → real branch.

## NEXT: the detection overhaul (its own measured iteration — see the section below)

## Completed this iteration

### 1. Baseline keyword-`sed` redaction path — DONE
`ghostc baseline --repo … --out workspace/baseline-ghost/` — plain case-sensitive global
replace of every `real` + `match[]` literal/identifier spelling with the kebab ghost alias
(`REDACTED` for `remove`), longest-first. No AST/casing engine/splice/graph, no mapping store.
Deterministic, git baseline commit, `baseline-spec.md` sibling. `ghostc/baseline.py` ·
`tests/test_baseline.py`. It leaks exactly the casing variants a keyword `sed` can't see
(`SKYROUTE_API_KEY`, `bookingCore`, `BOOKING_CORE_URL`, …) and corrupts identifiers
(`initDatadog` → `initvendor-c`) — both on purpose.

### 2. `ghostc eval` — DONE (MVP, no external agent)
`ghostc eval --real workspace/real` builds both comparators and counts residual real-entity
occurrences two ways: **casing-aware** (the compiler's own matchers via
`compile_repo(tree, dry_run=True)` in detector mode — the primary metric) and **strict**
(`anchored_scan` over configured spellings — `verify` / groundtruth method). Emits
`workspace/eval-report.{md,csv}`; audit events under component `eval`. `ghostc/eval.py` ·
`tests/test_eval.py`.

Deferred to the external-agent iteration (open question 3): the 10 + 1 eval **tasks** and the
full metric (task pass rate, approvals, wall-clock, token cost). The MVP fills the
primary-metric row only.

### 3. `ghostc apply-patch` — DONE
Ghost PR diff → real PR diff. `ghostc/patch.py` · `tests/test_apply_patch.py`. Two-pass
translation: exact `ghost`→`real` literal (token-boundary anchored, longest first), then
segment splicing for the remaining casings (`vendorA`→`skyRoute`, `VENDOR_A_URL`→`SKYROUTE_URL`,
`vendorAClient.js`→`skyRouteClient.js`), reusing `ghostc/aliasing.splice_span`. Context lines
are translated too so the real diff applies. Fail closed (`Rejection`, exit 1, `patch.rejected`
audit, nothing written): unmapped ghost-alias-shaped token · real value present in the ghost
diff (named by entity id, never cleartext) · `--mapping-version` mismatch · duplicate ghost
alias. `--apply` → `git apply --3way` onto `--branch` in `--real`. Audit: `patch.parsed` /
`patch.entity_resolved` (per entity, `real_sha256`, `lossy` flag) / `patch.applied` /
`patch.rejected`. Known lossy: multi-word display names (`Northwind Airlines`, `SkyRoute Data
Ltd`) — code tokens round-trip exactly, prose casing lands approximately, flagged for the
downstream human review gate (open question 1 is the same limitation).

### 4. `CHANGELOG.md` — DONE
`CHANGELOG.md` at the repo root: evidence-linked Improvement Changelog. Rows: baseline (28
residual) → 001 compiler (0) → 002 verify → 003 reverse patch + eval → next (detection
overhaul). Every row links a test and/or an audit-event family. Numbers from `ghostc eval`.

## NEXT: detection overhaul (its own measured iteration)

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
