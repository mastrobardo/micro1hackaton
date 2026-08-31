# Getting Started — reproduction guide

Written for someone starting from a **clean environment**. Every command is copy-paste from
the repo root. The whole thing runs **offline and deterministically** — no external accounts
are needed for the baseline, the solution, or the evaluation. One optional section uses the
Anthropic API to run the coding agent for real.

- **What you reproduce:** the primary metric (leak count **28 → 0**), the `ghostc discover`
  recall (13/13 configured entities + 2 unconfigured proposals), and a full agent round-trip
  (real ticket → sanitized ghost task → external agent on the ghost → reverse PR onto the real
  repo) — i.e. a third-party model did the work with **zero real entities disclosed**.
- **Evidence trail:** `CHANGELOG.md` (the Improvement Changelog) and
  `workspace/eval-report.md` (generated, derived from the audit log).

---

## 0. Prerequisites

| Tool | Version used | Notes |
|---|---|---|
| Python | 3.14 (min **3.10**) | `python3 --version` |
| Node.js | 22 (min **20**) | only for the runnable webapp demo + the MCP server; the core pipeline is pure Python |
| git | any recent | |
| OS | macOS / Linux | scripts are `bash` |
| Disk | ~250 MB | includes the base fixture checkout |
| Network | once, to clone the MIT base fixture | everything after that is local |

No API keys are required for sections 1–5. Section 6 (real coding agent) needs an
`ANTHROPIC_API_KEY`; a fully offline stub path is provided.

---

## 1. Set up (clean environment)

```bash
git clone <this-repo> ghostc && cd ghostc

# base fixture: MIT, unmodified upstream (ground rule 02)
git clone --depth 1 https://github.com/hagopj13/node-express-boilerplate.git ../node-express-boilerplate

python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

ghostc --version          # -> ghostc, version 0.1.0
```

Optional extras (not needed for the main result):

```bash
pip install -e ".[dev,agents]"     # the LangGraph agent workflow (section 6)
pip install -e ".[dev,mcp]"        # the ghostc-mcp server
pip install -e ".[dev,semantic]"   # real sentence-embeddings for one detection signal (~2 GB torch)
```

---

## 2. Reproducibility check — the test suite

```bash
pytest -q
```

Expected: **268 passed, 1 skipped** in ~45 s. Fixture-dependent tests skip cleanly if
`workspace/real/` is absent, so this is green on a fresh checkout; it goes fully green after
section 3.

---

## 3. Build the fixture

```bash
./fixtures/apply.sh        # -> workspace/real/  (base repo + synthetic sensitive-entity layer)
```

The synthetic layer is entirely fictional (client *Northwind Airlines*, vendor *SkyRoute Data
Ltd*, service *booking-core*, person *Priya Nair*, infra hosts/IPs, plus an adversarial
`src/integrations/adversary.js` with unconfigured *Meridian* / *Contoso*). See
`fixtures/README.md`. Ground truth: **67** configured-spelling occurrences across 13 entities
(`tests/expected/groundtruth.json`).

---

## 4. Baseline — keyword redaction (the "simple script people use today")

```bash
ghostc baseline --repo workspace/real --config privacy.yaml
#  -> workspace/baseline-ghost/  + workspace/baseline-spec.md
```

Case-sensitive global string replace of every configured spelling → its alias (or `REDACTED`).
No AST, no casing engine, no mapping store, not reversible. It corrupts identifiers
(`initDatadog` → `initvendor-c`) and leaks every casing variant it was not literally given
(`SKYROUTE_API_KEY`, `BOOKING_CORE_URL`, …). This is the fair comparator.

---

## 5. Solution — the privacy compiler pipeline

```bash
# 5a. discover — score + propose sensitive entities from code alone
ghostc discover --repo workspace/real --config privacy.yaml
#  Expected: re-finds all 13 configured entities; proposes the 2 unconfigured ones
#  (Meridian ~0.99, Contoso ~0.83) with 0 OSS-library false positives.

# 5b. compile — real repo -> privacy-safe ghost repo
ghostc compile --repo workspace/real --config privacy.yaml
#  -> workspace/ghost/ (fresh git init) + workspace/ghost-spec.md   [these cross the boundary]
#  -> workspace/private/{mapping.json,audit.jsonl}                  [never cross]

# 5c. verify — fail-closed leak + mapping + build gate
ghostc verify --ghost workspace/ghost --mapping workspace/private/mapping.json
#  Expected: PASS (exit 0). Any real value in the ghost -> BLOCK (exit 1).

# 5d. eval — count residual real-entity occurrences in baseline vs compile
ghostc eval --real workspace/real --config privacy.yaml
#  -> workspace/eval-report.{md,csv}
#  Expected (casing-aware residual): baseline 28, compile 0.
```

**Round-trip a ghost PR back to the real repo** (`ghost diff → real diff`):

