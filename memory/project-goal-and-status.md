---
name: project-goal-and-status
description: What this project is, how it's judged, and where to find live status
metadata:
  type: project
---

## Goal

`learn/hackaton/` — a **micro1 Agentic Workflows Hackathon** entry. Build an agent workflow that
lets external AI coding agents (Codex, Copilot, Claude) implement real tasks on a private
codebase **without any sensitive information crossing the company trust boundary**: compile the
real repo into a semantically-faithful **ghost repo** (`Stripe -> PaymentProviderA`, not
`-> REDACTED`), let an ordinary external agent work on the ghost, reverse-compile the ghost PR
into a real PR, and verify both privacy and task-consistency — with a structured audit log
behind every step. Full long-term vision: `TODO.md` (16 phases). Hackathon build = a thin
vertical slice of it.

## How it's judged (keep design decisions aligned to this)

Score /100: Problem & User Value 15 · **Agent Solution & Engineering 30** · End-to-End Quality
20 · **Measured Improvement 15** · Reproducibility 15 · Hot Take 5. The judged artifact is an
**agent workflow whose design choices measurably beat a fair baseline**, plus a changelog that
proves which choice caused which gain. "Monitoring and improving the process is paramount" — the
audit log doubles as the measurement instrument.

Baseline = keyword `sed` redaction + the same external agent + the same 10 eval cases.
Primary metric = **leak count** (real sensitive values exposed to the external agent), target 0.
Secondary = task pass rate.

## Deliverables

1. Solution code + **Improvement Changelog** (`CHANGELOG.md`: baseline -> each iteration -> final, every row linked to evidence)
2. Reproduction guide (clean env, exact commands, versions, runtime, cost)
3. Solution video <= 5 min
4. Agent trajectories for every agent used

## Binding ground rules

Sandbox/simulation + human approval before consequential actions · qualified human reviewer
where people are affected · **public or synthetic data only** (fixture is MIT + a fictional
entity layer) · no credentials in the submission · state clearly what pre-existed vs. what we
added.

## Where the live status is

- **`PROGRESS.md`** — snapshot, decision log, workflow diagram, metrics table, eval cases. Read first.
- **`SESSION_TODO.md`** — the immediate next action + open questions awaiting the user. Read second.

Do not restate volatile status here — those two files are the single source of truth.
Related: [[hackathon-scope-and-fixture]], [[privacy-levels-model]], [[testing-approach]], [[working-agreements]].
