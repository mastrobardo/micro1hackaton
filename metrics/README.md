# Agent run metrics

`agent-runs.jsonl` — one JSON object per line, one line per agent run. Written by
`bridge/metrics.py::record_run`. **Generated, not committed** (`metrics/*.jsonl` is
gitignored); a dashboard / GitHub Action step consumes it as a build artifact, the
same way CI consumes a test report or a coverage/sonar report.

## Producers

| run | `role` | `command` | notable fields |
|---|---|---|---|
| `client-agent start <spec>` | `client` | `start` (reduced) / `run-task` (full) | `flow`, `outcome`, `substitutions`, `consultancy_commits`, `consultancy_authors`, `wall_clock_s` |
| `client-agent open-real-pr <spec>` | `client` | `open-real-pr` | `outcome`, `real_branch`, `entities_resolved`, `lossy_entities`, `files`, `hunks` |
| consultancy agent (post-receive hook) | `consultancy` | `start` | `task_branch`, `backend`, `steps`, `files_changed`, `outcome`, `wall_clock_s` |

## Common fields

- `schema` — bump on any incompatible change (currently `1`).
- `ts` — UTC ISO-8601 timestamp of the write.
- `role` — `client` | `consultancy`.
- `command` — the subcommand that produced the row.
- `task_id` — the ghost branch id (`ghostc/task/<task_id>`); boundary-neutral.
- `outcome` — `ok` | `rejected` (a fail-closed gate tripped; `rejected` carries the reason).
- `wall_clock_s` — run duration.

## Reading it

```bash
# last 5 runs, one line each
tail -5 metrics/agent-runs.jsonl | jq -c '{ts, role, command, task_id, outcome, wall_clock_s}'

# rejected runs only
jq -c 'select(.outcome == "rejected")' metrics/agent-runs.jsonl
```

Override the path with `--metrics-file <path>` or `$GHOSTC_METRICS_FILE`.