```bash
ghostc apply-patch \
  --ghost-diff <some-ghost-pr.diff> \
  --mapping workspace/private/mapping.json \
  --real workspace/real --apply
#  Fail-closed: unmapped alias-shaped token, a real value in the ghost diff,
#  mapping-version mismatch, or ambiguous resolution -> Rejection, exit 1, nothing written.
```

**One-shot:** `./scripts/e2e.sh` runs sections 4–5 (happy paths **and** the fail-closed
cases) and checks each result. `SKIP_EVAL=1` skips the slow step.

### Runnable demo — real vs ghost, side by side

```bash
./scripts/demo-webapp.sh
#  real   http://localhost:3000   Northwind Airlines / SkyRoute Data Ltd / booking-core
#  ghost  http://localhost:3001   Client A / Vendor A / service-a       (same UI, same tests)
#  DEMO_NO_SERVE=1 ./scripts/demo-webapp.sh   # build + compile + health diff, no servers
```

A zero-dependency Node app (`fixtures/webapp/`) staged **outside** this repo at
`../ghostc-demo/{real,ghost}`. Same endpoints, same passing tests, sensitive names aliased.

---

## 6. The agent workflow (optional — needs the `[agents]` extra)

The full loop: a real ticket → a sanitized ghost task on a git branch → an external coding
agent implements it on the **ghost** repo only → the client reverse-compiles that work onto a
**real-repo** branch for human review.

```bash
pip install -e ".[agents]"        # console scripts: client-agent, consultancy-agent
cp .env.example .env
```

### 6a. Offline / deterministic path — no API key

```bash
ghostc-agent run-task --task specs/001-add-companyx-integration.md --backend stub
#  full pipeline with the deterministic stub consultancy -> a real-repo PR record.
```

Uses local bare git repos and a scripted consultancy. `$0`, a few seconds, reproducible
run-to-run. This is the path judges can run from a clean environment.

### 6b. Real coding agent — needs `ANTHROPIC_API_KEY`

