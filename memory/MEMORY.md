# Project memory index

Canonical location for this project's memory (in-repo since 2026-08-29).

- [Project goal and status](project-goal-and-status.md) — what this is, how it's judged, and that live status lives in PROGRESS.md + SESSION_TODO.md (read those first)
- [Working agreements](working-agreements.md) — plan before acting; never commit (user does); markdown trackers over CLI todo; private repos never enter the submission
- [Hackathon scope and fixture](hackathon-scope-and-fixture.md) — why Python CLI, why node-express-boilerplate not Sharetribe, why a synthetic entity layer
- [Privacy levels model](privacy-levels-model.md) — the 4 levels + ordered decision test for classifying entities
- [Compiler and alias model](compiler-and-alias-model.md) — `ghostc compile` + the flat-alias / segment-casing engine, decisions, known limits (implemented 2026-08-30)
- [Verify and leak scan](verify-and-leak-scan.md) — `ghostc verify` fail-closed gate (leak / mapping / build) + `anchored_scan`, the one shared leak-scan primitive
- [Testing approach](testing-approach.md) — pytest suite ON DISK + green (109 pass on fixture / 65 clean-env, 0 fails); leak scanner is `ghostc/scanning.anchored_scan`
