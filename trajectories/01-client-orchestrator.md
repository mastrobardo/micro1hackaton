# Trajectory 1 — client orchestrator (`client_agent`)

> **Generated** by `scripts/make-trajectories.py` from `.ghostc/webapp-private/audit.jsonl`
> and `metrics/agent-runs.jsonl`. Every timestamp, branch, count and tool response below is read
> from those logs — only the narrative between the tables is authored. Regenerate with:
>
> ```bash
> scripts/make-trajectories.py --audit .ghostc/webapp-private/audit.jsonl --metrics metrics/agent-runs.jsonl --out trajectories
> ```


## The agent

| | |
|---|---|
| **Role** | Company-side orchestrator. Owns the real repo, the mapping store and the audit log. The only component allowed to see both sides of the boundary. |
| **Kind** | LangGraph state machine — fixed nodes, deterministic transitions. Not a free-running prompt loop: the graph decides what happens next, so a fail-closed gate cannot be talked out of by a model. |
| **Instructions** | The graph topology itself (`client_agent/graph.py::_wire`, diagram in `client_agent/graph.md`). Two LLM calls inside it — the outbound-screen adjudicator (`client_agent/screen_llm.py`) and the PR-consistency verdict (`client_agent/graph.py`) — and neither of them decides anything on its own. |
| **Tools** | `ghostc.spec.compile_spec`, `ghostc.screen.screen_text`, `ghostc.patch.reverse_patch`, `ghostc.verify`, `bridge.forge` (git), `bridge.llm` (screen adjudicator + consistency verdict). |
| **Boundary rule** | `handoff` is the only node that writes to the ghost side. |

## Node sequence

```
plan → compile_spec → screen → handoff → await_ghost_pr → reverse_patch
     → verify → consistency → open_real_pr → emit_metrics
```

Dotted edges in `client_agent/graph.md` are fail-closed short-circuits: on any `Rejection`, the run jumps straight to `emit_metrics` and **no PR is opened**.

`compile_spec` and `screen` are the two gates in front of the wire, and they fail for opposite reasons: `compile_spec` blocks when a **known** real spelling survives its own substitution, `screen` blocks when something **nobody ever configured** is still there. The first is closed-world and cannot see the second class at all.

## What actually happened


### Invocation 1 — `ghostc compile` — stage the ghost repo  ·  `operation_id=op_c524e7a01f67`

| t | component | event | decision | what happened |
|---|---|---|---|---|
| 0.0s | `compiler` | `run.start` | — | config=fixtures/webapp/privacy.webapp.yaml · dry_run=False · out=../ghostc-demo/ghost · repo=../ghostc-demo/real |
| 0.1s | `compiler` | `run.end` | — | entities=7 · files_changed=11 · files_renamed=2 · files_scanned=14 · occurrences=91 |

### Invocation 2 — `client-agent start` — sanitize the ticket and hand off  ·  `operation_id=op_77622b2fbfb5`

| t | component | event | decision | what happened |
|---|---|---|---|---|
| 0.0s | `client_agent` | `agent.task_started` | — | backend=auto · task_id=001-add-second-provider |
| 0.0s | `spec_compiler` | `spec.compiled` | — | 4 entities substituted: client_northwind→`client-a` ×2, svc_booking_core→`service-a` ×2, vendor_companyx→`partner-a` ×17, vendor_skyroute→`vendor-a` ×6 |
| 183.4s | `client_agent` | `agent.spec_handoff` | — | branch=ghostc/task/001-add-second-provider · substitutions=4 · task_id=001-add-second-provider |
| 183.5s | `client_agent` | `agent.metrics` | — | wall_clock_s=183.518 · ghost_tests={"fail": 0, "ok": true, "pass": 7, "tests": 7} · ghost_build={"ok": true} · llm_model=claude-opus-5 · substitutions=4 |
| 183.5s | `client_agent` | `agent.task_completed` | ok | rejected=None · task_id=001-add-second-provider |

### Invocation 3 — `open-real-pr` → **rejected**  ·  `operation_id=op_cbba0bceb7c3, op_5619dcabf55d`

