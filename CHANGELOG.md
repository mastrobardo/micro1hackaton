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
  (`fixtures/`, all fictional — ground rule 07), including `src/integrations/adversary.js` —
  the detection/scoring adversarial corpus (unconfigured *Meridian* / *Contoso*). Ground truth:
  `tests/expected/groundtruth.json` — **67** configured-spelling occurrences across 13 entities;
  `tests/expected/discover-groundtruth.json` — the `ghostc discover` recall / precision targets.
- **Fair comparison:** `ghostc baseline` (keyword redaction) and `ghostc compile` (the
  workflow) produce trees of the same shape and run through identical downstream steps.
- **Measurement:** `ghostc eval` → `workspace/eval-report.{md,csv}`.

## Progression

> **What is measured.** `ghostc eval` scores **13 cases** — one per configured sensitive
> entity present in the fixture — with the same tree, the same scan and the same fixture for
> both approaches: **baseline 7/13 clean, `compile` 13/13**, aggregate residual **28 → 0**.
> Per-case table: `workspace/eval-report.md`; machine-readable
> `workspace/eval-report-cases.csv`. The challenging case is `vendor_skyroute` (29
> occurrences, 6 spellings; baseline leaves 11).
>
> The middle rows below are the design progression from 28 to 0 — each is covered by its own
> tests but was not separately re-measured against the full case set, so its leak column reads
> "—". The agent-run rows (task pass rate, approvals, time, cost) come from
> `metrics/agent-runs.jsonl` on a live run, not from this fixture.

| Stage | What we tried and why | Leak count (casing-aware) | Evidence | Decision / learning |
|---|---|:---:|---|---|
| **Baseline** | `sed` keyword redaction: case-sensitive global replace of every configured spelling → the alias (or `REDACTED`). The "simple script people use today". | **28** | `tests/test_baseline.py`; `workspace/eval-report.md`; `baseline.*` audit events | Establishes the starting point. Not reversible; corrupts identifiers (`initDatadog` → `initvendor-c`); leaks every casing variant it was not literally configured with (`SKYROUTE_API_KEY`, `BOOKING_CORE_URL`, …). |
| **Iteration 1 — node-scoped edits** | Replace `sed` with **tree-sitter node-scoped** replacement (JS/TS/HCL) + a scoped fallback for config files — only identifier / string-content / comment nodes, never blind substrings. Motivated by the baseline corrupting unrelated tokens. | — | `tests/test_compile.py` | **Kept.** Stops code corruption; `node --check` passes on the ghost JS. |
| **Iteration 2 — semantic aliases + casing engine** | One canonical kebab alias per entity, **re-cased per occurrence** by a segment engine, with compound-token sub-span splice and sensitive path-component rename. `SkyRoute Data Ltd` → `Vendor A`, not `REDACTED`. Motivated by (a) the agent needing semantics and (b) the same entity appearing as `booking-core` / `bookingCore` / `BOOKING_CORE_URL`. | **0** | `tests/test_compile.py`, `tests/test_determinism.py`; `compile.*` audit events | **Kept.** This is the row that takes the leak count to 0 — the casing engine is the single biggest contributor. Deterministic; reversible via the mapping store. |
| **Iteration 3 — verification gate** | `ghostc verify`: fail-closed leak scan + mapping-leak scan + build gate before anything crosses the boundary. `BLOCK` + exit 1 on any residual real value or mapping-shaped file. | 0 (enforced) | `tests/test_verify.py`; `verify.scan` / `verify.pass` / `verify.block` audit events | **Kept.** Makes 0 a guarantee, not a hope. One shared leak-scan primitive (`anchored_scan`) so the gate and the tests can't drift. |
| **Iteration 4 — mapping store as memory** | Frozen `real ↔ ghost` entries, versioned; a `restricted` entity from `discover`/`human` blocks `compile` until `approved_by`. So an entity seen in a later run keeps its alias. | — | `tests/test_mapping.py`, `tests/test_compile.py` (`frozen_alias_reused`) | **Kept.** Stable identity across runs; prerequisite for the reverse compiler. (Entity Discovery agent — `ghostc discover` — landed in Iteration 6.) |
| **Iteration 5 — reverse patch compiler + eval harness** | `ghostc apply-patch`: ghost PR diff → real PR diff via the mapping + `privacy.yaml` match rules; fail-closed rejects (unmapped alias / real value present in the ghost diff / mapping-version mismatch / duplicate alias); `git apply --3way` onto a real branch. `ghostc eval`: builds both comparators and derives the leak metric from the audit log. | **0** (round-trip: real values restored, no alias survives into the real diff) | `tests/test_apply_patch.py`, `tests/test_eval.py`; `patch.*` / `eval.*` audit events | **Kept.** Closes the loop. Code tokens round-trip exactly; multi-word display names are flagged `lossy` for the downstream human review gate. |
| **Final** | Combine the changes that worked: node-scoped + casing engine + verify gate + mapping memory + reverse compiler. | **0** vs baseline **28** | `workspace/eval-report.md`, `CHANGELOG.md` | Biggest single contributor: **the per-occurrence casing engine** (Iteration 2). A keyword `sed` and a node-scoped replace both leave every casing variant; re-casing one canonical alias is what neutralises them. |
| **Iteration 6 — detection overhaul (`ghostc discover`)** | Candidate **scoring** model (noisy-OR over independent signals: exact / stem / import / declared-alias / reference-**graph** taint / bounded **fuzzy** (`rapidfuzz`) / structural **shapes** / **decode** pass / semantic) → each candidate gets a score in `[0,1]` and an `auto` / `review` / `ignore` action. New adversarial corpus `fixtures/inject/src/integrations/adversary.js` (fictional vendor *Meridian* + gateway operator *Contoso*, unconfigured on purpose — 20+ evasion forms: alias lists, `@scope/pkg`, env-var laundering, `x = y` alias chains, base64, split strings, case arrays). The compiler is now **threshold-driven**: `detection.auto_alias` off (default) → matcher output byte-identical, candidates written to a review queue; on → unconfigured `auto` candidates get a minted alias and are transformed (restricted still blocks). | Baseline **28** / `compile` **0** unchanged; `discover` on the fixture: **13/13** configured entities re-found from code alone, **Meridian 0.99** + **Contoso 0.83** proposed, **0** OSS libraries proposed | `tests/test_scoring.py`, `tests/test_discover.py`, `tests/test_compile.py` (detection block); `discover.candidate_scored` / `discover.entity_proposed` / `compile.candidate_review` audit events | **Kept.** Anchor-driven proposals (a new entity needs a scoped package / declared alias list / internal host / decoded name / graph taint — weak mentions only *attach* to an anchor) is what gives precision: `helmet` / `moment` / `swagger-jsdoc` never propose. Semantic tier is optional (`[semantic]` extra) with a stdlib n-gram fallback. **Follow-up:** `compile` now keeps package **import specifiers** (`require`/`import` args + `package.json` dep keys) verbatim rather than aliasing them — a renamed dependency does not resolve in the ghost env; first-party (`./`) specifiers still rewrite; kept ones are listed in `ghost-spec.md` + `compile.import_specifier_kept` audit; `rewrite_imports: true` per entity overrides. |

