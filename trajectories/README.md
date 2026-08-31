# Agent trajectories

Hackathon deliverable 04. One trajectory per agent, each readable from the agent's instructions through to its final result — what it did, how its tools responded, the feedback that shaped the next step, and every retry and human checkpoint.

These are **generated from the run logs**, not written from memory:

```bash
scripts/make-trajectories.py --audit .ghostc/webapp-private/audit.jsonl \
    --metrics metrics/agent-runs.jsonl --out trajectories
```

| # | Agent | Kind | Trajectory |
|---|---|---|---|
| 1 | client orchestrator (`client_agent`) | LangGraph state machine + one LLM verdict | [`01-client-orchestrator.md`](01-client-orchestrator.md) |
| 2 | consultancy coding agent (`consultancy_agent`) | Claude prompt loop over a tool surface | [`02-consultancy-coding-agent.md`](02-consultancy-coding-agent.md) |

## Why there are only two

`ghostc discover`, the privacy compiler, the verifier and the reverse-patch compiler are **deterministic programs, not agents** — they are the tools the two agents call, and they are covered by the audit log and the test suite rather than by a trajectory. Presenting them as agents would overstate what they are.

## The two things worth looking at

- **A genuine fail-closed block and its retry** — trajectory 1. The reverse-compiled diff did not apply to a real repo that had moved on, so the run stopped and wrote a `rejected` metrics row instead of forcing the patch. Both attempts are in the log.
- **Verification shaping the next step** — trajectory 2. `done: true` is refused until `run_tests` and `run_build` have both returned `exit=0` since the last write, so the agent's own claim of completion is never what ends the run.

Generated files: `01-client-orchestrator.md`, `02-consultancy-coding-agent.md`.

