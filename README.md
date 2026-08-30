# Privacy Agent — privacy-safe bridge for external AI coding agents

> **micro1 Agentic Workflows Hackathon submission.**
> An agent workflow that lets external AI coding agents (Codex, Copilot, Claude) implement real
> tasks on a private codebase **without any sensitive information crossing the company trust
> boundary** — and proves it with a fair baseline and an evidence-linked changelog.

## Who has this problem

Consultancies and product teams working on **client-owned code**. They want to use external
coding agents but cannot expose client identity, commercial partners, internal service names,
private infrastructure, or secrets. Today they either don't use external agents on those repos
at all, or they hand-redact — which corrupts the code and still leaks.

## The bottleneck

Redaction is a dead end: string-replacing `AcmeAir` with `REDACTED` breaks identifiers and
imports, strips the semantics an agent needs to work, and misses the same entity spelled three
other ways. There is no repeatable, auditable method that keeps the repo **useful** while
keeping it **safe**.

## What this builds

A pipeline that compiles a real repo into a semantically-faithful **ghost repo** (`Stripe -> PaymentProviderA`,
not `Stripe -> REDACTED`), lets an ordinary external agent work on the ghost, translates the
resulting ghost PR back into a real PR, and verifies both privacy and task-consistency — with a
structured audit log behind every step.

```
task text
   -> Entity Discovery agent      (proposes entities + sensitivity; human approves `restricted`)
   -> Privacy Compiler            (tree-sitter JS/TS + HCL; stable aliases; -> ghost repo + spec)
   -> Verification agent          (leak scan + build gate; fail closed)
   -> External coding agent       (ghost only: no real repo, no mapping, no credentials)
   -> Reverse Patch Compiler      (ghost diff -> real diff; rejects ambiguous mappings)
   -> PR-consistency agent        (real diff matches the task? -> human review)
   -> real PR
```

See `ARCHITECTURE.md` for component contracts, `THREAT_MODEL.md` for the trust boundary and
known limitations, `TODO.md` for the full long-term roadmap, and `PROGRESS.md` for current status.

## Primary metric

**Leak count** — occurrences of ground-truth real sensitive values present in what is exposed to
the external agent (ghost repo + ghost spec). Target: **0**.
Secondary: **task pass rate** (reverse-compiled real PR applies, `yarn lint` + `yarn test` +
acceptance check pass). Tertiary: human approvals, wall-clock, token cost.

## Baseline

Keyword `sed` redaction to `REDACTED` + the same external agent + the same 10 tasks. This is the
"simple script" / "manual process people use today" baseline. `CHANGELOG.md` records each
iteration from that baseline to the final workflow, with evidence.

## Reproduction (fills in as subcommands land)

```bash
# 1. base fixture (MIT, offline — no external accounts)
git clone --depth 1 https://github.com/hagopj13/node-express-boilerplate.git ../node-express-boilerplate

# 2. apply the synthetic sensitive-entity layer (documented, all fictional — ground rule 07)
./fixtures/apply.sh

# 3. env
python -m venv .venv && . .venv/bin/activate && pip install -e .

# 4. pipeline  (all 7 subcommands implemented)
ghostc discover --repo workspace/real --config privacy.yaml   # score + propose sensitive entities
ghostc compile  --repo workspace/real --config privacy.yaml --out workspace/ghost
ghostc verify   --ghost workspace/ghost --mapping workspace/private/mapping.json
ghostc apply-patch --ghost-diff <ghost-pr.diff> --mapping workspace/private/mapping.json --real workspace/real --apply
ghostc baseline --repo workspace/real --config privacy.yaml   # fair comparator (keyword redaction)
ghostc eval     --real workspace/real --config privacy.yaml   # -> workspace/eval-report.{md,csv}
```

### Runnable demo — real + ghost in two browser windows

