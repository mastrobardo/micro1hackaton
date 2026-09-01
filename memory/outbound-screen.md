# The outbound screen (`ghostc screen` + the `screen` graph node)

Shipped session 10 (2026-09-01). Detect / score / gate the text that is **about to cross**,
for the entities `privacy.yaml` never named.

## Why it exists — the gap it closes

`ghostc compile` and `ghostc compile-spec` are **closed-world**:

- they substitute the entities in `privacy.yaml` + `mapping.json`, and
- their fail-closed gate leak-scans for **those same real spellings**
  (`ghostc/spec.py::_known_real_spellings`).

So an entity nobody ever configured — a partner typed fresh into a ticket — is invisible to
the redactor *and* to the redactor's own gate, and crosses untouched. `ghostc discover` had
the scorer that catches this class since session 6, but only as a **manual pass over a
repo**; it was never on the wire.

The screen scores the compiler's **output**, not its input. That is the design decision:
everything the closed world handled is already gone by then, so every remaining finding is
by construction an unknown. Screening the input would mostly re-report `privacy.yaml`.

## Shape

| piece | file | note |
|---|---|---|
| deterministic layer | `ghostc/screen.py` | import-light, no LLM, no `bridge` |
| LLM adjudicator | `client_agent/screen_llm.py` | lives here because `ghostc/` may not import `bridge` (`tests/test_boundary.py`) |
| graph node | `client_agent/graph.py::screen_node` | between `compile_spec` and `handoff`, **both** shapes |
| CLI | `ghostc screen` (deterministic only) | + `screen` MCP tool in `mcp_server.py` |
| example | `specs/002-onboard-halcyon-cargo.md` | a spec that exists to be blocked |

Three evidence layers, all folded into the *same* `combine_score` (noisy-OR) + `classify`
that `discover` uses:

1. structural shapes (`detect/shapes.py`) — secrets, internal hosts, contract/tenant ids,
   scoped packages, emails, RFC1918;
2. standing **unfrozen** `discover` proposals read from `candidates.jsonl` — a name the
   scorer already flagged and nobody moved into the config;
3. the injected adjudicator.

Ghost aliases from the config + mapping (`_known_ghosts`) are suppressed, or the compiler's
own output (`@vendor-a/sdk`, `ops@client-a.example`) would gate every run.

## Invariants — do not break these

- **The screen never transforms anything.** No screen signal is in
  `candidate._HARD_SIGNALS`, so `classify` can only return `review` / `ignore` here. Adding
  a hard signal to it would silently give it auto-transform power.
- **The model may accuse, never decide.** Every claim is re-anchored into the outbound text
  with `anchored_scan` before it can score — a name that exists only in the real half of
  the prompt, or in the model's imagination, is dropped and counted
  (`screen_llm_dropped`). Its signal is capped at `W_LLM_CAP = 0.60`, below
  `auto_threshold`.
- **`_restricted_floor`** queues a *structural* hit at a `restricted` level even below
  `review_threshold` (the email shape is 0.35 — tuned for repos, where an address is
  usually a package author; in an outbound ticket it is a person). Deliberately **not**
  extended to the adjudicator: a shape is a fact about the text, a model claim is an
  opinion.
- **A reviewer `accept` keeps blocking**; only `ignore` suppresses. An accepted entity has
  to reach `privacy.yaml` before the compiler can act on it.
- **Availability never weakens the gate silently.** `--screen-llm best-effort` (default)
  records `screen_llm: skipped` when no client key resolves and the deterministic layer
  still gates; `required` refuses to run on the stub. Failing closed on an *unavailable*
  model would break offline CI and every `--backend stub` run.

## Boundary note (user decision, session 10)

The adjudicator is a **`role="client"`** LLM and its prompt carries the **real** task text
alongside the ghost one, so it can diff them. That widens a crossing the PR-consistency
gate already makes rather than opening a new one; recorded in `THREAT_MODEL.md` → "Which
LLM sees what". `screen_findings` in `TaskState` quotes real surfaces — boundary-internal,
like `real_task`. Audit events are hash-only.

## Measured

`specs/002` (ticket naming an unconfigured partner), Opus 5 client role, one call ~4k
tokens: deterministic layer **4** findings (the shapes); with the adjudicator **5–7**
depending on the run — always the four shapes (corroborated upward, 0.35–0.55 → 0.70–0.81)
plus `Halcyon Freight` itself, and sometimes the derived spellings (`HalcyonClient`,
`halcyonClient.js`, `HALCYON_API_KEY`) whose confidence hovers around the threshold.
0 hallucinated claims observed. `specs/001` (the clean demo spec): **0** findings on both
layers — the demo path is unaffected.

The LLM-only rows are the whole argument for the layer: the deterministic detector
proposes an unconfigured entity **only from an anchor**, which is exactly what keeps
`helmet` / `swagger-jsdoc` out of `discover`'s proposals ([[detection-scoring]]) and
exactly what blinds it to a partner's name in an English sentence.

## Not done

- The screen runs on the **ghost task only**. The inbound direction — screening the
  consultancy's returned diff before it is reverse-compiled — is not wired.
- `ghostc screen` (the CLI) has no adjudicator by design; only the agent path does.

Related: [[detection-scoring]] · [[agent-harness]] · [[compiler-and-alias-model]] ·
[[verify-and-leak-scan]]
