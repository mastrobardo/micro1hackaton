# `consultancy_agent/` — external coding agent

Runs **outside** the trust boundary. **Must not import `ghostc` or `client_agent`**
— enforced by `tests/test_boundary.py`. `agent.py` may import `bridge` (env + LLM
client); `_hook.py` is stdlib only.

| in | out | rule |
|---|---|---|
| its **own persistent clone** of the ghost origin (`../ghostc-demo/ghost-consultancy`), a task branch with `TASK.md` at the root (NO mapping, NO real repo, NO client creds) | more commits on that branch — committed as its own git identity — pushed. **no PR** | isolation is **infrastructure** (its clone only reaches the ghost origin; a separate process never handed a mapping path or `CLIENT_*` key; the import boundary), not a runtime self-check — a real external agent does not audit its own sandbox |

**Trigger:** a `post-receive` hook on the bare ghost origin (`../ghostc-demo/ghost.git`,
installed by `client_agent.localgit.ensure_ghost_origin`). The client pushes
`ghostc/task/<id>`; the hook runs `consultancy-agent start --repo <consultancy-clone>
--branch <ref>` — no mapping / client-repo path on the command line. `GHOSTC_NO_HOOK=1`
stops the consultancy's own push-back from re-triggering the hook.

## Entrypoint

`consultancy-agent start --repo <consultancy-clone> --branch ghostc/task/<id> [--backend auto|claude|stub]`
(`cli.py` → `agent.run`). `git fetch origin` → `checkout -B <branch> origin/<branch>`
→ implement `TASK.md` → commit as **`Consultancy Dev <dev@consultancy.example>`**
(override `CONSULTANCY_GIT_NAME` / `CONSULTANCY_GIT_EMAIL`) → `git push origin <branch>`.
No PR (that path is the client's `run-task`).

- `agent.py` — `run()`:
  - `--backend claude` / `auto` with `CONSULTANCY_ANTHROPIC_API_KEY` (or bare
    `ANTHROPIC_API_KEY`) → a hand-rolled loop over the checkout: Claude emits one
    JSON action per turn (`list_files` / `read_file` / `write_file` / `run_tests` /
    `run_build`), `_MAX_STEPS` budget, transient-error backoff.
    `configure_langsmith(role="consultancy")` + `get_llm(..., role="consultancy")` +
    `@traceable("consultancy:agent")` → traces in the `ghostc-consultancy` LangSmith
    project, billed to the consultancy key.
  - `--backend stub` / no key → `_scripted_impl`: a deterministic `IMPL_NOTES.md`
    marker commit, so the graph tests + an offline demo run reproducibly.
- `_hook.py` — the `post-receive` runner (stdlib only). Writes the child's output to
  `<clone>/../<ref>.consultancy.log`.
- `sim.py` — in-process stand-in the **full** `run-task` graph uses (`run_consultancy`,
  opens a ghost PR via `LocalBareForge`). `open_pr=False` commits on the feature branch
  instead. The reduced flow no longer touches it.
