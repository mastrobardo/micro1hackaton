# Session TODO — 2026-08-30

Session-scoped checklist. Long-term plan lives in `TODO.md`; running status in `PROGRESS.md`.

## Done this session: `ghostc compile`

- [x] Flat alias scheme in `privacy.yaml` (`vendor-a`, `service-a`, `region-a`, `ip-a`, `client-a`, …)
- [x] Added `person_service_owner` seed entity (`Priya Nair`) + injected owner line into `internalServices.js`
- [x] `privacy.yaml` `match[]` stems: `northwind`, `skyroute`/`skyRoute`, `aerofeed`, `datadoghq` literal; dropped the `SKYROUTE_[A-Z_]+` regex
- [x] `ghostc/aliasing.py` — segment casing engine (`analyze` / `render` / `splice_span` / `render_like`)
- [x] `ghostc/matching.py` — entity matchers, longest-span + remove/level priority, multi-entity compound tokens
- [x] `ghostc/parsers/treesitter.py` (JS/TS/TSX/HCL) + `ghostc/parsers/scoped.py` (`.env*`/`.json`/`.yml`/`.md`/…)
- [x] `ghostc/compile.py` — walk + exclusions, ghost tree, path rename, `git` baseline, mapping store, `ghost-spec.md`, audit events
- [x] Wired `compile` into `cli.py` (+ approval-gate pre-flight); deps → `tree-sitter-language-pack`
- [x] `cli.md` — manual test walkthrough, every command verified
- Result: 84 files scanned, 7 changed, 3 renamed, 13 entities, **0 leaks**, deterministic, ghost JS parses

## Next session (in order)

- [ ] **`tests/` suite** (nothing on disk yet):
  - `test_aliasing.py` — `analyze`/`render` round-trip, `splice_span` sub-spans, bare-run `-` fallback
  - `test_matching.py` — remove/level tie priority, multi-entity compound token, name-shaped literal casing
  - `test_compile.py` — 0 real values in ghost, determinism/idempotence, `.git` not copied, rename, spec has no real values, 3+ levels in spec, frozen-alias reuse on 2nd run
  - backfill scaffold suite from the `testing-approach` memory: `test_schemas` / `test_config` / `test_mapping` / `test_audit` / `test_fixture_groundtruth` (+ `tests/expected/groundtruth.json`) / `test_cli` / `test_determinism`; `test_fixture_builds` skips if `node`/`terraform` absent
- [ ] `ghostc verify` — `\b`-anchored leak scan + `yarn lint` gate, fail closed
- [ ] Baseline `sed` keyword-redaction path
- [ ] `ghostc eval` — 10 cases, baseline vs solution, metric table
- [ ] `ghostc apply-patch` — ghost diff → real diff + ambiguity rejection
- [ ] Start filling `CHANGELOG.md` with evidence-linked rows

## Open questions for you

1. Ghost prose casing inconsistency (`client-a` / `Client A` / `ClientA`) — leave as-is (reversible, cosmetic) or add a normalisation pass?
2. File renaming in `compile` (sensitive path components + git baseline commit in `workspace/ghost/`) — keep?
3. The 10 eval tasks (`PROGRESS.md` → "Eval cases") — still deferred; review before `eval` is built.
