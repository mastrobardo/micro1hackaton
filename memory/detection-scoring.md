---
name: detection-scoring
description: `ghostc discover` — candidate scoring model, reference graph, anchor-driven proposals, threshold-driven compile
metadata:
  type: project
---

Implemented 2026-08-30 (Iteration 6, was SESSION_TODO "detection overhaul"). Modules:
`ghostc/detect/{candidate,settings,tokenize,shapes,decode,graph,semantic,signals,scan}.py` ·
`ghostc/discover.py` · `tests/{test_scoring,test_discover}.py` ·
`tests/expected/discover-groundtruth.json`. See [[compiler-and-alias-model]],
[[privacy-levels-model]], [[testing-approach]], [[baseline-and-eval]].

## Scoring model

- **`Candidate{surface, entity_id|None, kind, level, score, signals[], action, occurrences[], aliases[]}`**.
  `score = 1 − Π(1 − wᵢ)` (noisy-OR) over independent `Signal{name, weight, detail}`; an
  `exact` signal (weight 1.0) short-circuits to 1.00. `combine_score` in `candidate.py`.
- **Signals** (default weights in `signals.py` `W_*`, overridable via
  `detection.signal_weights`): `exact` 1.0 · `stem` 0.85 (contiguous segment run inside a
  compound token; 0.6 for a prefix of a longer segment) · `import_ref` 0.9 (scoped `@x/y`
  package, or `.env`/import node) · `symbol_context` 0.8 · `alias_enum` 0.8 (a
  "known internally as: …" comment list) · `acronym` 0.22 alone / 0.7 if the full stem also
  appears in the same file · `fuzzy` 0.45–0.7 (`rapidfuzz`, len≥6 ratio≥88, skips bare
  generic words) · `shape` 0.3–0.55 (review-only) · `decoded` 0.5 (review-only) · `semantic`
  ≤0.45 (review-only) · `graph` = decayed taint · `weak` 0.02.
- **`action`** via `classify()`: `auto` needs `score ≥ auto_threshold` **and** a *hard*
  structural signal (`has_hard_evidence`: exact/stem/import_ref/symbol_context, or graph ≥ 0.9)
  — fuzzy/semantic/shape/acronym alone never auto. `restricted` never auto. An unconfigured
  proposal auto-transforms only when `detection.auto_alias` is on. Else `review` (≥
  `review_threshold`) or `ignore`.
- Defaults (`settings.py` `DetectionSettings`, from the optional `detection:` block in
  `privacy.yaml`, schema-validated): `auto_threshold 0.90`, `review_threshold 0.45`,
  `auto_alias false`, `decode_pass true`, `graph_decay 0.85`, `graph_floor_hops 3`.

## Reference graph (`graph.py`, networkx)

tree-sitter walk of JS/TS → DiGraph: `const a = b` alias, `require`/destructure, `new C()`,
`obj.prop = x`, call args, `module.exports`, `x || 'literal'` / `process.env.X` flows. `taint()`
BFS from seed nodes (occurrences already scoring ≥ 0.5), ×0.85 per hop, stop at `floor_hops`.
This is what lifts laundered aliases (`@meridianaero/flight-sdk` → `RestrictedFlightClient` →
`client` → `flightProvider` → `providers`). Node ids are bare identifier names — scope-
insensitive, accepted imprecision.

## Anchor-driven proposals — the precision lever

An unconfigured entity is proposed **only from an anchor**: a scoped `@company/pkg`, a declared
alias list, an `*.internal` host, a decoded literal with a distinctive stem, or graph taint
from a real occurrence. Weaker mentions (env var, camel identifier, comment) only *attach* to
an existing anchor by stem match (long stems match by prefix, acronyms exact). No anchor → the
token is dropped. An early "distinctive identifier" heuristic without anchors proposed `helmet`
/ `moment` / `swagger-jsdoc`; anchors give **0 OSS false positives** on the fixture at the cost
of missing a truly context-free brand mention.

## Fixture result

`discover` on `workspace/real`: **13/13** configured entities re-found from code alone
(`recall_configured` 1.0), **Meridian Aero Systems 0.99** + **Contoso (`gw.prod.contoso.internal`)
0.83** proposed, **0** denylisted OSS tokens. `adversary.js`
(`fixtures/inject/src/integrations/`) is the adversarial corpus — fictional, unconfigured on
purpose, excluded from the lint gate, stray `y` on line 1 removed.

## Threshold-driven `compile`

`compile_repo(detect=True)` runs the scan: `auto_alias` off (default) → matcher output
byte-identical, `review` candidates → `workspace/private/candidates.jsonl` +
`compile.candidate_review` audit; on → each unconfigured `auto` candidate becomes a synthetic
`source: discovered` entity (`_augment_with_auto_candidates`, flat alias `vendor-e` etc.) and
is transformed — a `restricted` proposal raises `BLOCKED`. `eval.py` passes `detect=False` (it
only wants the matcher residual). CLI: `--no-detect`, `--candidates`.

## Import specifiers (edge case, fixed 2026-08-30)

`auto_alias` on a scoped-package-anchored proposal (Meridian's signal *is*
`@meridianaero/flight-sdk`) used to rewrite `require('@meridianaero/flight-sdk')` →
`require('@vendor-e/flight-sdk')`, which breaks `yarn install` / `require` in the ghost.
Now `compile` keeps package import specifiers verbatim (see [[compiler-and-alias-model]]
→ "Import specifiers kept, not aliased") and flags them in `ghost-spec.md` +
`compile.import_specifier_kept`. Everything else about the entity (env vars, identifiers,
prose, base64) is still aliased.

## Semantic tier

Optional `[semantic]` extra (`sentence-transformers`); absent → stdlib char-3-gram cosine in
`semantic.py`. Capped ≤ 0.45, review-only either way. Kept optional to protect the
"green pytest from a clean env" reproducibility signal (torch is ~2 GB).

## Audit

Schema gained `discover.candidate_scored` / `compile.candidate_review`; component `discovery`.
Surfaces hashed into `subject.real_sha256` (the schema's only free string key) — `discover`
runs on the real repo so its events carry no cleartext. `test_discover.py` enforces it.
