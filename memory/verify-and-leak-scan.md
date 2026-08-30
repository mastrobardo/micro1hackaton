---
name: verify-and-leak-scan
description: How `ghostc verify` gates the ghost and the one shared leak-scan primitive
metadata:
  type: project
---

`ghostc verify` (implemented 2026-08-30) is the fail-closed gate before the ghost repo
crosses to an external agent. `ghostc/verify.py` + `ghostc/scanning.py`.

## The scanner (`ghostc/scanning.py`)

`anchored_scan(corpus, needles) -> list[ScanHit]` is the **single** leak-scan primitive —
non-overlapping, `(?<![A-Za-z0-9_])…(?![A-Za-z0-9_])`-bounded, longest-needle-first (so
`Northwind Airlines` subsumes `Northwind`, and `ip-a` never substring-hits `strip-ansi`).
The test suite's `conftest.scan_entity_hits` delegates to it — do not reintroduce a second
regex. Also: `iter_text_files(root)` (UTF-8 files, skips `.git`/`node_modules`) and
`looks_like_mapping(text)` (mapping store / a lone entry / any `real_sha256` mention).

## The three checks (`verify_ghost -> VerifyResult`, `.ok` iff no check failed)

- **leak_scan** — hard gate. Needles = every non-empty `real` in the mapping store **plus**
  every seed spelling in `privacy.yaml` (`real` + `match[]` literal/identifier). Any hit → BLOCK,
  reported as `file:line entity_id (spelling)`.
- **mapping_leak** — hard gate. Any mapping-shaped file anywhere under the ghost → BLOCK.
- **build** — `yarn lint` in the ghost. **Best-effort**: `skipped` when `yarn`/`node_modules`
  absent (the MIT fixture ships none) and a skip alone does not block. `--require-build` turns
  a skip into a block. Production/CI passes `--require-build`.

Any exception in the verifier → a single failing `Check` (fail closed, never crash through).

## CLI + audit

`ghostc verify --ghost <dir> --mapping workspace/private/mapping.json [--config … --audit …
--operation-id … --require-build]`. Emits `verify.scan` (per-check status map) then
`verify.pass` or `verify.block` (decision=block, `details.reasons` = failed check names, **no
cleartext values**). Exit 0 on PASS, 1 on BLOCK.

**How to apply:** reuse `anchored_scan` for any future leak check (e.g. `apply-patch`
ambiguity, `eval` leak metric). Related: [[compiler-and-alias-model]], [[testing-approach]],
[[privacy-levels-model]].
