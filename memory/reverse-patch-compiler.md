---
name: reverse-patch-compiler
description: `ghostc apply-patch` — ghost PR diff -> real PR diff, fail-closed rejects, known lossiness
metadata:
  type: project
---

Implemented 2026-08-30 (SESSION_TODO §3). `ghostc/patch.py` · `tests/test_apply_patch.py`.
See [[compiler-and-alias-model]] (forward), [[baseline-and-eval]], [[verify-and-leak-scan]].

## What it does

Translates a ghost PR diff back to a real PR diff. Per diff line, two passes:

1. **exact `ghost` literal → `real` literal** — token-boundary anchored
   (`(?<![A-Za-z0-9_])…(?![A-Za-z0-9_])`), longest ghost first. Handles `service-a` →
   `booking-core`, `host-a.example` → `api.northwind-internal.net`, `Client A` prose.
2. **segment splice** for the remaining casings, via `ghostc.aliasing.splice_span` — the same
   engine `compile` uses forward. `serviceA` → `bookingCore`, `SERVICE_A_URL` →
   `BOOKING_CORE_URL`, `vendorAClient.js` → `skyRouteClient.js`.

Header lines (`--- `, `+++ `, `diff --git`, `rename from/to`) and **context lines** are
translated too, so the real diff applies against the real tree. `@@`, `index`, mode lines pass
through untouched.

Per-entity reversible "core" = the identifier `match` spelling that segments into the **most
pieces** (`skyRoute` → `[sky, route]` beats `skyroute` → `[skyroute]`), else a clean `real`
token, else the whitespace-split words. Trade-off: code identifiers / file paths round-trip
exactly; env-var underscoring can differ (`VENDOR_A_URL` → `SKY_ROUTE_URL`) — still a valid
token, caught by the downstream human review gate.

## Fail closed — `Rejection` (CLI exit 1, `patch.rejected` audit, nothing written)

- **unmapped ghost-alias-shaped token** — `<prefix>-<char>` / `<prefix>_<CHAR>` / camel
  `<prefix><Char>` in an added/context line, prefix ∈ the store's ghost prefixes, token not a
  known ghost. All-caps plurals (`SERVICES`) and lowercase words (`services`) are *not*
  alias-shaped (no-sep branch requires a mixed-case prefix + upper/digit tail).
- **unexpected real entity in the ghost diff** — `anchored_scan` of added lines finds a real
  value / seed spelling. Reported by **entity id, never cleartext** (audit contract;
  `test_rejection_audit_carries_no_cleartext`).
- **mapping-version mismatch** — `--mapping-version N` ≠ store's `mapping_version`.
- **ambiguous mapping** — duplicate `ghost` alias across entries.

## Apply + audit

`--apply` → `git checkout -b <branch>` + `git apply --3way --whitespace=nowarn` in `--real`.
Audit: `patch.parsed` / `patch.entity_resolved` (per entity: `real_sha256`, `lossy` bool) /
`patch.applied` / `patch.rejected`.

## Known lossy (by design)

Multi-word display names (`Northwind Airlines`, `SkyRoute Data Ltd`, `Priya Nair`): forward is
many-to-one so reverse can't recover word count / prose casing. Flagged `lossy` in
`PatchResult.lossy_entities` + the audit; the pipeline's PR-consistency + human review gate is
downstream. Same limitation as open question 1 (ghost prose casing).

## Changelog

`CHANGELOG.md` at the repo root — evidence-linked, rows = capability milestones (baseline 28 →
compiler 0 → verify → reverse+eval → detection overhaul), each linking a test + an
audit-event family. Numbers from `ghostc eval`.