```bash
./scripts/demo-webapp.sh    # stage real -> compile ghost -> verify -> npm test both -> serve
# real  http://localhost:3000  → Northwind Airlines / SkyRoute Data Ltd / booking-core
# ghost http://localhost:3001  → Client A / Vendor A / service-a          (same UI, same tests)
```

A zero-dependency Node app (`fixtures/webapp/`) staged **outside** this repo at
`../ghostc-demo/{real,ghost}`. Same endpoints, same passing tests, sensitive names aliased.

**Current result** (`ghostc eval` on the fixture): keyword-redaction baseline leaves **28**
residual real-entity occurrences in what an external agent would see; `ghostc compile` leaves
**0**, and the ghost PR round-trips back to a real branch through `ghostc apply-patch`.
`ghostc discover` re-finds all 13 configured entities from code alone and proposes the two
unconfigured ones seeded in `adversary.js` (Meridian, Contoso) with no OSS-library false
positives. Full evidence trail: `CHANGELOG.md` + `workspace/eval-report.md`.

## Agent workflow (`ghostc-agent`, `ghostc-mcp`)

The LangGraph client orchestrator lives in `client_agent/` (`ghostc-agent run-task`); the
external coding agent in `consultancy_agent/` (may not import `ghostc` — enforced by
`tests/test_boundary.py`); shared git/LLM plumbing in `bridge/`. Needs the extras:

```bash
pip install -e ".[agents,mcp]"
cp .env.example .env                                  # ANTHROPIC_API_KEY, LANGSMITH_*, backend/model
ghostc-agent run-task --task task.md --backend stub   # full loop -> a real-repo PR
ghostc-agent print-graph                              # regenerate client_agent/graph.md
```

`.env` (gitignored, template `.env.example`) is the one config source — loaded by
`bridge.env.load_env`, never overriding a var already set in the shell / CI / `docker run -e`.
With no Anthropic key the workflow uses the deterministic stub backend. Point elsewhere with
`GHOSTC_ENV_FILE`.

**Per-agent credentials.** The two agents — `client` (orchestrator) and `consultancy`
(external coder) — resolve each secret role-first then shared:
`CLIENT_ANTHROPIC_API_KEY` / `CONSULTANCY_ANTHROPIC_API_KEY` → `ANTHROPIC_API_KEY`, same for
`*_LANGSMITH_API_KEY` / `*_LANGSMITH_PROJECT` / `*_LANGSMITH_ENDPOINT`. One shared key works;
split them for separate billing, LangSmith trace projects (`ghostc-client` /
`ghostc-consultancy`), and blast radius. Phase E's `docker compose` hands each service only
its own subset.

**Monitoring.** Set `LANGSMITH_API_KEY` (+ `LANGSMITH_TRACING=true`) and every run is traced
— LangGraph nodes, the wrapped Anthropic calls, and explicit `@traceable` spans
(`bridge.trace`) on `run_task` / each node / `*.complete` / the consultancy entry. If your
key is in LangSmith's **EU** tenant, also set
`LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com` (a US default + an EU key → `403`).

### Poking the MCP server

`ghostc-mcp` exposes `compile_spec` / `discover` / `verify` / `apply_patch` as MCP tools.
Test it interactively with the MCP Inspector (needs Node; first run downloads it):

```bash
npx @modelcontextprotocol/inspector ghostc-mcp
#   or:  npx @modelcontextprotocol/inspector python -m ghostc.mcp_server
```

Run it from the repo root — the tools take filesystem paths resolved against the server's CWD.

## What pre-existed vs. what we added (ground rule 02)

| Pre-existing | Added for the competition |
|---|---|
| `hagopj13/node-express-boilerplate` (the fixture, unmodified upstream) | Everything in this repo: `ghostc/` compiler + agents, `privacy.yaml`, `schemas/`, `fixtures/` synthetic entity layer, eval harness, all docs |

## License / data

Fixture is MIT. All injected client / vendor / infrastructure entities are **fictional**
(`fixtures/`). No real credentials or private data are in this repo (ground rule 08).
