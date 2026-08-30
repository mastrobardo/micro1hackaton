# Fixtures — synthetic sensitive-entity layer

The base repo (`hagopj13/node-express-boilerplate`, MIT) has no client-identifying or
commercially-sensitive content — real OSS never does. To measure a **leak count** we need a
known ground-truth set of sensitive entities, so we inject a small, fully **fictional** layer
(ground rule 07: synthetic data).

Everything here is invented. There are no real credentials, clients, or endpoints
(ground rule 08).

## What gets injected

| File | Entities it introduces |
|---|---|
| `inject/src/integrations/skyRouteClient.js` | `SkyRoute Data Ltd` vendor, `api.northwind-internal.net`, `SKYROUTE_API_KEY` |
| `inject/src/integrations/observability.js` | `Datadog`, `Sentry` (low-sensitivity vendors) |
| `inject/src/integrations/internalServices.js` | `booking-core`, `pricing-svc`, `fare-cache`, `10.20.4.7`, `Priya Nair` (person / PII) |
| `inject/src/integrations/adversary.js` | **`ghostc discover` adversarial corpus.** Fictional vendor *Meridian Aero Systems* (aka Meridian / MAS / MDS / meridianaero / meridian-flight) and gateway operator *Contoso* — **deliberately NOT in `privacy.yaml`**, so `discover` recall is measured "from code alone". 20+ evasion forms: a "known internally as:" alias list, `@meridianaero/flight-sdk` scoped package, `process.env.X ‖ 'literal'` env-var laundering, `const flightProvider = client` alias chains, base64 blobs, split strings, case-variant arrays, DB/cache namespaces, cert paths. Not lint-clean by design → excluded from the build gate. Targets: `tests/expected/discover-groundtruth.json`. |
| `inject/.env.northwind.example` | `Northwind Airlines` client, vendor key, region |
| `infra/main.tf`, `infra/variables.tf` | `nwa-prod-eu-west-1`, AWS account `447015923388`, same vendor + IP (HCL path) |

Ground truth for the metric is `privacy.yaml` `entities` (all `source: seed`). The seed set
spans three transform levels — `internal` (Datadog, Sentry), `confidential` (vendor / service /
infra topology), `restricted` (client identity, AWS account, API key, `Priya Nair` PII). The
`public` level is exercised in the `discover` phase (candidates classified public and kept).

## Apply

```bash
./fixtures/apply.sh          # -> workspace/real/  (base repo + injected layer)
```

Idempotent: re-running rebuilds `workspace/real/` from the clone at
`../node-express-boilerplate`.