| t | component | event | decision | what happened |
|---|---|---|---|---|
| 0.0s | `reverse-compiler` | `patch.parsed` | — | 8 files, 13 hunks · entities resolved: infra_internal_host, svc_booking_core, vendor_companyx, vendor_skyroute |
| 0.0s | `reverse-compiler` | `patch.entity_resolved` | — | `infra_internal_host` — exact round-trip |
| 0.0s | `reverse-compiler` | `patch.entity_resolved` | — | `svc_booking_core` — exact round-trip |
| 0.0s | `reverse-compiler` | `patch.entity_resolved` | — | `vendor_companyx` — exact round-trip |
| 0.0s | `reverse-compiler` | `patch.entity_resolved` | — | `vendor_skyroute` — **lossy** (multi-word display name — flagged for human review) |
| 0.1s | `client_agent` | `agent.real_pr_blocked` | **BLOCK** | **real diff does not apply** — `error: patch failed: .env.example:5` (+5 more) |
| 0.1s | `client_agent` | `agent.metrics` | — | outcome=rejected · wall_clock_s=0.151 · reason=real diff does not apply cleanly to the real repo |

### Invocation 4 — `open-real-pr` → **ok**  ·  `operation_id=op_186714d5f563, op_57ee7516536c`

| t | component | event | decision | what happened |
|---|---|---|---|---|
| 0.0s | `reverse-compiler` | `patch.parsed` | — | 8 files, 13 hunks · entities resolved: svc_booking_core, vendor_companyx, vendor_skyroute |
| 0.0s | `reverse-compiler` | `patch.entity_resolved` | — | `svc_booking_core` — exact round-trip |
| 0.0s | `reverse-compiler` | `patch.entity_resolved` | — | `vendor_companyx` — exact round-trip |
| 0.0s | `reverse-compiler` | `patch.entity_resolved` | — | `vendor_skyroute` — **lossy** (multi-word display name — flagged for human review) |
| 0.1s | `client_agent` | `agent.real_pr_opened` | — | branch `ghostc/real/001-add-companyx-integration` · commit `b7468a3f` · 8 files / 13 hunks |
| 0.1s | `orchestrator` | `approval.requested` | **PENDING** | gate `real_pr_review` on `ghostc/real/001-add-companyx-integration` — **awaiting a human** |
| 0.1s | `client_agent` | `agent.metrics` | — | outcome=ok · wall_clock_s=0.359 |

### Invocation 5 — `open-real-pr` → **ok**  ·  `operation_id=op_0da5f9f59d44, op_fb009e69af1a`

| t | component | event | decision | what happened |
|---|---|---|---|---|
| 0.0s | `reverse-compiler` | `patch.parsed` | — | 8 files, 13 hunks · entities resolved: svc_booking_core, vendor_companyx, vendor_skyroute |
| 0.0s | `reverse-compiler` | `patch.entity_resolved` | — | `svc_booking_core` — exact round-trip |
| 0.0s | `reverse-compiler` | `patch.entity_resolved` | — | `vendor_companyx` — exact round-trip |
| 0.0s | `reverse-compiler` | `patch.entity_resolved` | — | `vendor_skyroute` — **lossy** (multi-word display name — flagged for human review) |
| 0.1s | `client_agent` | `agent.real_pr_opened` | — | branch `ghostc/real/001-add-companyx-integration` · commit `4a9c3b4a` · 8 files / 13 hunks |
| 0.1s | `orchestrator` | `approval.requested` | **PENDING** | gate `real_pr_review` on `ghostc/real/001-add-companyx-integration` — **awaiting a human** |
| 0.1s | `client_agent` | `agent.metrics` | — | outcome=ok · wall_clock_s=0.303 |

### Invocation 6 — `open-real-pr` → **ok**  ·  `operation_id=op_5f4f91c6cd51, op_8f341fece1a8`

| t | component | event | decision | what happened |
|---|---|---|---|---|
| 0.0s | `reverse-compiler` | `patch.parsed` | — | 8 files, 13 hunks · entities resolved: svc_booking_core, vendor_companyx, vendor_skyroute |
| 0.0s | `reverse-compiler` | `patch.entity_resolved` | — | `svc_booking_core` — exact round-trip |
| 0.0s | `reverse-compiler` | `patch.entity_resolved` | — | `vendor_companyx` — exact round-trip |
| 0.0s | `reverse-compiler` | `patch.entity_resolved` | — | `vendor_skyroute` — **lossy** (multi-word display name — flagged for human review) |
| 0.1s | `client_agent` | `agent.real_pr_opened` | — | branch `ghostc/real/001-add-companyx-integration` · commit `5c5f9b4a` · 8 files / 13 hunks |
| 0.1s | `orchestrator` | `approval.requested` | **PENDING** | gate `real_pr_review` on `ghostc/real/001-add-companyx-integration` — **awaiting a human** |
| 0.1s | `client_agent` | `agent.metrics` | — | outcome=ok · wall_clock_s=0.356 |

