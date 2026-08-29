# Session TODO — 2026-08-29

Session-scoped checklist (easier to skim than the CLI todo). Long-term plan lives in `TODO.md`; running status in `PROGRESS.md`.

## This session: scaffold + entity discovery

- [x] Read `TODO.md` (roadmap) and the hackathon PDF (rules, judging, deliverables)
- [x] Agree long-term goal + hackathon-scoped slice
- [x] Pick reproducible base repo → `hagopj13/node-express-boilerplate` (MIT, offline tests)
- [x] Clone base repo → `../node-express-boilerplate`
- [x] Scaffold docs: `README.md`, `PROGRESS.md`, `CHANGELOG.md`, `ARCHITECTURE.md`, `THREAT_MODEL.md`
- [x] Scaffold `schemas/` (privacy-config, mapping, audit-event)
- [x] Scaffold `privacy.yaml` (levels + strategies + synthetic entities)
- [x] Scaffold `ghostc/` Python CLI skeleton (`discover`/`compile`/`verify`/`apply-patch`/`eval`)
- [x] Scaffold `fixtures/` (synthetic sensitive-entity layer + `infra/*.tf`)
- [x] Scaffold `scripts/` (`demo.sh`, `eval.sh`) + `.gitignore`
- [x] Install package, smoke-test CLI (`ghostc validate-config` works; 13 seed entities OK)
- [x] Build `workspace/real/` via `fixtures/apply.sh`
- [x] Run entity discovery (manual grep pass — discovery agent not built yet)
- [ ] **← YOU: approve the entity list** (see "Discovery result" below) before building `compile`

## Next session (not now)

- [ ] Implement `ghostc compile` — tree-sitter (JS/TS) node-scoped replacement + stable aliases
- [ ] Implement `ghostc verify` — leak scan + `yarn lint` gate (fail closed)
- [ ] Baseline: `sed` keyword redaction path
- [ ] `ghostc eval` — 10 cases, baseline vs solution, metric table
- [ ] `ghostc apply-patch` — ghost diff → real diff + ambiguity rejection
- [ ] Wire audit log through every step; start filling `CHANGELOG.md` with evidence

## Discovery result (for your approval)

**Seed entities** — 12 of 13 confirmed present in `workspace/real`:
`Northwind Airlines`, `SkyRoute Data Ltd`, `Datadog`, `Sentry`, `booking-core`, `pricing-svc`,
`fare-cache`, `api.northwind-internal.net`, `10.20.4.7`, `nwa-prod-eu-west-1`, `447015923388`,
`sk_live_northwind_…`. `AeroFeed` (swap target for case 10) is intentionally absent until the agent adds it.

**New candidates in the base repo → all `public`, no transform:**

| Candidate | Proposed | Why |
|---|---|---|
| `support@yourapp.com` (`EMAIL_FROM`), `email-server` SMTP placeholder, `Ethereal` | public | placeholders / ubiquitous test service |
| `mongodb://127.0.0.1:27017/...` | public | localhost only |
| `nodemailer`, `passport-jwt`, `swagger`, `mongoose`, `coveralls` | public | OSS libraries |

**Conclusion:** the base repo has no sensitive surface of its own — ground truth = exactly the
13 seed entities in `privacy.yaml`. Clean for the leak metric.

## Open questions for you

1. Approve the discovery result above (nothing to add to `privacy.yaml`)?
2. The 10 eval tasks (`PROGRESS.md` → "Eval cases") — good set or swap any?
3. Alias naming: keep `FlightDataProviderA` / `internal-service-a` style, or prefer flatter `vendor-a`?
