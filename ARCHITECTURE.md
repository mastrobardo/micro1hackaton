# Architecture

Scope: the hackathon slice. Full system is in `TODO.md`.

## This is a reproducibility-first POC

The threat being addressed is **unintentional disclosure** — the hand-redaction that misses a
casing variant, the agent that quotes a client name in a comment or PR body, a leaked env-var
name — not a motivated adversary doing structural correlation (see `THREAT_MODEL.md` for where
that line sits). Reproducibility is how that claim is *proven*: a second person, from a clean
checkout, runs the baseline, the solution, and the evaluation and reaches the same numbers —
leak count 0 — offline, deterministically, with no accounts to create. Several components are
therefore deliberately *simulated* rather than integrated:

| Concern | In this POC | Why |
|---|---|---|
| Git forge (PRs, branches, webhooks) | **local bare git repos** (`bridge.forge.LocalBareForge`) + a `post-receive` hook; a "PR" is a JSON record + a pushed ref | no GitHub/GitLab account, token, or network needed; the loop is byte-for-byte repeatable |
| Issue tracker | **spec `.md` files** in `specs/` with a `task-id:` header | judges read the exact input; no Jira/Linear instance to stand up |
| External coding agent | real Claude **or** a deterministic `--backend stub` | `pytest` and the eval numbers must not move run-to-run on model sampling |
| CI runner | shell scripts (`scripts/e2e.sh`, `scripts/demo-webapp.sh`) | run anywhere `bash` + Python exist |
| Human approval gate | a **flagged branch** + the consistency-agent verdict in the run output | keeps the consequential action (merge) behind a person without a review UI |

