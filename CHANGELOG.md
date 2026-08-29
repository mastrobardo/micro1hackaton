# Improvement Changelog

Per the hackathon brief: start from a fair baseline and record every meaningful experiment —
what was tried, why, the evidence (same evaluation each time), and the decision. Include
experiments that were removed and what they taught us.

Evaluation is identical for every row: the 10 eval cases + 1 hard case (see `PROGRESS.md`),
run against baseline and solution with the same task text and acceptance checks.

| Metric | Definition |
|---|---|
| Leak count | Real ground-truth sensitive values appearing in {ghost repo + ghost spec}. Lower is better; target 0. |
| Task pass rate | Reverse-compiled real PR applies cleanly AND `yarn lint` + `yarn test` pass AND acceptance check passes. |
| Approvals / task | Human approval gates triggered. |
| Time / task, Cost / task | Wall-clock and token cost. |

---

## Progression

> Status: **not started** — rows below are the planned experiment sequence. Evidence columns
> fill in as each iteration runs. Numbers come from `workspace/eval-report.*`, which is
> generated from the audit log.

| Stage | What we tried and why | Evidence | Decision / learning |
|---|---|---|---|
| **Baseline** | `sed` keyword redaction (`AcmeAir` -> `REDACTED`) + external agent. The "simple script" baseline. | _pending_ | _establishes starting point_ |
| **Iteration 1** | Replace `sed` with **tree-sitter node-scoped** replacement — only rename identifier / string / import nodes, never substrings. Motivated by baseline corrupting unrelated tokens. | _pending_ | _kept / revised / removed_ |
| **Iteration 2** | **Semantic aliases** (`SkyRoute -> FlightDataProviderA`) instead of `REDACTED`. Motivated by the agent flailing with no context for redacted regions. | _pending_ | _kept / revised / removed_ |
| **Iteration 3** | Add the **Verification agent**: leak scan + `yarn lint` gate before the ghost is exposed; fail closed on any residual real value or unresolved `restricted`. | _pending_ | _kept / revised / removed_ |
| **Iteration 4** | **Mapping store as memory** + Entity Discovery agent, so a sensitive entity introduced in a later run still gets a stable alias and is caught. | _pending_ | _kept / revised / removed_ |
| **Iteration 5** | **Reverse patch compiler + PR-consistency agent**: translate ghost PR -> real PR, reject ambiguous mappings, flag unexpected real entities for human review. | _pending_ | _kept / revised / removed_ |
| **Final** | Combine the changes that worked. | _pending_ | _identify the single biggest contributor_ |

## Removed experiments

_(record here: what we tried, why we dropped it, what it taught us about the problem)_

## Main failure mode + hot take

_(to be written after the eval — the observed failure mode turned into a practical lesson for
building more reliable agent workflows)_
