# Trajectory 2 — consultancy coding agent (`consultancy_agent`)

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
| **Role** | The external coding agent. Stands in for Codex / Copilot / a contractor's Claude. Treated as untrusted. |
| **Kind** | A real prompt loop — Claude, driven step by step against a tool surface until the acceptance criteria are met and tests and build are green (`consultancy_agent/agent.py`). |
| **Sees** | The **ghost** checkout and the sanitized `TASK.md`. Nothing else. |
| **Cannot see** | The real repo, the mapping store, `privacy.yaml`, the audit log, any credential. Enforced at import level: `consultancy_agent/` may not import `ghostc` or `client_agent` — `tests/test_boundary.py` fails the build if it does. |
| **Tools** | `list_files`, `read_file`, `write_file`, `run_tests`, `run_build`. |

## Agent instructions (verbatim, `consultancy_agent/agent.py::_SYSTEM`)

```text
You are an autonomous coding agent working inside a single git checkout.
Implement the change described in TASK.md **in full**. Work only inside the repo.

Method — follow in order:
  1. list_files on "." and the directories it names to learn the layout.
  2. Enumerate the acceptance criteria (AC1, AC2, ...) from TASK.md. You must
     satisfy EVERY one — a partial implementation is a failure.
  3. read_file the existing files the task points at (the sibling client / service
     / config / test it tells you to mirror) BEFORE writing, so new code matches
     the surrounding style and shape.
  4. write_file each change. Keep writes minimal and idiomatic.
  5. run_tests, then run_build. If either fails, read the output, fix the code,
     and re-run. Repeat until both pass.
  6. Only when every AC is done AND run_tests AND run_build have both passed on
     this checkout, reply {"done": true, "summary": "<what you changed, AC by AC>"}.

Each turn, reply with exactly ONE json object and nothing else — no prose, no
markdown fences:
  {"tool": "list_files", "args": {"dir": "."}}
  {"tool": "read_file", "args": {"path": "src/config.js"}}
  {"tool": "write_file", "args": {"path": "src/x.js", "content": "..."}}
  {"tool": "run_tests", "args": {}}
  {"tool": "run_build", "args": {}}
  {"done": true, "summary": "<what you changed>"}

You have a generous step budget. Do not stop early, do not leave an AC unfinished,
and do not claim done before the tests and build have actually passed.
```

## The verification feedback loop

This is the design choice that matters most in this agent. `done: true` is **not** taken at face value — it is only honoured once `run_tests` *and* `run_build` have each returned `exit=0` **since the last `write_file`**. Any write resets both flags. If the model claims done early it receives:

```text
[obs] you are NOT done — run_tests has not returned exit=0 since your last
write_file. Run run_tests and run_build; if either fails, read the output, fix
the code, and re-run. Re-check every acceptance criterion before saying done again.
```

Every turn also carries a status line the model cannot ignore:

```text
[status] step 7/N · tests_green=False · build_green=True · files_written=[...]
```

So the agent's next step is shaped by tool output, not by its own confidence. After a bounded number of premature `done` claims the partial result is accepted and **labelled** as unconfirmed rather than silently trusted.

## What actually happened


### Invocation 1 — `agent.consultancy_developed`  ·  `operation_id=op_77622b2fbfb5`

| t | component | event | decision | what happened |
|---|---|---|---|---|
| 0.0s | `consultancy_agent` | `agent.consultancy_developed` | — | branch `ghostc/task/001-add-second-provider` · commit `6900249a` · +1 commit(s) by Consultancy Dev |

## Per-step tool trace

_No step trace at `metrics/trajectories/<none>-consultancy.jsonl`._ Step-level capture (`bridge/trajectory.py`) records one line per tool call and per nudge; it is written by any `--consultancy-backend claude` run. The run above predates it, so only its aggregate is available. To produce the full trace:

```bash
client-agent start <spec> --consultancy-backend claude
scripts/make-trajectories.py   # picks the trace up automatically
```

## The real run

| | |
|---|---|
| Backend | `claude-opus-5` |
| Steps (tool calls) | **40** |
| Wall-clock | 182.158s |
| Files changed | 8 |
| Ghost tests | 7/7 passing, 0 failing → `ok=True` |
| Ghost build | `ok=True` |
| Outcome | `ok` |
| Branch | `ghostc/task/001-add-second-provider` |

Agent's own closing summary, as recorded:

> AC1: Added PARTNER_A_API_KEY and PARTNER_A_BASE_URL (fictional sandbox values) to .env.example and a `partnerA` block in src/config.js reading them from env with defaults. AC2: New src/integrations/pa

**40 steps to satisfy the acceptance criteria** — the loop did not converge on the first attempt. It read the sibling client it was told to mirror, wrote the integration, ran the tests, and iterated until the suite and the build were both green. That is the shape the verification gate forces.

## What it never saw

The agent produced a working implementation while the words *Northwind*, *SkyRoute*, *booking-core* and the real vendor name were absent from everything it was given. Its commits are authored as a separate git identity (`Consultancy Dev`), so `git log` on the ghost branch shows two distinct parties — the client's handoff commit and the external agent's work.

## Metrics rows for these runs

```json
{"backend": "claude-opus-5", "command": "start", "commit": "6900249a373340ac4947e33714cd752c2eb04fac", "files_changed": 8, "flow": "develop", "ghost_build": {"ok": true}, "ghost_tests": {"fail": 0, "ok": true, "pass": 7, "tests": 7}, "outcome": "ok", "role": "consultancy", "schema": 1, "steps": 40, "summary": "AC1: Added PARTNER_A_API_KEY and PARTNER_A_BASE_URL (fictional sandbox values) to .env.example and a `partnerA` block in src/config.js reading them from env with defaults. AC2: New src/integrations/pa", "task_branch": "ghostc/task/001-add-second-provider", "ts": "2026-08-31T09:54:01.199385+00:00", "wall_clock_s": 182.158}
```
