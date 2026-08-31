# `workspace/` is deprecated — do not use it for new work

User directive (2026-08-31, session 4): **the in-repo `workspace/` folder should not be
used anymore.** New pipeline / agent-workflow output must land elsewhere.

## Status

- **Not yet migrated.** `workspace/…` is still the default in `ghostc/cli.py`
  (`compile` / `discover` / `verify` / `baseline` / `eval` / `compile-spec` `--out` /
  `--mapping` / `--audit` / `--candidates`), `client_agent/cli.py` + `client_agent/graph.py`
  (`--workspace`, `--mapping`, `--audit`), `fixtures/apply.sh` (`workspace/real`),
  `scripts/*.sh`, and docs (`README.md`, `ARCHITECTURE.md`, `THREAT_MODEL.md`, `cli.md`) +
  many tests. A full migration is a dedicated task — get the target location from the user
  first.
- **Split to keep in mind when migrating:**
  - *Throwaway plumbing* (agent git remotes, scratch, consultancy work dirs) — no secrets,
    can go anywhere gitignored, e.g. `.ghostc/agent/`.
  - *Boundary-internal artifacts* (`mapping.json` = real values, `audit.jsonl`,
    `candidates.jsonl`) — **must not** sit under `../ghostc-demo/` next to the ghost tree
    (THREAT_MODEL: the mapping store must not be one `ls` from the ghost). Needs its own
    gitignored location, still separate from anything that crosses.
  - *Real/ghost checkouts* already live outside the repo at `$GHOSTC_DEMO_ROOT`
    (default `../ghostc-demo/{real,ghost}`) — see [[demoable-fixture]].

## Applied so far (session 4)

- **Reduced flow (`client-agent start`) uses NO workspace at all.** It operates on the real
  demo repos under `$GHOSTC_DEMO_ROOT` (`../ghostc-demo/`): `ghost/` gets a bare origin
  `ghost.git` + a `post-receive` hook, the consultancy gets its own clone `ghost-consultancy/`.
  Branches are real branches on real repos — `git -C ../ghostc-demo/ghost log ghostc/task/<id>`.
  The only in-repo state is `.ghostc/scratch/<id>.TASK.md` (the sanitized spec) +
  `.ghostc/webapp-private/{mapping,audit}` — gitignored, no git.
- The **full** pipeline (`ghostc-agent run-task`, ghost PR → reverse-patch → real PR) still
  uses `.ghostc/agent` for its synthesized `LocalBareForge`. Migrating it to the same
  real-repo model is a follow-up.
- `LocalBareForge.__init__` resolves its root to an absolute path.

Related: [[demoable-fixture]], [[agent-harness]].
