# TICKET FLIGHT-142 — Add CompanyX flight-status integration

<!-- ghostc:spec
task-id: 001-add-second-provider
fixture: webapp
config: fixtures/webapp/privacy.webapp.yaml
-->

**Type:** feature · **Priority:** high · **Component:** integrations

## Context

Ops wants a second source of flight-status data alongside **SkyRoute Data Ltd** for
**Northwind Airlines**. **CompanyX** (https://developer.companyx.example) exposes a REST
status API and we already hold a sandbox key. Wire CompanyX in as an additional provider
behind the existing `/api/flights` shape — no UI change beyond the provider badge showing
both sources. The `booking-core` service consumes `/api/flights` unchanged.

## Acceptance criteria

1. **Env vars.** Add `COMPANYX_API_KEY` and `COMPANYX_BASE_URL` to `.env.example`
   (fictional values), read via `src/config.js` under a `companyX` block.
2. **API client.** New `src/integrations/companyXClient.js` exporting a `CompanyXClient`
   class with `fetchCompanyXStatuses()` returning `{ provider, fetchedAt, flights: [...] }`
   in the same row shape as `SkyRouteClient`
   (`flightNo, origin, destination, departs, status`). Stub the upstream call with a
   static dataset, exactly as `SkyRouteClient` does.
3. **Wrapper / service.** A thin `companyXStatusService` that calls the client and
   normalises the result. The server uses it; it is not called from the route handler
   directly.
4. **Config entry.** `config.providers` lists both `SkyRoute Data Ltd` and `CompanyX` so
   `/api/health` can report which sources are active.
5. **Test.** `test/companyx.test.js` (`node:test`) asserts the client returns the
   documented shape and that `/api/health` lists CompanyX as a provider.
6. `npm test` and `npm run build` stay green.

## Out of scope

Merging / deduping the two feeds, retry / backoff, and the real CompanyX HTTP call
(stub it with a static dataset like `SkyRouteClient` does).

## Notes for the workflow

- Entities in play: `Northwind Airlines`, `SkyRoute Data Ltd`, `booking-core`, `CompanyX`.
  `ghostc compile-spec` rewrites this ticket into the sanitized `TASK.md` the consultancy
  side sees — `CompanyX` becomes its ghost alias (`PartnerA`), no real names cross the
  boundary.
- `task-id` above (`001-add-second-provider`) is deliberately **boundary-neutral**: it
  becomes the `ghostc/task/<id>` git branch name on the ghost remote, which the consultancy
  side can see. Keep sensitive names out of it. The filename can stay descriptive.
- The consultancy agent implements `TASK.md` on the **same** `ghostc/task/001-add-second-provider`
  branch of the ghost remote and pushes. No PR in this flow.
