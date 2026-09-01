# Threat model

Scope: the hackathon slice. Production hardening is roadmap Phase 11 (`TODO.md`).

## What may cross the privacy boundary

- The ghost repository (`workspace/ghost/`) after the Verification agent returns `PASS`
- The ghost implementation spec (`workspace/ghost-spec.md`)
- The ghost PR produced by the external agent (it is already ghost-side)

## What must never cross

- The real repository
- The mapping store (`workspace/private/mapping.json`) — contains real->ghost in cleartext
- The audit log (`workspace/private/audit.jsonl`) — even though it stores only hashes of real values
- `privacy.yaml` `entities[].real` values
- Any credential, token, private key, connection string
- Real task text (Jira), real client names, real commercial-relationship details

## Which LLM sees what

Two model **roles**, and they are not equally trusted (`bridge/llm.py::resolve_secret`
gives each its own key so they can be billed and revoked separately):

| role | runs | prompt may contain | why |
|---|---|---|---|
| `client` | inside the boundary: the PR-consistency verdict, the `screen` adjudicator | **real** values — the real task text, the real diff | It is the company's own model call, on the company's own key, about the company's own data. It never talks to the consultancy. |
| `consultancy` | outside: the external coding agent | ghost values only | It is the adversary in the row below. |

So the `screen` adjudicator (`client_agent/screen_llm.py`) is given the real task
*and* the ghost task and asked to diff them. That is a deliberate widening of a
crossing the consistency gate already makes, not a new one: it buys the recall that
catches a partner name in prose, where the deterministic detector has no anchor to
work from. It costs one API call per task, on the client key.

If that trade is wrong for a deployment, `--screen-llm off` removes the layer and the
deterministic screen still gates; a self-hosted client model removes the crossing
without removing the layer.

## Adversaries considered

| Adversary | Assumed capability | Mitigation in this slice |
|---|---|---|
| External AI provider | Sees everything given to the coding agent; may log/retain it | Privacy by construction: the ghost is already safe. Verification agent gate. Leak metric proves it. |
| Compromised / misbehaving coding agent | Executes arbitrary code in the ghost workspace; tries to exfiltrate | Ghost workspace has no real credentials and no network route to company services (enforced by the run sandbox, not by asking the model). |
| Curious reviewer of the ghost PR | Reads the ghost diff | Ghost diff contains only ghost entities; reverse compiler is the only path back. |
| Mapping-store leak | Obtains `mapping.json` | Full de-anonymization. Treated as crown-jewel: lives under `workspace/private/`, gitignored, never an output that crosses. `compile` refuses to write it (or the audit log) anywhere inside the ghost repo. (Encryption at rest = Phase 11.) |

## Privacy-level decision test

Assign the level by the first matching rule:

1. Secret, credential, token, private key, or PII / regulated data -> **restricted**
2. Directly identifies the client / end customer, or is name-bound by NDA / contract -> **restricted**
3. Reveals a non-public commercial relationship — contract, partnership, data-supply deal (the OAG / `SkyRoute` case) -> **confidential**
4. Reveals exploitable internal attack surface — internal hostnames, network topology, account IDs, auth architecture, non-public service names -> **confidential**
5. Widely-used, unremarkable vendor whose presence reveals nothing competitive and is often publicly inferable (Datadog, Sentry, Stripe, GA) -> **internal**
6. Open-source / industry-standard tooling, language, framework (Express, Mongoose, Jest, Terraform) -> **public**

**Context beats token.** The level attaches to the occurrence, not the bare string.
`Datadog` alone -> internal. `// Datadog dashboard for Northwind fraud team, ping jane@northwind.example`
-> restricted (client name + PII present).

## Known limitations (be honest for judging)

- **Re-identification by structure.** Semantic preservation and privacy are in tension. A ghost
  entity that carries a vendor's exact API surface, webhook event names, and idempotency
  semantics can be re-identified by a determined analyst. Our bar for this slice: defeat casual
  inspection and accidental disclosure, not a motivated adversary doing correlation analysis.
- **One-shot only.** No incremental sync; each run recompiles. Mapping stability across runs is
  provided by the mapping store, but divergence handling is not implemented (Phase 4).
- **Entity discovery is not exhaustive.** Recall depends on `privacy.yaml` + the discovery
  agent. `ghostc screen` is the second backstop on the outbound wire (structural shapes +
  standing `discover` proposals + an LLM adjudicator, `screen.scanned` / `screen.blocked`),
  and it is what catches an entity nobody ever configured. It is still not a proof:
  a sensitive name with no shape, no standing proposal, and nothing about it that reads
  as a proper noun can pass all three layers. The gate raises the floor; it does not
  close the class.
- **Sandbox is assumed, not built.** Network isolation for the external agent is a property of
  how the run is executed, not enforced by this codebase in the slice.
- **Reverse compilation of agent-invented tokens.** New identifiers the agent creates that
  reference ghost aliases are handled heuristically; genuinely ambiguous cases are rejected for
  human resolution rather than guessed.

## Assumptions

- The company side (real repo, mapping, agents, audit) runs on trusted infrastructure.
- Humans are available at the approval gates (`restricted` entity discovery, final PR review).
- The fixture's injected entities are fictional; no real data is at risk in this repo.
