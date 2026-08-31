# Project memory index

Canonical location for this project's memory (in-repo since 2026-08-29). Do not use
`~/.agent/memory.md` for this project — see [Working preferences](working-preferences.md).

- [Project goal and status](project-goal-and-status.md) — what this is, how it's judged, and that live status lives in PROGRESS.md + SESSION_TODO.md (read those first)
- [Working agreements](working-agreements.md) — plan before acting; never commit (user does); markdown trackers over CLI todo; private repos never enter the submission
- [Working preferences](working-preferences.md) — memory stays in-repo; diagram every graph (mermaid beside it); the client/consultancy package boundary is structural + test-enforced
- [Hackathon scope and fixture](hackathon-scope-and-fixture.md) — why Python CLI, why node-express-boilerplate not Sharetribe, why a synthetic entity layer
- [Privacy levels model](privacy-levels-model.md) — the 4 levels + ordered decision test for classifying entities
- [Compiler and alias model](compiler-and-alias-model.md) — `ghostc compile` + the flat-alias / segment-casing engine, decisions, known limits (implemented 2026-08-30)
- [Verify and leak scan](verify-and-leak-scan.md) — `ghostc verify` fail-closed gate (leak / mapping / build) + `anchored_scan`, the one shared leak-scan primitive
- [Baseline and eval](baseline-and-eval.md) — `ghostc baseline` (fair keyword-redaction comparator) + `ghostc eval` (casing-aware residual metric: baseline 28 vs compile 0 on the fixture)
- [Reverse patch compiler](reverse-patch-compiler.md) — `ghostc apply-patch` (ghost PR diff → real PR diff), the two-pass translation, fail-closed rejects, known lossiness; `CHANGELOG.md`
- [Detection scoring](detection-scoring.md) — `ghostc discover` candidate scoring (noisy-OR signals), reference graph taint, anchor-driven proposals, threshold-driven `compile` (`detection.auto_alias`); adversary.js fixture
- [Agent harness](agent-harness.md) — `ghostc compile-spec` + `ghostc-agent run-task` (full: LangGraph, `bridge.forge`, ghost PR → reverse-patch → real PR) + **`client-agent start <spec>` (reduced hook-triggered E2E, session 4 — runs on REAL repos: bare origin `../ghostc-demo/ghost.git` + `post-receive` hook + persistent `ghost-consultancy` clone; two git identities on the branch; `client_agent/localgit.py`)** + `ghostc-mcp`. Packages: `ghostc`/`bridge`/`client_agent`/`consultancy_agent`. **Env: gitignored root `.env` via `bridge/env.py`; per-agent keys `bridge/llm.py::resolve_secret({ROLE}_X → X)` for `role` client|consultancy; `@traceable` via `bridge/trace.py`. C2 = hand-rolled loop, not `deepagents` — currently under-implements on real Claude (step budget), needs hardening.**
- [Demoable fixture](demoable-fixture.md) — **C0 + C1 DONE**: `fixtures/webapp/` zero-dep Node app, real+ghost on :3000/:3001, checkouts OUTSIDE the repo at `../ghostc-demo/{real,ghost}`, `privacy.webapp.yaml` (7 entities, `CompanyX`→`partner-a` added). Spec `specs/001-add-companyx-integration.md` compiles clean. Next: C2 (consultancy loop completes the ticket) + C3 (`ghost_tests`/`ghost_build` in metrics).
- [Testing approach](testing-approach.md) — pytest suite ON DISK + green (222 pass on fixture, 0 fails); leak scanner is `ghostc/scanning.anchored_scan`
- [workspace/ deprecated](workspace-deprecated.md) — user directive (2026-08-31): stop using the in-repo `workspace/` folder; not yet migrated (defaults still point there across `ghostc/cli.py`, scripts, docs, tests); mapping/audit need a gitignored home NOT under `../ghostc-demo/`