### Invocation 7 — `open-real-pr` → **ok**  ·  `operation_id=op_c771d51fba3b, op_e99728335a8c`

| t | component | event | decision | what happened |
|---|---|---|---|---|
| 0.0s | `reverse-compiler` | `patch.parsed` | — | 8 files, 13 hunks · entities resolved: svc_booking_core, vendor_companyx, vendor_skyroute |
| 0.0s | `reverse-compiler` | `patch.entity_resolved` | — | `svc_booking_core` — exact round-trip |
| 0.0s | `reverse-compiler` | `patch.entity_resolved` | — | `vendor_companyx` — exact round-trip |
| 0.0s | `reverse-compiler` | `patch.entity_resolved` | — | `vendor_skyroute` — **lossy** (multi-word display name — flagged for human review) |
| 0.1s | `client_agent` | `agent.real_pr_opened` | — | branch `ghostc/real/001-add-companyx-integration` · commit `ac794067` · 8 files / 13 hunks |
| 0.1s | `orchestrator` | `approval.requested` | **PENDING** | gate `real_pr_review` on `ghostc/real/001-add-companyx-integration` — **awaiting a human** |
| 0.1s | `client_agent` | `agent.metrics` | — | outcome=ok · wall_clock_s=0.351 |

### Invocation 8 — `client-agent start` — sanitize the ticket and hand off  ·  `operation_id=op_e916876a4f12, op_b171640b31b7, op_94a2c246c2cb`

| t | component | event | decision | what happened |
|---|---|---|---|---|
| 0.0s | `client_agent` | `agent.task_started` | — | backend=auto · task_id=002-add-cargo-provider |
| 0.0s | `spec_compiler` | `spec.compiled` | — | 3 entities substituted: client_northwind→`client-a` ×1, svc_booking_core→`service-a` ×1, vendor_skyroute→`vendor-a` ×3 |
| 8.2s | `screen` | `screen.scanned` | **BLOCK** | ghost_task · 5 flagged / 11 scored · top=0.8119 · adjudicator=ran |
| 8.2s | `screen` | `screen.blocked` | **BLOCK** | **5 unscreened finding(s)** in the outbound ghost_task — strongest `llm + structural shape` @ 0.8119 (secret/restricted). Surfaces are hashed. |
| 8.2s | `client_agent` | `agent.metrics` | — | wall_clock_s=8.194 · llm_model=claude-opus-5 · substitutions=3 |
| 8.2s | `client_agent` | `agent.task_completed` | rejected | rejected=screen: 5 unscreened finding(s) in the outbound ghost_task; strongest: llm + structural shape @ 0.81 · task_id=002-add-cargo-provider |
| 24.5s | `spec_compiler` | `spec.compiled` | — | 4 entities substituted: client_northwind→`client-a` ×2, svc_booking_core→`service-a` ×2, vendor_companyx→`partner-a` ×17, vendor_skyroute→`vendor-a` ×6 |
| 24.6s | `screen` | `screen.scanned` | pass | /tmp/ghost-task.md · 0 flagged / 0 scored · top=0.0 · adjudicator=off |

## Reading the trajectory

1. **`spec.compiled` is a gate, not a formatting step.** The real ticket names the client, the internal service and two vendors. The sanitized `TASK.md` that reaches the external agent carries only aliases. If any entity could not be resolved the node raises and the run ends here — the task text never crosses half-sanitized.
2. **`agent.spec_handoff` is the boundary crossing.** Everything after it that touches ghost data is the other agent's work (trajectory 2).
4. **`patch.entity_resolved` carries a `lossy` flag.** A code token round-trips exactly; a multi-word display name may not, so it is flagged rather than guessed — the reverse compiler never invents a real value it is not sure of.

## The retry — a real fail-closed block

At `223.8s` the run **stopped** rather than producing a real-repo branch:

```
error: patch failed: .env.example:5
error: .env.example: patch does not apply
error: patch failed: src/config.js:19
error: src/config.js: patch does not apply
error: patch failed: src/server.js:3
error: src/server.js: patch does not apply
```

Reason recorded: `real diff does not apply`. The reverse-compiled diff was correct but its context lines no longer matched the real repo, which had moved on. The orchestrator did **not** force the patch, fuzz the context, or open a partial PR — `open-real-pr` exited non-zero and wrote a `rejected` metrics row.