`.env` keys: `ANTHROPIC_API_KEY` (or `CLIENT_` / `CONSULTANCY_` variants),
`LANGSMITH_API_KEY` for tracing (+ `LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com`
**if your key is in LangSmith's EU tenant** — a US default + an EU key is a `403`).

```bash
# stage the runnable fixture first (real + ghost outside the repo)
./fixtures/webapp/apply.sh
ghostc compile --repo ../ghostc-demo/real --config fixtures/webapp/privacy.webapp.yaml \
  --out ../ghostc-demo/ghost --spec ../ghostc-demo/ghost-spec.md \
  --mapping .ghostc/webapp-private/mapping.json --audit .ghostc/webapp-private/audit.jsonl \
  --candidates .ghostc/webapp-private/candidates.jsonl

# 1) real ticket -> sanitized TASK.md on ghostc/task/<id> -> post-receive hook ->
#    consultancy (real Claude) implements on the ghost branch and pushes back
client-agent start 001-add-companyx-integration --consultancy-backend claude

# 2) the "webhook": reverse-compile the consultancy's ghost work onto the real repo
client-agent open-real-pr 001-add-companyx-integration

# inspect
git -C ../ghostc-demo/ghost log --stat ghostc/task/001-add-second-provider   # two git identities
git -C ../ghostc-demo/real  log --stat ghostc/real/001-add-companyx-integration
cat metrics/agent-runs.jsonl                                                  # one row per agent run
```

Expected on a good run: ghost `TASK.md` carries **no real names**; the consultancy produces a
working implementation (**ghost `npm test` + build green**); the reverse branch on the real
repo restores the real names, is **leak-scan clean**, and **real `npm test` + build stay
green**.

Clean slate between runs:

```bash
rm -rf ../ghostc-demo/ghost.git ../ghostc-demo/ghost-consultancy .ghostc
git -C ../ghostc-demo/ghost branch -D ghostc/task/001-add-second-provider
```

---

## 7. CI — the workflow as opened pull requests

`.github/workflows/agent-workflow.yml` runs the whole thing in GitHub Actions so a
reviewer inspects **normal forge objects**, not a local run. Two jobs:

- **`checks`** — deterministic, offline, no secrets: `ghostc compile` / `verify` /
  `eval` + `pytest`, then `scripts/ci/check_leak_gate.py` **fails the job on a
  leak-count regression** (compile residual must stay `0` and beat the baseline).
  The eval report + `metrics/agent-runs.jsonl` are uploaded as build artifacts.
- **`roundtrip`** — runs the verified reduced flow (`client-agent start` →
  `open-real-pr`) with the deterministic **stub** consultancy by default, then
  `scripts/ci/publish-prs.sh` pushes the two branches and opens/updates:
  - **ghost PR** on `github.com/mastrobardo/ghostc-demo-ghost` — the sanitized
    `TASK.md` + the consultancy's implementation, **no real names**;
  - **real PR** on `github.com/mastrobardo/ghostc-demo-real` — the same work
    reverse-compiled, real names restored, flagged **HUMAN REVIEW REQUIRED**.

  A manual **Run workflow** (`workflow_dispatch`) can set `consultancy_backend:
  claude` for a live agent run (needs the `ANTHROPIC_API_KEY` secret).

### One-time setup

```bash
# `gh` must be authed as (or GH_TOKEN set for) the repo owner
GH_OWNER=mastrobardo scripts/ci/init-demo-repos.sh   # create + seed the two public demo repos
```

Then add repo secrets (**Settings → Secrets and variables → Actions**):

| Secret | Needed for | Notes |
|---|---|---|
| `GH_PAT` | `roundtrip` — push branches + open PRs on the demo repos | a `mastrobardo` PAT with `repo` scope |
| `ANTHROPIC_API_KEY` | only a `consultancy_backend: claude` dispatch | omit for the deterministic path |

### Dry-run it locally

```bash
scripts/ci/run-local.sh                         # stub consultancy, opens the two PRs
CONSULTANCY_BACKEND=claude scripts/ci/run-local.sh
```

---

## 8. Human review board (`ghostc-review`)

The compiler's `restricted`-entity gate and `discover`'s proposals are approved by
a person. Today the deterministic path reads that decision from a **file** —
`decisions.jsonl` — so the ghost reproduces without any UI:

```bash
# reproduce the reviewed ghost — no Streamlit needed
ghostc compile --repo workspace/real --config privacy.yaml \
  --decisions fixtures/decisions.example.jsonl
#  the seeded example accepts the laundered vendor *Meridian* (-> vendor-e) and
#  ignores the weaker *Contoso* signal; `discover --decisions` shows the same log
#  as a scorer-vs-human agreement stat.

ghostc discover --repo workspace/real --config privacy.yaml \
  --decisions fixtures/decisions.example.jsonl
```

`decisions.jsonl` is **append-only** (latest record per entity wins, history kept)
and boundary-internal. `ghostc compile --decisions <path>` reads:
- **restricted clearances** — a `restricted` entity whose latest decision is
  `accept` + `approved_by` stops blocking the run;
- **accepted proposals** — an accepted unconfigured surface is compiled as its own
  alias (`source: human`).
No `--decisions` → exactly today's behaviour.

The UI that *writes* that file (optional `[review]` extra):

```bash
pip install -e ".[review]"
ghostc-review -- --candidates workspace/private/candidates.jsonl \
                 --decisions review/decisions.jsonl --config privacy.yaml
```

- **Review** tab — the `candidates.jsonl` queue; per proposal accept / ignore /
  escalate, with the implied `privacy.yaml` delta shown live.
- **Process data** tab — read-only dashboard: `metrics/agent-runs.jsonl`,
  `eval-report.csv`, audit-event counts, and the scorer-vs-human agreement stat.
  *The process generates the data that improves the process.*

---

## Runtime & cost

| Step | Runtime | Cost |
|---|---|---|
| `pip install -e ".[dev]"` | ~30 s | free |
| `pytest -q` | ~45 s | free |
| `ghostc baseline` / `compile` / `verify` / `discover` / `eval` | seconds each | free |
| `./scripts/e2e.sh` (with eval) | ~1–2 min | free |
| `ghostc-agent run-task --backend stub` | ~5 s | free |
| `client-agent start --consultancy-backend claude` | ~3 min | ≈ **$0.50–2** (Claude Opus, ~1 real agent run; approximate — varies with the model's step count) |
| `client-agent open-real-pr` | seconds | free (deterministic reverse-compile) |
| `scripts/ci/run-local.sh` (stub) | ~15 s + push | free |
| CI `checks` job | ~2 min | free |
| `ghostc compile --decisions …` | seconds | free |
| `ghostc-review` (Streamlit) | interactive | free |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `base repo not found at ../node-express-boilerplate` | run the `git clone` in step 1 |
| many `pytest` skips | expected before `./fixtures/apply.sh`; node-gated tests also skip without Node |
| `the agent workflow needs the [agents] extra` | `pip install -e ".[agents]"` |
| `the review board needs the [review] extra` | `pip install -e ".[review]"` (only the UI needs it; `--decisions` does not) |
| LangSmith `403` | your key is EU-tenant — set `LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com` |
| `open-real-pr` says `NotReady` | the ghost task branch has no impl on top of `TASK.md` — run `client-agent start <spec>` first (the stub backend now writes a small real file, so the offline reverse works) |
| CI `roundtrip` job: `GH_PAT secret is required` | add the `GH_PAT` repo secret, or run only `checks` (the deterministic job) |

---

## Where to look next

- **`OVERVIEW.md`** — what this is and who it's for, in one page.
- **`CHANGELOG.md`** — the Improvement Changelog: baseline → final, each step with evidence.
- **`ARCHITECTURE.md`** — component contracts, the trust boundary, and how a production
  CI/CD / issue-tracker integration would differ from this POC.
- **`cli.md`** — the full command reference with expected output for every subcommand.
- **`THREAT_MODEL.md`** — the boundary and known limitations.
