---
name: hackathon-scope-and-fixture
description: "Privacy Agent hackathon slice — scope cut, base fixture choice, and why"
metadata: 
  node_type: memory
  type: project
  originSessionId: 98ea484b-2dc3-44e8-8c55-19efa120aaf2
  modified: 2026-08-29T14:48:23.801Z
---

micro1 Agentic Workflows Hackathon project in `learn/hackaton/`. Long-term roadmap is `TODO.md` (16 phases); the hackathon build is a thin vertical slice: one-shot privacy compiler (JS/TS + HCL) → verify → external agent → reverse patch compiler → eval, with the audit log as the measurement instrument.

**Why these choices** (details in `PROGRESS.md` decision log):
- Anonymizer CLI is **Python** even though targets are TS/HCL — it is a standalone process, not bound to repo language; tree-sitter parses TS/JS/HCL from Python.
- Base fixture is **`hagopj13/node-express-boilerplate`** (MIT, offline tests), cloned to `learn/node-express-boilerplate` (sibling, outside the submission). Sharetribe was rejected: its frontend needs a paid Marketplace API subscription, so judges can't reproduce it.
- A **synthetic sensitive-entity layer** is injected into the fixture (`fixtures/inject/` + `fixtures/infra/`) — fictional client Northwind Airlines, vendor SkyRoute Data Ltd, Datadog/Sentry, internal services, IPs, AWS account, fake API key. Real OSS has no NDA'd entities, and the leak metric needs a known ground-truth set. Ground truth = the 13 `source: seed` entities in `privacy.yaml`.

**How to apply:** When resuming, read `SESSION_TODO.md` and `PROGRESS.md` first. Next implementation step is `ghostc compile`. User does private parallel testing on undisclosed TS/Terraform repos — nothing about those enters the micro1 submission. Related: [[privacy-levels-model]].
