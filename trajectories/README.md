# Agent trajectories

Hackathon deliverable 04. One trajectory per agent, each readable from the agent's instructions through to its final result — what it did, how its tools responded, the feedback that shaped the next step, and every retry and human checkpoint.

These are **generated from the run logs**, not written from memory:

```bash
scripts/make-trajectories.py --audit .ghostc/webapp-private/audit.jsonl \
    --metrics metrics/agent-runs.jsonl --out trajectories
```

| # | Agent | Kind | Trajectory |
|---|---|---|---|
| 1 | client orchestrator (`client_agent`) | LangGraph state machine + two advisory LLM calls (screen adjudicator, consistency verdict) | [`01-client-orchestrator.md`](01-client-orchestrator.md) |
| 2 | consultancy coding agent (`consultancy_agent`) | Claude prompt loop over a tool surface | [`02-consultancy-coding-agent.md`](02-consultancy-coding-agent.md) |

## Why there are only two

`ghostc discover`, the privacy compiler, the verifier, the reverse-patch compiler and the outbound screen are **deterministic programs, not agents** — they are the tools the two agents call, and they are covered by the audit log and the test suite rather than by a trajectory. Presenting them as agents would overstate what they are.

The screen is the closest call, because it *does* make an LLM call (`client_agent/screen_llm.py`). It stays a tool rather than a third agent because the model has no autonomy in it: one prompt, no loop, no tools of its own, and its output is re-anchored and score-capped before a deterministic rule decides. It appears in trajectory 1 as two audit events, which is exactly its weight.

## The things worth looking at

- **Two fail-closed blocks, for two different reasons** — trajectory 1. `screen` stopped a run over five values *nobody had ever configured* (the class the closed-world compiler cannot see), and the recorded findings are hashes, not surfaces.
- **A genuine fail-closed block and its retry** — trajectory 1. The reverse-compiled diff did not apply to a real repo that had moved on, so the run stopped and wrote a `rejected` metrics row instead of forcing the patch. Both attempts are in the log.
- **Verification shaping the next step** — trajectory 2. `done: true` is refused until `run_tests` and `run_build` have both returned `exit=0` since the last write, so the agent's own claim of completion is never what ends the run.

Generated files: `01-client-orchestrator.md`, `02-consultancy-coding-agent.md`.

