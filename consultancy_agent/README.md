# `consultancy_agent/` — external coding agent

Runs **outside** the trust boundary. **Must not import `ghostc` or
`client_agent`** — enforced by `tests/test_boundary.py`. May import `bridge`
(git forge + LLM client only).

| in | out | rule |
|---|---|---|
| ghost repo checkout + `TASK.md` (NO mapping, NO real repo, NO creds) | commits on the ghost impl branch + a ghost PR | `assert_boundary_clean()` refuses to start if a mapping-shaped file or a real-repo marker is reachable from the work dir |

- `sim.py` — deterministic stand-in used by the Phase B graph (`run_consultancy`).
- `agent.py` — Phase C landing pad: a Claude tool-loop (`list_files` / `read_file`
  / `write_file` / `run_tests`) over the checkout via `bridge.llm`, then commit +
  ghost PR via `bridge.forge`. Currently `NotImplementedError` + the boundary guard.
