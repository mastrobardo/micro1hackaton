---
name: testing-approach
description: How the scaffold phase is tested — pytest suite + fixture ground-truth guard
metadata:
  type: project
---

**STATUS 2026-08-30: the `tests/` suite is ON DISK and green** — `pytest -q` → 87 passed / 1 skipped (fixture built), 65 passed / 23 skipped (clean checkout, `workspace/real/` absent). All files below exist plus `test_aliasing.py`, `test_matching.py`, `test_compile.py`, `test_cli.py`, `test_determinism.py`, and `tests/gen_groundtruth.py` (regenerates the frozen baseline). The leak scanner now lives in `ghostc/scanning.py` as `anchored_scan()` — **non-overlapping, `(?<![A-Za-z0-9_])…(?![A-Za-z0-9_])`-anchored, longest-needle-first** (not `grep -F`: that false-positives `ip-a` in `strip-ansi` and double-counts `Northwind` inside `Northwind Airlines`). `tests/conftest.py::scan_entity_hits()` and `ghostc verify` both call it. Also: `load_config` raises `ConfigError` on duplicate entity ids. New: `tests/test_verify.py` (15 cases) covers the fail-closed gate — see [[verify-and-leak-scan]].

The scaffold phase is tested with a `pytest` suite under `tests/`. Run: `pip install -e ".[dev]" && pytest -q`. Green from a clean env is the Reproducibility (15 pts) signal for judging. Fixture-dependent tests skip (never fail) when `workspace/real/` is missing.

What it covers:
- `test_schemas.py` — the 3 JSON schemas are valid Draft 2020-12; `privacy.yaml` + sample `mapping.json` / `audit.jsonl` validate.
- `test_config.py` — good config loads; broken configs (missing field, bad enum, empty `ghost` on non-`remove` strategy, dup id) raise `ConfigError`; `entities_needing_approval` filter.
- `test_mapping.py` — save/reload roundtrip; frozen-alias invariant raises on ghost change; lookups; ghost stable across instances.
- `test_audit.py` — `emit` writes schema-valid JSONL; `hash_real` deterministic; **no seed real value ever appears in the audit file**.
- `test_fixture_groundtruth.py` — after `fixtures/apply.sh`: every `entities[].real` occurs >=1x in `workspace/real`; every `ghost` value occurs 0x (clean leak-scan baseline); counts match `tests/expected/groundtruth.json`.
- `test_fixture_builds.py` — injected JS passes `node --check` + `yarn lint`; `terraform validate` on `infra/`. Skipped if toolchain absent.
- `test_cli.py` — `--help` lists 6 commands; stubs exit non-zero with pointer; `validate-config` exit codes.
- `test_determinism.py` — `apply.sh` run twice produces an identical tree manifest.

`tests/expected/groundtruth.json` (the 13 real values + occurrence counts) doubles as the seed for the eval harness's leak metric. See `PROGRESS.md` for status.