The pipeline logic — the compiler, the leak scan, the reverse-compile, the audit log, the
import boundary — is **not** simulated. Only the systems it would plug into are. The section
[**Where a production integration differs**](#where-a-production-integration-differs) below
maps each simulation to its real form.

## Trust boundary

```
                 COMPANY TRUST BOUNDARY
──────────────────────────────────────────────────────
 real repo · task text · mapping store · audit log
 privacy.yaml · entity-discovery + verification agents
──────────────────── PRIVACY BOUNDARY ────────────────
 EXTERNAL AI
 ghost repo · ghost spec · ghost PR
──────────────────────────────────────────────────────
```

The external coding agent receives **only** `workspace/ghost/` + `workspace/ghost-spec.md`.
It never receives the real repo, the mapping, or any credential.

## Components

| Component | Kind | Input | Output | Contract |
|---|---|---|---|---|
| **Entity Discovery agent** (`ghostc discover`) | deterministic candidate scoring — noisy-OR over lexical / import / declared-alias / `rapidfuzz` / structural-shape / decode / reference-graph-taint / semantic signals | real repo, `privacy.yaml` (`detection:` block) | ranked candidates (`surface`, `score` ∈ [0,1], `signals`, `auto`/`review`/`ignore`, occurrences) + `workspace/private/candidates.jsonl` + `discover.*` audit | Never invents replacements silently — an unconfigured entity is only *proposed* (anchor-driven), never auto-aliased unless `detection.auto_alias` is on; new `restricted` entities require human approval before use. Reuses existing mapping entries (stable identity). |
| **Privacy Compiler** | deterministic | real repo, `privacy.yaml`, mapping store | `workspace/ghost/` (fresh `git init`) + sibling `workspace/ghost-spec.md`, updated mapping, audit events | Node-scoped replacement only (identifier / string / comment nodes via tree-sitter). **Package import specifiers are kept verbatim** (a renamed dependency would not resolve in the ghost); first-party (`./`) specifiers still rewrite; `rewrite_imports: true` per entity overrides. Deterministic output. Never copies `.git`. Refuses to run if spec/mapping/audit paths resolve inside `--out`; re-scans the ghost tree for stray metadata before the baseline commit. |
| **Mapping store** | data | — | `workspace/private/mapping.json` | Boundary-internal. Holds real->ghost in cleartext (needed for reverse compile). Once an entry is `frozen`, its `ghost` value never changes. Versioned by `mapping_version`. |
| **Verification agent** | deterministic (`ghostc verify`) | `workspace/ghost/`, mapping store, `privacy.yaml` | `PASS` / `BLOCK` + reasons, exit 0/1, `verify.*` audit events | Fail closed. `BLOCK` on any real value found in the ghost (`\b`-anchored scan of mapping `real` values + seed spellings), any mapping-shaped file under the ghost, or `yarn lint` failure. Build gate is `skipped` without the toolchain unless `--require-build`. |
| **External coding agent** | off-the-shelf | ghost repo + ghost spec | ghost PR (branch + diff) | Treated as untrusted. No network to company services. |
| **Reverse Patch Compiler** | deterministic | ghost diff, mapping store | real diff applied to a branch on the real repo | Rejects: unmapped ghost-alias-shaped tokens, unexpected real entities, mapping-version mismatch, ambiguous resolution. |
| **PR-consistency agent** | LLM | real diff, task text | consistency verdict + flags | Output feeds a human review gate; does not merge. |
| **Orchestrator** | deterministic | all of the above | pipeline run + `workspace/private/audit.jsonl` | Enforces approval gates; assigns one `operation_id` per run; writes an audit event per step. |

## Data schemas

- `schemas/privacy-config.schema.json` — `privacy.yaml` shape (levels, strategies, defaults-by-kind, exclusions, entities)
- `schemas/mapping.schema.json` — the mapping store
- `schemas/audit-event.schema.json` — one line of `private/audit.jsonl`

## Privacy levels (summary — full decision test in `THREAT_MODEL.md`)

| Level | Transform? | Approval | On leak |
|---|---|---|---|
| public | no | — | n/a |
| internal | yes (stable alias) | auto | low severity, still counted |
| confidential | yes (mandatory) | auto only if match unambiguous | incident |
| restricted | yes (mandatory) | **human**; blocks sync | critical; never logged in cleartext |

## Transformation strategies

| Strategy | Example |
|---|---|
| `semantic_alias` | `SkyRoute Data Ltd -> FlightDataProviderA` |
| `synthetic_id` | `AcmeAir -> ClientA`, `10.20.4.7 -> PRIVATE_IP_001` |
| `synthetic_endpoint` | `api.northwind-internal.net -> internal-endpoint-a.example` |
| `generalize` | `nw-prod-eu-west-1 -> production-region-a` |
| `remove` | secrets / tokens -> deleted, env var kept |

## Language support

tree-sitter grammars: `javascript`, `typescript`, `tsx`, `hcl`. Everything else (`.yml`,
`.json`, `.env*`, `.md`, `Dockerfile`) goes through a scoped literal + regex matcher that only
touches configured entity values, never arbitrary strings.

## Evaluation

| Component | Kind | Input | Output | Contract |
|---|---|---|---|---|
| **Baseline** (`ghostc baseline`) | deterministic | real repo, `privacy.yaml` | `workspace/baseline-ghost/` + `baseline-spec.md` | The fair comparator, **not** a shippable ghost. Plain case-sensitive keyword replace of configured spellings only — no AST, casing engine, compound splice, graph, or mapping store. Reuses the compiler's file-walk so `eval` compares like with like. |
| **Eval harness** (`ghostc eval`) | deterministic | real repo, `privacy.yaml` | `workspace/eval-report.{md,csv}` + `eval.*` audit events | Builds baseline + compile ghosts, counts residual real-entity occurrences in each — **casing-aware** (compiler matchers in detector mode, primary metric) and **strict** (`anchored_scan`, the `verify` method). MVP: no external agent; task/approval/latency/token rows are `n/a`. |

On the fixture: baseline leaves **28** residual occurrences, `compile` leaves **0**.

## Monitoring is first-class

Every step emits a structured audit event. The eval report is **derived from the audit log**,
so the Improvement Changelog's evidence and the product's observability feature are the same
mechanism. Audit events carry `real_sha256`, never the real value.

## Agent workflow packages (Phases A–B; full writeup pending)

The trust boundary is also a **module-import rule**:

| package | side of the boundary | imports | entrypoint |
|---|---|---|---|
| `ghostc/` | company | deterministic compiler; `ghostc/spec.py` = `compile_spec`; `ghostc/mcp_server.py` | `ghostc`, `ghostc-mcp` |
| `bridge/` | neither | git forge (`LocalBareForge`) + LLM client (Claude / stub) | — |
| `client_agent/` | company | LangGraph orchestrator; imports `ghostc` + `bridge` | `ghostc-agent` |
| `consultancy_agent/` | external | coding agent; **may import only `bridge`** — `tests/test_boundary.py` fails if it reaches `ghostc`/`client_agent` | — |

The client↔consultancy handoff is a git push to a ghost remote (`bridge.forge`), not a
function call — so the two agents run as genuinely separate processes/containers with the
privacy boundary on the wire. `ghostc-mcp` exposes `compile_spec` / `discover` / `verify` /
`apply_patch` as MCP tools for LLM-driven use; the graph's fixed nodes call `ghostc.*`
in-process. Diagram: `client_agent/graph.md`.

## Where a production integration differs

Everything below is a **swap of the boundary system, not the pipeline**. The compiler,
mapping store, leak scan, reverse-compiler, audit log, and the `consultancy_agent` import
rule are unchanged; what changes is what they read from and write to.

| POC shortcut | Production form | What changes concretely |
|---|---|---|
| **Ghost / real remotes** are local bare repos; a "PR" is a JSON record + a pushed `refs/ghostc/pr/<id>`. | GitHub / GitLab / Bitbucket via their REST API behind the existing `Forge` seam (`bridge.forge`). | A real PR is opened on the ghost repo and on the real repo. `open_real_pr` posts the reverse-compiled branch **as a pull request**, not a bare branch; the PR description carries the substitution count and the `lossy` flags. Merge is gated by branch protection + `CODEOWNERS`, not by a console message. |
| **Trigger** is a synchronous `post-receive` hook that runs the consultancy agent in-process; `await_consultancy` then polls the branch once. | A forge **webhook** (`push` / `pull_request`) into a queue; the consultancy agent is a worker that consumes it. The client graph replaces the synchronous wait with a real `interrupt()` resumed by the webhook for the return event. | The two sides no longer need a shared filesystem. Auth becomes a scoped deploy key / token per side — the consultancy's credential can reach **only** the ghost remote. This is the credential-level boundary that the local POC approximates with separate `CONSULTANCY_*` env vars. |
| **Task source** is a `specs/*.md` file; `task-id:` is hand-authored to be boundary-neutral. | A Jira / Linear issue. An inbound webhook creates the run; `compile_spec` sanitizes the issue body; status transitions (`In Progress` → `In Review`) are written back via the tracker API. | The `task-id` → ghost branch name mapping needs a deterministic, non-reversible derivation from the issue key (the issue key itself may be sensitive). Attachments and comments become additional `compile_spec` inputs. |
| **Evaluation** is `ghostc eval` run by hand → `workspace/eval-report.md`. | A CI job (GitHub Actions / GitLab CI) that runs `ghostc eval` + `pytest` on every change and publishes the report and `metrics/agent-runs.jsonl` as a **build artifact / status check** — the same way test coverage or a Sonar report is surfaced. | No logic change; the report becomes a gate. A regression in leak count fails the check. `metrics/agent-runs.jsonl` is already shaped as one row per run for exactly this. |
| **Human approval** is a flagged branch + the consistency verdict printed to stdout. | A required PR review. The `PR-consistency agent` posts its verdict and entity flags as a **review comment**; a `restricted`-entity proposal from `discover` blocks the pipeline until an approver signs off in the tracker/forge. | The gate moves from "the operator reads the output" to "the forge won't let the merge button work". |
| **Secrets** live in one gitignored `.env` loaded by `bridge.env`. | Per-service secrets from the CI/orchestrator secret store; each side gets only its subset (`CLIENT_*` vs `CONSULTANCY_*`). | `.env` loading already never overrides a var set in the environment, so `docker run -e` / CI secrets / a Vault sidecar drop in without code changes. |
| **Determinism** via `--backend stub` and local repos. | The stub stays as the CI backend (fast, free, reproducible checks); real Claude runs only in the actual workflow. | The eval suite's numbers stay stable; the live workflow's task-pass-rate / cost / latency rows are populated from `metrics/agent-runs.jsonl` in production, not from the fixture.

**Next step (planned, not in this submission):** run the workflow inside CI so a reviewer sees
the **opened PRs** — ghost PR and reverse-compiled real PR — as normal forge objects, without
needing to execute anything locally. The Actions/webhook wiring is the following iteration.