The operator re-ran the command against the current base; the second attempt resolved the same three entities and opened the branch. **Both attempts are in the log** — the rejected one is evidence the gate is real, not decorative.

## The screen block — a class the compiler cannot see

A later run stopped for a different reason: not a *known* real value surviving substitution, but **5 value(s) nobody had ever configured**. `compile_spec` had nothing to say about them — it substitutes what `privacy.yaml` and the mapping name, and its own leak scan searches for those same spellings — so they reached `screen` untouched, one node before the only node that writes ghost-side.

| finding (hashed) | score | kind / level | evidence |
|---|---|---|---|
| `6dfab64a21e1…` | 0.8119 | secret/restricted | llm + structural shape |
| `395282f73a1f…` | 0.7635 | domain/confidential | llm + structural shape |
| `c9cd10149a2f…` | 0.747 | infra_identifier/confidential | llm + structural shape |
| `8de865c67166…` | 0.701 | person/restricted | llm + structural shape |
| `999c1dad5330…` | 0.57 | vendor/internal | llm |

By layer: 1× llm, 4× llm + structural shape. The `llm`-only rows are the ones that justify the adjudicator existing at all — the deterministic detector proposes an unconfigured entity only from a structural *anchor*, which is exactly what keeps OSS package names out of `discover`'s proposals and exactly what blinds it to a partner's name in an English sentence.

Note what is **not** in this table: the surfaces themselves. The audit log is hash-only by construction, so the record of a privacy failure is not itself a privacy failure. The operator reads the cleartext from the run's own stdout, inside the boundary.

## Human checkpoint

The run ends at `approval.requested` (`gate=real_pr_review`) with decision **pending**. The real-repo branch exists and is flagged `HUMAN REVIEW REQUIRED`; nothing merges without a person. The `lossy` entity flag is what that reviewer is asked to check first.

## Metrics rows for these runs

