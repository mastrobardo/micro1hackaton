# `fixtures/webapp` — runnable fullstack fixture

A tiny fullstack web app used to demo the privacy compiler on something you can
**open in a browser**, not just leak-scan. The real repo and the compiled ghost
repo run side by side on two ports and serve the same UI — one with real
client/vendor names, one with aliases.

## What it is

`app/` — the version-controlled template. **Zero runtime dependencies**: Node's
built-in `http` server + `node:test`. ~12 files. `npm ci` installs nothing, so the
whole thing is offline and reproducible.

| path | role |
|---|---|
| `app/src/server.js` | HTTP server — `/`, `/api/health`, `/api/flights`, static assets |
| `app/src/config.js` | one source for the display names + env-driven credentials |
| `app/src/integrations/skyRouteClient.js` | SkyRoute Data Ltd flight-schedule client (existing partner) |
| `app/src/integrations/internalServices.js` | `booking-core` on `api.northwind-internal.net` |
| `app/public/` | the console UI (vanilla HTML/JS/CSS, names pulled live from the API) |
| `app/test/api.test.js` | contract tests on response *shape* — pass for real **and** ghost |
| `tasks/add-companyx-integration.md` | the first real ticket — add CompanyX (Phase C1/C2) |
| `privacy.webapp.yaml` | focused entity set for this fixture (subset of the repo-root config, same aliases) |

Sensitive entities the app carries: `Northwind Airlines` → `client-a`,
`SkyRoute Data Ltd` → `vendor-a`, `booking-core` → `service-a`,
`api.northwind-internal.net` → `host-a.example`, `Priya Nair` → `person-a`,
`SKYROUTE_API_KEY` value → removed.

## Where real + ghost live

**Outside this repo** — a sibling dir, like `../node-express-boilerplate`:

```
$GHOSTC_DEMO_ROOT/real     # clean checkout of app/  (default: ../ghostc-demo/real)
$GHOSTC_DEMO_ROOT/ghost    # ghostc compile output
$GHOSTC_DEMO_ROOT/ghost-spec.md
```

Boundary-internal artifacts (`mapping.json`, `audit.jsonl`, `candidates.jsonl`)
stay in-repo under `workspace/webapp-private/` and never cross to the ghost.

## Run the demo

```bash
./scripts/demo-webapp.sh          # stage real -> compile ghost -> verify -> test both -> serve :3000 + :3001
```

Then open `http://localhost:3000` (real) and `http://localhost:3001` (ghost).
`REAL_PORT` / `GHOST_PORT` override the ports; `DEMO_NO_SERVE=1` stops after the
health diff.

Manually:

```bash
GHOSTC_DEMO_ROOT=../ghostc-demo ./fixtures/webapp/apply.sh
( cd ../ghostc-demo/real && npm ci && npm test && PORT=3000 npm start )

ghostc compile --repo ../ghostc-demo/real \
  --config fixtures/webapp/privacy.webapp.yaml \
  --out ../ghostc-demo/ghost --spec ../ghostc-demo/ghost-spec.md \
  --mapping workspace/webapp-private/mapping.json \
  --audit workspace/webapp-private/audit.jsonl \
  --candidates workspace/webapp-private/candidates.jsonl
( cd ../ghostc-demo/ghost && npm ci && npm test && PORT=3001 npm start )
```

Everything here is fictional — no real credentials, clients, or endpoints.
