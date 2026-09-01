# TICKET FLIGHT-153 — Onboard Halcyon Freight as a cargo status provider

<!-- ghostc:spec
task-id: 002-add-cargo-provider
fixture: webapp
config: fixtures/webapp/privacy.webapp.yaml
-->

**Type:** feature · **Priority:** high · **Component:** integrations

> **This spec exists to be blocked.** It is the worked example for the `screen`
> gate: a ticket written the way tickets actually get written, naming a partner
> that is **not** in `fixtures/webapp/privacy.webapp.yaml`. `compile-spec`
> sanitizes the four configured entities and — being closed-world — hands the
> rest straight through. `screen` is what stops the run. See
> `docs/PROGRESS.md` → "the screen gate" for the expected output.

## Context

Ops has signed **Halcyon Freight** (contract `HAL-CF-2026-01`) as a cargo partner for
**Northwind Airlines**. Their flight-status feed sits behind `gw.prod.halcyon.internal`
and our sandbox key is `hal_live_9f8e7d6c5b4a3210`. Integration questions go to
dispatch.lead@halcyonfreight.example.

Wire Halcyon in as an additional provider behind the existing `/api/flights` shape,
alongside **SkyRoute Data Ltd**. The `booking-core` service consumes `/api/flights`
unchanged.

## Acceptance criteria

1. **Env vars.** Add `HALCYON_API_KEY` and `HALCYON_BASE_URL` to `.env.example`
   (fictional values), read via `src/config.js` under a `halcyon` block.
2. **API client.** New `src/integrations/halcyonClient.js` exporting a `HalcyonClient`
   class with `fetchHalcyonStatuses()` returning `{ provider, fetchedAt, flights: [...] }`
   in the same row shape as `SkyRouteClient`. Stub the upstream call with a static
   dataset, exactly as `SkyRouteClient` does.
3. **Config entry.** `config.providers` lists Halcyon so `/api/health` reports it.
4. **Test.** `test/halcyon.test.js` (`node:test`) asserts the documented shape.
5. `npm test` and `npm run build` stay green.

## Expected result — a fail-closed block, not a PR

```bash
client-agent start 002-onboard-halcyon-cargo
# REJECTED (fail closed): screen: 5 unscreened finding(s) in the outbound ghost_task
```

Nothing reaches the ghost remote: `screen` runs before `handoff`, the only node that
writes to the ghost side. The findings split cleanly across the two layers —

| finding | score | caught by |
|---|---|---|
| `hal_live_9f8e7d6c5b4a3210` | 0.81 | shape (`prefixed_secret`) + adjudicator |
| `gw.prod.halcyon.internal` | 0.76 | shape (`internal_host`) + adjudicator |
| `HAL-CF-2026-01` | 0.75 | shape (`contract_id`) + adjudicator |
| `dispatch.lead@halcyonfreight.example` | 0.70 | shape (`email`) + adjudicator |
| `Halcyon Freight` | 0.57 | **adjudicator only** — prose, no structural anchor |

That last row is why the LLM layer exists: the deterministic detector proposes an
unconfigured entity only from an *anchor*, and a partner's name in a sentence has none.
With `--screen-llm off` the run still blocks, on the first four — which is the point of
having a deterministic layer under the model rather than only a model.

**The count varies between 5 and 7 across runs, the gate does not.** The four shapes are
deterministic and always fire. The adjudicator's confidence on the *derived* spellings
(`HalcyonClient`, `halcyonClient.js`, `HALCYON_API_KEY`, `halcyon.test.js`) moves around
0.4–0.5, so some runs put them over `review_threshold` and some under. `Halcyon Freight`
itself has cleared the line on every run. Treat the flagged **set** as stable and the
tail as a confidence gradient — which is the honest description of a scored gate.

## Clearing it

Either add `Halcyon Freight` to `fixtures/webapp/privacy.webapp.yaml` (then
`compile-spec` substitutes it and the screen goes quiet), or dismiss individual
findings in `ghostc-review` — an `ignore` in `decisions.jsonl` suppresses that
surface permanently, and `client-agent start --decisions <path>` picks it up.
