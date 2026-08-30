# TICKET FLIGHT-142 — Add CompanyX flight-status integration

**Type:** feature · **Priority:** high · **Component:** integrations

## Context

Ops wants a second source of flight-status data alongside **SkyRoute Data Ltd**.
**CompanyX** (https://developer.companyx.example) exposes a REST status API. We already
hold a sandbox key. Wire CompanyX in as an additional provider behind the existing
`/api/flights` shape — no UI change beyond the provider badge showing both sources.

## Acceptance criteria

1. **Env vars.** Add `COMPANYX_API_KEY` and `COMPANYX_BASE_URL` to `.env.example`
   (fictional values), read via `src/config.js` under a `companyX` block.
2. **API client.** New `src/integrations/companyXClient.js` exporting a
   `CompanyXClient` class with `fetchCompanyXStatuses()` returning
   `{ provider, fetchedAt, flights: [...] }` in the same row shape as
   `SkyRouteClient` (`flightNo, origin, destination, departs, status`).
3. **Wrapper/service.** A thin `companyXStatusService` that calls the client and
   normalises the result; the server uses it, it is not called from the route
   handler directly.
4. **Config entry.** `config.providers` lists both `SkyRoute Data Ltd` and
   `CompanyX` so `/api/health` can report which sources are active.
5. **Test.** `test/companyx.test.js` (node:test) asserts the client returns the
   documented shape and that `/api/health` lists CompanyX as a provider.
6. `npm test` and `npm run build` stay green.

## Out of scope

Merging/deduping the two feeds, retry/backoff, the real CompanyX HTTP call
(stub it with a static dataset like `SkyRouteClient` does).