| **Iteration 7 — per-case evaluation + trajectory capture** | Two gaps found by reading the submission against the brief. (a) The eval reported **two aggregate numbers**, which cannot show *which* changes helped — so `ghostc eval` now scores **one case per sensitive entity** (13 exercised on this fixture), same scan on both trees, with the hard case named and a configured-but-absent entity reported as `n/a` rather than counted as a free pass. (b) The agents' step-by-step behaviour existed only as run *summaries* — so `bridge/trajectory.py` records one line per tool call and per nudge, and `scripts/make-trajectories.py` renders `trajectories/` from the audit log + metrics rather than from memory. | baseline **7/13** cases clean · `compile` **13/13** (aggregate 28 → 0, unchanged) | `workspace/eval-report{,-cases}.csv`, `tests/test_eval.py` (per-case block), `tests/test_trajectory.py`, `tests/test_consultancy_trajectory.py`; `eval.case` audit events; `trajectories/` | **Kept.** The per-case view is what makes the win legible: the baseline is not uniformly bad, it is *fine on 7 entities and blind on 6* — every one of those 6 is a casing variant it was never literally given. Also surfaced a real gap: the ghost spec did not declare unconfigured surfaces left verbatim (`Meridian`, `Contoso`), so the ghost now explains itself instead of reading as an unexplained leak. |

| **Iteration 8 — the outbound screen (`ghostc screen` + the `screen` graph node)** | The compiler is **closed-world**: `compile` / `compile-spec` substitute the entities `privacy.yaml` + `mapping.json` name, and their fail-closed leak scan searches for those *same* real spellings. So a partner nobody ever configured — a name typed fresh into a ticket — is invisible to the redactor *and* to its own gate, and crosses untouched. `ghostc discover` had the scorer that catches this, but only as a manual pass over a **repo**, never on the wire. New second gate on the outbound text: structural shapes + standing (unfrozen) `discover` proposals + a **client-side LLM adjudicator**, all folded into the same noisy-OR + `classify` used by `discover`, and wired as a `screen` node between `compile_spec` and `handoff` in both graph shapes. | On `specs/002-onboard-halcyon-cargo.md` (a ticket naming an unconfigured partner): deterministic layer **4/7** findings, + adjudicator **7/7** — and **0** findings on the clean `specs/001` spec with the same real model. Leak metric (baseline **28** / `compile` **0**) unchanged. | `tests/test_screen.py` (22), `tests/test_screen_llm.py` (13), `tests/test_client_graph.py` (7 screen tests); `screen.scanned` / `screen.blocked` audit events | **Kept.** Three design calls carried the result. (1) **Screen the compiler's output, not its input** — everything the closed world handled is already gone, so every finding is by construction an unknown; screening the input would just re-report the config. (2) **The model may accuse, never decide** — each claim is re-anchored into the outbound text with `anchored_scan` (a name that exists only in the real half of the prompt is dropped and counted), and its signal is capped at 0.60, below `auto_threshold`; no screen signal is a *hard* signal, so `classify` can only ever return `review`/`ignore` here. (3) **The layers are complementary, not redundant** — the deterministic detector proposes only from an *anchor*, which is what keeps `helmet` out of `discover`'s proposals and equally what blinds it to `Halcyon Freight` in an English sentence; the LLM has no anchor requirement and caught exactly those three (`Halcyon Freight` 0.58, `HalcyonClient` 0.51, `halcyonClient.js` 0.45) while corroborating the four shapes upward (0.35–0.55 → 0.70–0.81). **Cost:** one client-role call per task (~4k tokens on the fixture). **Availability is not allowed to weaken the gate silently:** `--screen-llm best-effort` (default) records `screen_llm: skipped` when no client key resolves and the deterministic layer still gates; `required` refuses to run on the stub. |

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
pytest -q                              # 369 passed, 2 skipped
```
