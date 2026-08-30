---
name: compiler-and-alias-model
description: How `ghostc compile` and the alias/casing engine work, and the decisions behind them
metadata:
  type: project
---

`ghostc compile` (real repo → privacy-safe ghost repo) is implemented and CLI-wired as of
2026-08-30. Modules: `ghostc/aliasing.py`, `ghostc/matching.py`,
`ghostc/parsers/{treesitter,scoped}.py`, `ghostc/compile.py`. On the fixture: 84 files
scanned, 7 changed, 3 renamed, 13 entities, **0 leaks**, deterministic, ghost JS parses.

## Alias model (decisions)

- **Flat scheme**: `vendor-a`, `service-a`, `region-a`, `ip-a`, `host-a.example`, `client-a`,
  `account-a`, `person-a` — NOT descriptive (`FlightDataProviderA`). User preference; uniform,
  short, simple `\b`-anchored leak-scan regex. Letters assigned in `privacy.yaml` declaration
  order (skyroute=a, aerofeed=b, datadog=c, sentry=d).
- **Segment casing engine** (`aliasing.py`): one canonical kebab alias per entity, re-cased
  per occurrence. `analyze(token)` → lowercase `Segment`s (with char spans) + a `Style`
  (separator + case). `splice_span(token, stem, ghost_segs)` finds an entity's segment run and
  returns just that sub-range re-cased, so several entities in one compound token are each
  rewritten (`northwind-skyroute-connector` → `client-a-vendor-a-connector`). Bare
  lower/upper single-run + multi-segment ghost falls back to `-` (`skyroute` → `vendor-a`).
- `privacy.yaml` `match[]` kinds: `identifier` → a stem (segment list); `literal` →
  case-sensitive substring for prose, re-cased via `render_like` if name-shaped else raw ghost;
  `regex` → escape hatch, whole match → kebab ghost. Segment engine only runs for kinds
  `vendor/client/internal_service/person`; `domain/infra_identifier/secret` are literal-only.

## Compiler behaviour

- tree-sitter (`tree-sitter-language-pack`, NOT `tree-sitter-languages` — no Py3.14 wheel) for
  JS/TS/TSX/HCL; edits only identifier / string-content (`string_fragment`, `template_literal`)
  / comment nodes. `scoped.py` fallback (whole-file text) for `.env*`/`.json`/`.yml`/`.md`/etc.
- Renames sensitive path components (`skyRouteClient.js` → `vendorAClient.js`).
- Fresh `git init` + one baseline commit in `workspace/ghost/`; never copies `.git`.
  ("Never commit" working-agreement is about the submission repo, not this throwaway.)
- `--dry-run` computes + prints, writes nothing. Blocks if a `restricted` entity from
  `discover`/`human` lacks `approved_by`.
- **Boundary layout** (2026-08-30): `workspace/ghost/` + sibling `workspace/ghost-spec.md`
  cross the boundary; `workspace/private/{mapping.json,audit.jsonl}` never cross. CLI flags
  `--out` / `--spec` / `--mapping` / `--audit`. `compile_repo` raises if spec/mapping/audit
  resolve inside `--out` (`_assert_outside_ghost`) and re-scans the ghost tree for stray
  metadata before the git baseline (`_assert_ghost_tree_is_clean`). The ghost tree mirrors
  the real repo and nothing else.
- Artifacts: `workspace/ghost/`, `workspace/ghost-spec.md` (no real values),
  `workspace/private/mapping.json` (13 frozen entries + `{file,line}` occurrences),
  `workspace/private/audit.jsonl` (`real_sha256` only).

## Threshold-driven (2026-08-30, Iteration 6)

`compile_repo` now runs the `ghostc discover` scan (`detect=True` default). With
`detection.auto_alias: false` (default) the ghost tree is **byte-identical** to the
matcher-only output — the scan only writes `workspace/private/candidates.jsonl` +
`compile.candidate_review` audit events for the human review queue. With `auto_alias: true`,
each unconfigured `auto` candidate becomes a synthetic `source: discovered` entity (minted
flat alias) and is transformed; a `restricted` proposal raises `BLOCKED`. Full detail:
[[detection-scoring]].

## Import specifiers kept, not aliased (2026-08-30)

`compile` leaves **package** import specifiers verbatim — `require('@x/sdk')` /
`import … from '@x/sdk'` / `jest.mock('@x/…')` args (via a tree-sitter pre-pass,
`ghostc/parsers/treesitter._spec_string_ranges`) **and** `package.json`
`dependencies`/`devDependencies`/`peerDependencies`/`optionalDependencies`/`resolutions`
KEYS (`ghostc/parsers/scoped._compile_package_json`). Rationale: a renamed dependency
resolves nowhere → the ghost fails `yarn install` / `MODULE_NOT_FOUND`; any resolvable
rewrite re-leaks the real name. First-party specifiers (`./`, `../`, `~`) still rewrite
(the target file is renamed too → consistent). `node:` builtins are kept.
`matching.transform_text(text, "import_specifier", …)` returns the matching `Hit`s with
`kept=True` and unchanged text. `compile` routes them to
`CompileResult.kept_specifiers` + `compile.import_specifier_kept` audit + a
"Dependency names left un-aliased" section in `ghost-spec.md`; a *seed* entity in a
specifier → stderr WARNING that `verify` will BLOCK. Per-entity `rewrite_imports: true`
(schema) forces the old rewrite-everywhere behaviour. Not yet covered: dynamically-built
specifiers and inline dep-map objects inside `.js` (`adversary.js` `vendorDependencies`).

## Known limits

Ghost prose casing varies (`client-a` / `Client A` / `ClientA`) — reversible, cosmetic.
No transform in HCL `"${var.x}"` interpolations. Single-segment stems could false-positive in
free prose. See `PROGRESS.md` → "Known limits". `person` entity added so seeds span
internal/confidential/restricted; `public` deferred to `discover`. Related:
[[privacy-levels-model]], [[testing-approach]], [[hackathon-scope-and-fixture]].
