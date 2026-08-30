---
name: baseline-and-eval
description: `ghostc baseline` (the fair comparator) + `ghostc eval` (the measured leak win), MVP without an external agent
metadata:
  type: project
---

Implemented 2026-08-30 (SESSION_TODO §1–2). See [[compiler-and-alias-model]] and
[[verify-and-leak-scan]].

## `ghostc baseline` — `ghostc/baseline.py`

The fair comparator the hackathon is scored against — "the simple script people use today".
Dumb keyword redaction: plain case-sensitive global `str.replace` of every `real` + every
`match[]` literal/identifier spelling → the kebab ghost alias (`REDACTED` for
`strategy: remove`), **longest needle first** (Python stable sort ⇒ deterministic).
**No** AST, casing engine, compound-token splice, graph, or mapping store — it is deliberately
not reversible. Reuses `compile`'s file-walk helpers (`_excluded`, `_git_baseline`, `_rmtree`,
`_boundary_internal`, `_NullAudit`) so `eval` compares like with like. Writes
`workspace/baseline-ghost/` (fresh `git init` + baseline commit) + `workspace/baseline-spec.md`
sibling; emits `baseline.*` audit events.

It corrupts identifiers (`initDatadog` → `initvendor-c`) and leaks every spelling it was not
literally configured with — that is the point, not a bug.

## `ghostc eval` — `ghostc/eval.py`

MVP metric, **no external coding agent**. Builds baseline + compile ghosts from `--real`, then
counts residual real-entity occurrences in each tree two ways:

- **casing-aware (PRIMARY METRIC)** — `compile_repo(tree, dry_run=True)` in "detector mode":
  the compiler's own matchers run over the tree, writing nothing; `result.hits` /
  `result.entities` are the residual count. Zero new detection code.
- **strict** — `anchored_scan` over configured spellings only (the `verify` /
  `groundtruth.json` method).

Task pass rate / human approvals / wall-clock / token cost are emitted as `n/a` (need the
agent harness — deferred with the 10+1 task review, open question 3). Emits
`workspace/eval-report.{md,csv}` + `eval.metric` ×2 + `eval.summary` under component `eval`.

## Why the casing-aware detector is the primary metric

On this fixture **every configured spelling is an exact keyword**, so a keyword `sed`
neutralises all of them and the strict scan reads **0 for both** approaches — it cannot see
the win. The casing-aware detector, applied symmetrically to both trees, can.

**Result on the fixture:** baseline residual = **28** (`svc_*` + `vendor_*` casing variants:
`SKYROUTE_API_KEY`, `bookingCore`, `BOOKING_CORE_URL`, `DATADOG_SITE`, `SENTRY_DSN`, …),
`compile` residual = **0**. Groundtruth = 66 configured-spelling occurrences; the casing-aware
detector sees 105 in the real repo.

Tests: `tests/test_baseline.py`, `tests/test_eval.py`. `pytest`: 124 passed / 1 skipped.

NEXT: `ghostc apply-patch` → `CHANGELOG.md`, then the detection overhaul.