```json
{"command": "start", "consultancy_authors": ["Consultancy Dev"], "consultancy_commit": "6900249a373340ac4947e33714cd752c2eb04fac", "consultancy_commits": 1, "consultancy_pushed": true, "flow": "reduced", "ghost_branch": "ghostc/task/001-add-second-provider", "ghost_build": {"ok": true}, "ghost_pr": null, "ghost_tests": {"fail": 0, "ok": true, "pass": 7, "tests": 7}, "llm_model": "claude-opus-5", "llm_tokens": 0, "outcome": "ok", "real_pr": null, "rejected": null, "role": "client", "schema": 1, "substitutions": 4, "task_id": "001-add-second-provider", "ts": "2026-08-31T09:54:01.575038+00:00", "wall_clock_s": 183.518}
{"command": "open-real-pr", "flow": "reverse-pr", "ghost_branch": "ghostc/task/001-add-second-provider", "outcome": "rejected", "real_branch": "ghostc/real/001-add-companyx-integration", "reason": "real diff does not apply cleanly to the real repo", "role": "client", "schema": 1, "task_id": "001-add-second-provider", "ts": "2026-08-31T09:54:32.154740+00:00", "wall_clock_s": 0.151}
{"base": "main", "command": "open-real-pr", "entities_resolved": ["svc_booking_core", "vendor_companyx", "vendor_skyroute"], "fallbacks": [], "files": 8, "flow": "reverse-pr", "ghost_branch": "ghostc/task/001-add-second-provider", "ghost_handoff": "eea76b95aa5be785cc3ec1b19462be9c7a5c32d3", "hunks": 13, "lossy_entities": ["vendor_skyroute"], "outcome": "ok", "real_branch": "ghostc/real/001-add-companyx-integration", "real_commit": "b7468a3f28d9b589c195365653f9142ad1a9755e", "real_repo": "/Users/davide.arcinotti/learn/ghostc-demo/real", "role": "client", "schema": 1, "task_id": "001-add-second-provider", "ts": "2026-08-31T10:16:40.255189+00:00", "wall_clock_s": 0.359}
{"base": "main", "command": "open-real-pr", "entities_resolved": ["svc_booking_core", "vendor_companyx", "vendor_skyroute"], "fallbacks": [], "files": 8, "flow": "reverse-pr", "ghost_branch": "ghostc/task/001-add-second-provider", "ghost_handoff": "eea76b95aa5be785cc3ec1b19462be9c7a5c32d3", "hunks": 13, "lossy_entities": ["vendor_skyroute"], "outcome": "ok", "real_branch": "ghostc/real/001-add-companyx-integration", "real_commit": "4a9c3b4a220f0d547c64bee13b7eee4903f04210", "real_repo": "/Users/davide.arcinotti/learn/ghostc-demo/real", "role": "client", "schema": 1, "task_id": "001-add-second-provider", "ts": "2026-08-31T10:18:20.420485+00:00", "wall_clock_s": 0.303}
{"command": "run-task", "consistency": "consistent", "consistency_flags": [], "consultancy_commit": null, "consultancy_pushed": false, "entities_resolved": ["client_northwind", "svc_booking_core", "vendor_skyroute"], "files": 1, "flow": "full", "ghost_branch": "ghostc/task/task-aef9fac3", "ghost_pr": "1", "hunks": 1, "llm_model": "stub", "llm_tokens": 785, "lossy_entities": ["client_northwind", "vendor_skyroute"], "outcome": "ok", "real_diff_applies": true, "real_pr": "1", "rejected": null, "role": "client", "schema": 1, "substitutions": 3, "task_id": "task-aef9fac3", "ts": "2026-08-31T14:57:43.791655+00:00", "wall_clock_s": 0.843}
{"command": "run-task", "consistency": "consistent", "consistency_flags": [], "consultancy_commit": null, "consultancy_pushed": false, "entities_resolved": ["client_northwind", "svc_booking_core", "vendor_skyroute"], "files": 1, "flow": "full", "ghost_branch": "ghostc/task/task-aef9fac3", "ghost_pr": "1", "hunks": 1, "llm_model": "stub", "llm_tokens": 785, "lossy_entities": ["client_northwind", "vendor_skyroute"], "outcome": "ok", "real_diff_applies": true, "real_pr": "1", "rejected": null, "role": "client", "schema": 1, "substitutions": 3, "task_id": "task-aef9fac3", "ts": "2026-08-31T15:24:07.970250+00:00", "wall_clock_s": 1.043}
{"base": "main", "command": "open-real-pr", "entities_resolved": ["svc_booking_core", "vendor_companyx", "vendor_skyroute"], "fallbacks": [], "files": 8, "flow": "reverse-pr", "ghost_branch": "ghostc/task/001-add-second-provider", "ghost_handoff": "eea76b95aa5be785cc3ec1b19462be9c7a5c32d3", "hunks": 13, "lossy_entities": ["vendor_skyroute"], "outcome": "ok", "real_branch": "ghostc/real/001-add-companyx-integration", "real_commit": "5c5f9b4a877fb5586f97a7c8dd7590ffccf988a6", "real_repo": "/Users/davide.arcinotti/learn/ghostc-demo/real", "role": "client", "schema": 1, "task_id": "001-add-second-provider", "ts": "2026-08-31T15:32:41.219916+00:00", "wall_clock_s": 0.356}
{"base": "main", "command": "open-real-pr", "entities_resolved": ["svc_booking_core", "vendor_companyx", "vendor_skyroute"], "fallbacks": [], "files": 8, "flow": "reverse-pr", "ghost_branch": "ghostc/task/001-add-second-provider", "ghost_handoff": "eea76b95aa5be785cc3ec1b19462be9c7a5c32d3", "hunks": 13, "lossy_entities": ["vendor_skyroute"], "outcome": "ok", "real_branch": "ghostc/real/001-add-companyx-integration", "real_commit": "ac794067fdcee11451fc42899b94d32143776640", "real_repo": "/Users/davide.arcinotti/learn/ghostc-demo/real", "role": "client", "schema": 1, "task_id": "001-add-second-provider", "ts": "2026-08-31T15:33:45.292064+00:00", "wall_clock_s": 0.351}
{"command": "start", "consultancy_commit": null, "consultancy_pushed": false, "flow": "reduced", "ghost_branch": null, "ghost_pr": null, "llm_model": "claude-opus-5", "llm_tokens": 4244, "outcome": "rejected", "real_pr": null, "rejected": "screen: 5 unscreened finding(s) in the outbound ghost_task; strongest: llm + structural shape @ 0.81", "role": "client", "schema": 1, "screen_blocked": true, "screen_evidence": ["llm", "llm + structural shape"], "screen_findings": 5, "screen_llm": "ran", "screen_llm_dropped": 0, "screen_mode": "block", "screen_source": "ghost_task", "screen_suppressed": 0, "screen_top_score": 0.8119, "substitutions": 3, "task_id": "002-add-cargo-provider", "ts": "2026-09-01T16:07:04.322058+00:00", "wall_clock_s": 8.194}
```
