---
name: privacy-levels-model
description: The 4 privacy levels and the ordered decision test used to assign them
metadata: 
  node_type: memory
  type: project
  originSessionId: 98ea484b-2dc3-44e8-8c55-19efa120aaf2
  modified: 2026-08-29T14:48:32.378Z
---

Privacy Agent uses two orthogonal axes: **entity kind** drives the transformation *strategy*; **privacy level** drives whether we must transform, how strict the match must be, and the approval gate. Full text in `learn/hackaton/THREAT_MODEL.md`.

Levels → action:
- `public` — no transform (OSS libs, frameworks, localhost, placeholders)
- `internal` — stable alias, auto-approve (ubiquitous vendors: Datadog, Sentry, Stripe)
- `confidential` — mandatory transform, auto only if match unambiguous (non-public commercial relationship; internal service names; infra topology)
- `restricted` — mandatory transform, **human approval**, blocks sync (secrets, PII, client identity, contract-bound IDs); never logged in cleartext

Decision test (first match wins): 1) secret/credential/PII → restricted; 2) identifies the client or NDA-bound → restricted; 3) reveals non-public commercial relationship → confidential; 4) reveals exploitable internal attack surface → confidential; 5) unremarkable ubiquitous vendor → internal; 6) OSS/industry-standard tooling → public.

**Context beats token:** the level attaches to the occurrence, not the bare string — `Datadog` alone is internal, but a comment naming a client + email alongside it is restricted.

**How to apply:** Use when classifying entities in `privacy.yaml` or building the discovery/verification agents. Related: [[hackathon-scope-and-fixture]].
