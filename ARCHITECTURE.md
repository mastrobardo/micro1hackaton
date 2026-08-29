# Architecture

Scope: the hackathon slice. Full system is in `TODO.md`.

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
| **Entity Discovery agent** | LLM + deterministic scan | real repo, `privacy.yaml`, mapping store | candidate entity list (`id`, `kind`, `level`, `strategy`, occurrences) | Never invents replacements silently; new `restricted` entities require human approval before use. Reuses existing mapping entries (stable identity). |
| **Privacy Compiler** | deterministic | real repo, `privacy.yaml`, mapping store | `workspace/ghost/` (fresh `git init`), updated mapping, audit events | Node-scoped replacement only (identifier / string / import / comment nodes via tree-sitter). Deterministic output. Never copies `.git`. |
| **Mapping store** | data | — | `workspace/mapping.json` | Boundary-internal. Holds real->ghost in cleartext (needed for reverse compile). Once an entry is `frozen`, its `ghost` value never changes. Versioned by `mapping_version`. |
| **Verification agent** | LLM + deterministic | `workspace/ghost/`, mapping store | `PASS` / `BLOCK` + reasons | Fail closed. `BLOCK` on any real value found in the ghost, any unresolved `restricted` entity, or `yarn lint` failure. |
| **External coding agent** | off-the-shelf | ghost repo + ghost spec | ghost PR (branch + diff) | Treated as untrusted. No network to company services. |
| **Reverse Patch Compiler** | deterministic | ghost diff, mapping store | real diff applied to a branch on the real repo | Rejects: unmapped ghost-alias-shaped tokens, unexpected real entities, mapping-version mismatch, ambiguous resolution. |
| **PR-consistency agent** | LLM | real diff, task text | consistency verdict + flags | Output feeds a human review gate; does not merge. |
| **Orchestrator** | deterministic | all of the above | pipeline run + `workspace/audit.jsonl` | Enforces approval gates; assigns one `operation_id` per run; writes an audit event per step. |

## Data schemas

- `schemas/privacy-config.schema.json` — `privacy.yaml` shape (levels, strategies, defaults-by-kind, exclusions, entities)
- `schemas/mapping.schema.json` — the mapping store
- `schemas/audit-event.schema.json` — one line of `audit.jsonl`

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

## Monitoring is first-class

Every step emits a structured audit event. The eval report is **derived from the audit log**,
so the Improvement Changelog's evidence and the product's observability feature are the same
mechanism. Audit events carry `real_sha256`, never the real value.
