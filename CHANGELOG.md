# Improvement Changelog

Per the hackathon brief: start from a fair baseline and record every meaningful experiment —
what was tried, why, the evidence (same evaluation each time), and the decision. Include
experiments that were removed and what they taught us.

Every row links to a test and/or an audit-event family. The audit log
(`workspace/private/audit.jsonl`) is both the product's observability feature and this
changelog's evidence source — the eval report is derived from it.

| Metric | Definition |
|---|---|
| **Leak count** (primary) | Real ground-truth sensitive values appearing in {ghost repo + ghost spec}. Target **0**. Counted two ways — strict exact-spelling scan (`anchored_scan`, the `verify` method) and **casing-aware residual** (the compiler's own matchers run as a detector). Casing-aware is primary: on this fixture every configured spelling is an exact keyword, so the strict scan can't separate the approaches. |
| Task pass rate | Reverse-compiled real PR applies cleanly AND `yarn lint` + `yarn test` pass AND the acceptance check passes. |
| Approvals / task | Human approval gates triggered. |
| Time / task, Cost / task | Wall-clock and token cost. |

## Method

- **Fixture:** `hagopj13/node-express-boilerplate` (MIT) + a synthetic sensitive-entity layer
  (`fixtures/`, all fictional — ground rule 07). Ground truth: `tests/expected/groundtruth.json`
  — **66** configured-spelling occurrences across 13 entities.
- **Fair comparison:** `ghostc baseline` (keyword redaction) and `ghostc compile` (the
  workflow) produce trees of the same shape and run through identical downstream steps.
- **Measurement:** `ghostc eval` → `workspace/eval-report.{md,csv}`.

## Progression

> The 10 eval cases + 1 hard case (`PROGRESS.md`) and the agent-run metrics (task pass rate,
> approvals, time, cost) need the external-agent harness — **deferred to its own iteration**.
> `ghostc eval` measures two live points: **Baseline = 28** and **current `compile` = 0**. The
> middle rows are the design progression from 28 to 0 (each covered by its own tests), not
> separately re-measured — marked "—".

| Stage | What we tried and why | Leak count (casing-aware) | Evidence | Decision / learning |
|---|---|:---:|---|---|
| **Baseline** | `sed` keyword redaction: case-sensitive global replace of every configured spelling → the alias (or `REDACTED`). The "simple script people use today". | **28** | `tests/test_baseline.py`; `workspace/eval-report.md`; `baseline.*` audit events | Establishes the starting point. Not reversible; corrupts identifiers (`initDatadog` → `initvendor-c`); leaks every casing variant it was not literally configured with (`SKYROUTE_API_KEY`, `BOOKING_CORE_URL`, …). |
| **Iteration 1 — node-scoped edits** | Replace `sed` with **tree-sitter node-scoped** replacement (JS/TS/HCL) + a scoped fallback for config files — only identifier / string-content / comment nodes, never blind substrings. Motivated by the baseline corrupting unrelated tokens. | — | `tests/test_compile.py` | **Kept.** Stops code corruption; `node --check` passes on the ghost JS. |
| **Iteration 2 — semantic aliases + casing engine** | One canonical kebab alias per entity, **re-cased per occurrence** by a segment engine, with compound-token sub-span splice and sensitive path-component rename. `SkyRoute Data Ltd` → `Vendor A`, not `REDACTED`. Motivated by (a) the agent needing semantics and (b) the same entity appearing as `booking-core` / `bookingCore` / `BOOKING_CORE_URL`. | **0** | `tests/test_compile.py`, `tests/test_determinism.py`; `compile.*` audit events | **Kept.** This is the row that takes the leak count to 0 — the casing engine is the single biggest contributor. Deterministic; reversible via the mapping store. |
| **Iteration 3 — verification gate** | `ghostc verify`: fail-closed leak scan + mapping-leak scan + build gate before anything crosses the boundary. `BLOCK` + exit 1 on any residual real value or mapping-shaped file. | 0 (enforced) | `tests/test_verify.py`; `verify.scan` / `verify.pass` / `verify.block` audit events | **Kept.** Makes 0 a guarantee, not a hope. One shared leak-scan primitive (`anchored_scan`) so the gate and the tests can't drift. |
| **Iteration 4 — mapping store as memory** | Frozen `real ↔ ghost` entries, versioned; a `restricted` entity from `discover`/`human` blocks `compile` until `approved_by`. So an entity seen in a later run keeps its alias. | — | `tests/test_mapping.py`, `tests/test_compile.py` (`frozen_alias_reused`) | **Kept.** Stable identity across runs; prerequisite for the reverse compiler. (Entity Discovery agent itself is still a stub.) |
| **Iteration 5 — reverse patch compiler + eval harness** | `ghostc apply-patch`: ghost PR diff → real PR diff via the mapping + `privacy.yaml` match rules; fail-closed rejects (unmapped alias / real value present in the ghost diff / mapping-version mismatch / duplicate alias); `git apply --3way` onto a real branch. `ghostc eval`: builds both comparators and derives the leak metric from the audit log. | **0** (round-trip: real values restored, no alias survives into the real diff) | `tests/test_apply_patch.py`, `tests/test_eval.py`; `patch.*` / `eval.*` audit events | **Kept.** Closes the loop. Code tokens round-trip exactly; multi-word display names are flagged `lossy` for the downstream human review gate. |
| **Final** | Combine the changes that worked: node-scoped + casing engine + verify gate + mapping memory + reverse compiler. | **0** vs baseline **28** | `workspace/eval-report.md`, `CHANGELOG.md` | Biggest single contributor: **the per-occurrence casing engine** (Iteration 2). A keyword `sed` and a node-scoped replace both leave every casing variant; re-casing one canonical alias is what neutralises them. |
| **Next — detection overhaul** | Candidate **scoring** model → reference-**graph** taint → bounded **fuzzy** + structural shapes → **token model** for the scoped parser. | measured vs `groundtruth.json` — precision / recall / F1 **per layer** | _pending — its own measured iteration_ | Pure lexical matching can't see aliases, near-misses, or unconfigured secrets. |

## Removed experiments

- **Strict exact-spelling scan as the primary metric** — tried first (it is what `verify` and
  `groundtruth.json` use). On this fixture every configured spelling is an exact keyword, so a
  keyword `sed` drives it to **0 for both** baseline and solution: it cannot measure the win.
  Kept as a secondary row; the **casing-aware residual** (compiler matchers as a detector,
  applied symmetrically to both trees) is now primary. Lesson: the measurement instrument has
  to be at least as strong as the thing being measured.
- **Descriptive aliases** (`FlightDataProviderA`) — replaced with a **flat, type-prefixed**
  scheme (`vendor-a`, `service-a`, …). Shorter, uniform, and gives a simple `\b`-anchored
  leak-scan regex. Lesson: the alias scheme is also a test surface.

## Main failure mode + hot take

The failure mode that matters is **the same entity spelled six ways**: `booking-core`,
`bookingCore`, `BOOKING_CORE_URL`, `booking-core.internal`, `booking_core`, and in prose.
Every redaction approach that treats the repo as text — `sed`, and even a careful node-scoped
string replace — neutralises the spelling it was handed and leaks the other five. The only
thing that closes the gap is normalising to **one canonical entity and re-casing it per
occurrence**. That is the whole product in one sentence; everything else (verify gate, mapping
memory, reverse compiler) is making that safe to operate.

## Reproduce

```bash
git clone --depth 1 https://github.com/hagopj13/node-express-boilerplate.git ../node-express-boilerplate
./fixtures/apply.sh
python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
ghostc eval --real workspace/real      # -> workspace/eval-report.{md,csv}
cat workspace/eval-report.md
pytest -q                              # 131 passed, 1 skipped
```
