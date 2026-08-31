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

`_translate` pass **1b** (added 2026-08-31): the space-separated display renderings of a
multi-segment alias — `Vendor A`, `VENDOR A` (how `compile` writes a display literal like
"SkyRoute Data Ltd") — are exact-substituted to `real` before the segment splice, which can't
see across a space. Without it a comment/prose line the consultancy wrote using the ghost
display name would carry a ghost alias into the real PR (real leak, not just cosmetic). Still
lossy on the *other* direction (env-var underscoring `COMPANYX`↔`COMPANY_X`, `id:'companyx'`↔
`'CompanyX'`) — consistent within the file so the code builds/tests, human-gate catches the
spelling.

## `reverse_apply` — handoff/base-anchored reverse (added 2026-08-31, used by `open-real-pr`)

`reverse_patch` (above) rebuilds the real diff by token-translating **every** line incl.
context; forward `compile` is not a perfect token-level involution
(`SKYROUTE_API_KEY`→`VENDOR_A_API_KEY`→reverse `SKY_ROUTE_API_KEY`) so translated context
drifts and `git apply` rejects the hunk. This blocked the live E2E's return leg (`config.js`,
`server.js`, `.env.example`).

`ghostc.patch.reverse_apply(ghost_diff, mapping_path, *, ghost_at, real_at, …)` fixes it:
forward `compile` is **line-preserving** (rewrites tokens *within* a line, never adds/removes
lines), so ghost line N at the handoff commit ≡ real line N at the PR base. It parses the
consultancy's unified diff (`_parse_unified` → `_FileDiff`/`_Hunk`) and:

- **new file** → translate added lines + path wholesale (unchanged; this half always worked);
- **deleted file** → drop;
- **modified file** → `_apply_hunks(real_base_lines, hunks, render_add=tr)` — context and `-`
  lines come **verbatim from the real pre-image by position**, only `+` lines are
  token-translated. Result applies by construction.
- **line-count mismatch** (multi-line string edit; rare) → fallback: translate the
  reconstructed ghost-impl file wholesale, name it in `ReverseApplyResult.fallbacks` (PR body
  + metrics flag it "review closely").

Returns `ReverseApplyResult{files: dict[realpath, str|None], entities_resolved, lossy_entities,
n_files, n_hunks, fallbacks}` — concrete file contents, **not a patch**. `client_agent/
reverse_pr.py` writes them straight into the `ghostc/real/<name>` branch (no `git apply` gate —
the tree is built, not patched). Same fail-closed `_check_ghost_diff` gate as `reverse_patch`
(leak / unmapped alias / version / dup). `ghost_at` = `git show <handoff>:p`, `real_at` =
`git show <base>:p`.

`reverse_patch` (textual) is untouched — still used by the full `ghostc-agent run-task` graph
(`reverse_patch_node`) + `tests/test_apply_patch.py`. New: `tests/test_reverse_pr.py` covers
`reverse_apply` via `open-real-pr`.

**Verified live 2026-08-31:** spec → ghost `TASK.md` (4 subs, no real names) → consultancy
(real Claude, ghost-only, 8 files, **7/7 ghost tests + build green**) → `open-real-pr` →
`ghostc/real/001-add-companyx-integration`: 8 files, 13 hunks, **0 ghost aliases in the diff**
(leak-scan clean), real names restored (`CompanyX`×31, `SkyRoute Data Ltd`, `booking-core`),
**7/7 real tests + build green**, 0 fallbacks.

## Changelog

`CHANGELOG.md` at the repo root — evidence-linked, rows = capability milestones (baseline 28 →
compiler 0 → verify → reverse+eval → detection overhaul), each linking a test + an
audit-event family. Numbers from `ghostc eval`.
