# Demoable fixture — C0 SHIPPED (2026-08-31)

The judged win is no longer only **leak count = 0** — it is **the ghost repo builds + tests
pass after the external agent's change, and the real repo builds + tests pass after
reverse-patch.** C0 delivers the fixture that makes that demonstrable.

## Decisions (settled with the user this session)

- **Hand-authored, zero runtime dependencies** — not a Yeoman/Vite scaffold. Node's
  built-in `http` server + `node:test`. `npm ci` installs nothing → offline, instant,
  reproducible from a clean checkout. Reproducibility signal > scaffold realism.
- **Real + ghost checkouts live OUTSIDE the tool repo** — `$GHOSTC_DEMO_ROOT/{real,ghost}`,
  default `../ghostc-demo/{real,ghost}`, a sibling of the repo like
  `../node-express-boilerplate`. Keeps the tool repo clean; matches "two independent
  projects". Boundary-internal artifacts (`mapping.json`/`audit.jsonl`/`candidates.jsonl`)
  stay in-repo at `workspace/webapp-private/` (gitignored).

## What got built

| path | role |
|---|---|
| `fixtures/webapp/app/` | version-controlled template — `src/server.js`, `src/config.js`, `src/integrations/{skyRouteClient,internalServices}.js`, `src/data/schedules.js`, `public/{index.html,app.js,style.css}`, `test/api.test.js`, `scripts/build.js`, `package.json` (no deps) |
| `fixtures/webapp/privacy.webapp.yaml` | 6-entity subset of the root `privacy.yaml`, same aliases + schema. `Northwind Airlines`→`client-a`, `SkyRoute Data Ltd`→`vendor-a`, `booking-core`→`service-a`, `api.northwind-internal.net`→`host-a.example`, `Priya Nair`→`person-a`, `sk_live_…` value removed |
| `fixtures/webapp/apply.sh` | stage template → `$GHOSTC_DEMO_ROOT/real` + git baseline commit |
| `fixtures/webapp/tasks/add-companyx-integration.md` | the first real ticket (FLIGHT-142) — names real `CompanyX`; for C1/C2 |
| `scripts/demo-webapp.sh` | stage → `ghostc compile` → `ghostc verify` → `npm test` both → serve real :3000 + ghost :3001, print the health-endpoint diff. `REAL_PORT`/`GHOST_PORT`/`DEMO_NO_SERVE` |
| `tests/test_webapp_fixture.py` | node-gated (skips w/o `node`). real + ghost both `npm test` + `node scripts/build.js` green; ghost `anchored_scan` leak-free. Suite 229→**235 pass / 1 skip** |

The UI reads client/vendor/service names **live from `/api/health`**, so the two browser
windows visibly differ (real: Northwind Airlines / SkyRoute Data Ltd / booking-core / Priya
Nair — ghost: Client A / Vendor A / service-a / Person A) with identical layout + tests.
`.html`/`.css` are in the scoped parser's ext list so static UI strings alias too.

## Verified this session

`./scripts/demo-webapp.sh` end to end: real + ghost serve, 4/4 `node --test` each,
`ghostc verify` PASS on the ghost, health-endpoint diff shows the alias swap. Compile:
14 files scanned, 11 changed, `skyRouteClient.js`→`vendorAClient.js` renamed + the
`require` rewritten, 6 entities / 75 occurrences.

## Next (C1 → C2 → C3)

- **C1:** add `CompanyX` (kind `vendor` → `partner-a`/`PartnerA`) to `privacy.webapp.yaml`;
  confirm `ghostc compile-spec` rewrites `fixtures/webapp/tasks/add-companyx-integration.md`
  to name `PartnerA`, leak-clean.
- **C2:** real Claude consultancy coding agent (`consultancy_agent/agent.py`) — tool-loop
  scoped to the ghost checkout, `assert_boundary_clean` first, opens the ghost PR. Keep a
  deterministic scripted fallback for offline/`--backend stub`.
- **C3:** graph `verify` node runs `npm ci && npm test && npm run build` on an applied real
  checkout; `agent.metrics` gains `ghost_build`/`ghost_tests`/`real_build`/`real_tests`.

Full breakdown: `SESSION_TODO.md` → "NEXT SESSION — Phase C".
Related: [[agent-harness]], [[working-preferences]], [[project-goal-and-status]].
