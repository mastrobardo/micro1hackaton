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

# 4. pipeline  (validate-config + compile implemented; discover/verify/apply-patch/eval are stubs)
ghostc discover --repo workspace/real --config privacy.yaml
ghostc compile  --repo workspace/real --config privacy.yaml --out workspace/ghost
ghostc verify   --ghost workspace/ghost --mapping workspace/private/mapping.json
ghostc apply-patch --ghost-diff <diff> --mapping workspace/private/mapping.json --real workspace/real
ghostc eval     --cases eval/cases --config privacy.yaml
```

## What pre-existed vs. what we added (ground rule 02)

| Pre-existing | Added for the competition |
|---|---|
| `hagopj13/node-express-boilerplate` (the fixture, unmodified upstream) | Everything in this repo: `ghostc/` compiler + agents, `privacy.yaml`, `schemas/`, `fixtures/` synthetic entity layer, eval harness, all docs |

## License / data

Fixture is MIT. All injected client / vendor / infrastructure entities are **fictional**
(`fixtures/`). No real credentials or private data are in this repo (ground rule 08).
