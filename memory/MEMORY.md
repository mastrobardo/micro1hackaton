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
- [Agent harness](agent-harness.md) — `ghostc compile-spec` (real task → sanitized ghost TASK.md) + `ghostc-agent run-task` (LangGraph client orchestrator, git-based handoff via `bridge.forge`, ghost PR → reverse-patch → real PR) + `ghostc-mcp` (MCP tools). Packages: `ghostc`/`bridge`/`client_agent`/`consultancy_agent`. Phases A+B shipped on `feat/004_agentic_harness`. **Env: one gitignored root `.env` via `bridge/env.py` (`load_env`, no-override); `.env.example` template; Phase-E compose reuses it. Per-agent keys: `bridge/llm.py` `resolve_secret({ROLE}_X → X)` for `role` client|consultancy — split Anthropic/LangSmith keys + projects + `LANGSMITH_ENDPOINT` (EU tenant), single-key fallback. `@traceable` spans via `bridge/trace.py` (no-op without `[agents]`). C2 = hand-rolled tool-loop, not `deepagents`.**
- [Demoable fixture](demoable-fixture.md) — **C0 SHIPPED**: `fixtures/webapp/` zero-dep Node app, real+ghost served on :3000/:3001 (`./scripts/demo-webapp.sh`), checkouts live OUTSIDE the repo at `../ghostc-demo/{real,ghost}`, `privacy.webapp.yaml` 6-entity subset, +6 pytest tests (235/1). Next: C1 wire the CompanyX ticket through `compile-spec`.
- [Testing approach](testing-approach.md) — pytest suite ON DISK + green (222 pass on fixture, 0 fails); leak scanner is `ghostc/scanning.anchored_scan`
