# ghostc — project overview

*One-page introduction. For how to run it: `GETTING_STARTED.md`. For the evidence trail:
`CHANGELOG.md`. For design and trade-offs: `ARCHITECTURE.md`.*

---

## The goal

**Reduce the surface where an *unintentional* data leak can happen when private code is handed
to a third-party model — and prove it works.** Show that an external AI coding agent (Claude,
Copilot, Codex) can do real work on a private codebase without ever seeing a real client name,
commercial partner, internal service, private host, or secret, and that the result still comes
back as a usable pull request.

This is deliberately scoped. It defeats *accidental* disclosure — the hand-redaction that
misses a casing variant, the agent that quotes a client name in a comment or a PR body, the
leaked env-var name — and makes that case **measurable** (leak count, target 0). It is **not**
a guarantee against a motivated adversary doing structural correlation analysis; see
`THREAT_MODEL.md` for where the line is.

## The problem

Consultancies and product teams work on **client-owned code**. They want to use external AI
coding agents (Codex, Copilot, Claude) on those repos, but they cannot let client identity,
commercial partners, internal service names, private infrastructure, or secrets leave the
company boundary. Today they either don't use external agents on that code at all, or someone
hand-redacts it first.

## Why it's hard

Redaction is a dead end. String-replacing `SkyRoute Data Ltd` with `REDACTED`:

- **breaks the code** — corrupts identifiers, import paths, env-var names;
- **strips the meaning** the agent needs to do the task;
- **still leaks** — it misses the same entity spelled three other ways
  (`skyRoute`, `SKYROUTE_API_KEY`, `skyRouteClient.js`).

There's no repeatable, auditable method that keeps the repo **useful** while keeping it
**safe**.

## What ghostc does

It **compiles** a real repo into a semantically-faithful **ghost repo** —
`SkyRoute Data Ltd → Vendor A`, not `→ REDACTED` — lets an ordinary external agent work on the
ghost, and **reverse-compiles** the resulting ghost PR back into a real-repo PR. Every step is
deterministic and emits a structured audit event.

```
real ticket
  → Entity Discovery   score + propose sensitive entities (human approves `restricted`)
  → Privacy Compiler   tree-sitter JS/TS + HCL; one stable alias per entity, re-cased per use
  → Verification       leak scan + build gate — fail closed
  → External agent     ghost only: no real repo, no mapping, no credentials
  → Reverse Patch      ghost diff → real diff; rejects anything ambiguous
  → PR-consistency     does the real diff match the task? → human review
  → real PR
```

The privacy boundary is also a **module-import rule**: the external agent's package
(`consultancy_agent/`) may not import the compiler or the mapping store, and a test fails if
it does.

## The number that matters

**Leak count** — ground-truth real sensitive values visible to the external agent
(ghost repo + ghost spec). Target **0**.

| | Baseline (`sed` redaction) | ghost compiler | Change |
|---|:---:|:---:|:---:|
| Residual real-entity occurrences (casing-aware) | **28** | **0** | **−28 (100%)** |
| Reversible (ghost PR → real PR) | no | yes | — |
| Code still runs (`node --check`, tests) | no (corrupted) | yes | — |

Measured by `ghostc eval` on a fixed fixture; `ghostc discover` separately re-finds 13/13
configured entities from code alone and proposes 2 unconfigured ones with no OSS-library false
positives.

## Status

The deterministic pipeline (`discover` / `compile` / `verify` / `baseline` / `eval` /
`apply-patch`) is complete and tested. The agent workflow runs end to end: a real ticket
becomes a sanitized ghost task, a real Claude agent implements it on the ghost repo, and the
work is reverse-compiled onto a real-repo branch — verified leak-clean with tests green on
both sides. This submission is a **reproducibility-first POC**: local git repos stand in for a
forge, spec files stand in for an issue tracker, and everything runs offline from a clean
checkout. `ARCHITECTURE.md` spells out where a production integration would differ.
