# Submission docs + the CI phase

## Submission docs (session 7, 2026-08-31)

Four docs written, **no code touched**, `pytest` still 268 pass / 1 skip:

| File | Purpose | Maps to |
|---|---|---|
| `GETTING_STARTED.md` | reproduction guide — clean env → `pip install -e ".[dev]"` → `pytest` → `fixtures/apply.sh` → baseline → `discover`/`compile`/`verify`/`eval` → runnable webapp demo → agent workflow (stub, then Claude). Expected output per step, runtime & cost table, troubleshooting. | brief deliverable 02 |
| `OVERVIEW.md` | one-page project intro: problem / why redaction fails / the pipeline / the 28→0 number / status. The front door. | README companion |
| `VIDEO_SCRIPT.md` | ≤5-min solution-video script. Two columns (screen / narration verbatim). "Record these before you hit record" checklist; live-type only the fast reverse-compile step. Arc: problem+baseline → one execution → comparison → changelog → removed experiment → hot take. | brief deliverable 03 prep |
| `ARCHITECTURE.md` | **restructured** (all prior component-contract content kept): new intro "This is a reproducibility-first POC" (table of what's simulated: forge, issue tracker, agent, CI, approval — and why) + new section "Where a production integration differs" (per-shortcut → production form → what changes concretely). | framing + CI spec |

The "Where a production integration differs" table in `ARCHITECTURE.md` is the **spec for the
CI session** — forge/PRs, webhook vs `post-receive` hook, Jira input, CI eval gate, PR-review
approval, per-service secrets.

## NEXT PHASE — CI (deferred to its own session)

**Goal:** judges see the workflow's output as **opened pull requests** on a real forge (ghost
PR + reverse-compiled real PR) as normal forge objects. They will **not** run the Actions
themselves — the PRs, plus `workspace/eval-report.md` + `metrics/agent-runs.jsonl` as build
artifacts / status checks, are what they inspect.

Planned work (nothing built yet):
- GitHub Actions (or equiv) running `ghostc compile` + `client-agent start` +
  `client-agent open-real-pr` on push / `workflow_dispatch`; `--consultancy-backend stub` is
  the deterministic CI path, real Claude behind a secret + a dispatch input.
- Swap `bridge.forge.LocalBareForge` → a GitHub backend behind the existing `Forge` seam so
  ghost/real branches become **real PRs** (PR body carries substitution count + `lossy` flags).
- Publish eval report + metrics JSONL as artifacts; **fail the job on a leak-count regression**.
- `pytest` + `ghostc eval` stay green offline; stub stays the default CI backend.

Open decision for that session: which forge (throwaway GitHub repo under the user's account
vs. self-hosted Gitea), and whether the real-Claude run happens in-CI or as a documented
local step whose PR is pushed.

## PHASE AFTER CI — human review board (Streamlit), MVP

Confirmed session 7: **MVP scope, own session, after the CI phase.**

Today the human gate = hand-editing `approved_by:` / entities into `privacy.yaml`
(`ghostc/config.py::entities_needing_approval`; `compile.py` blocks unapproved `restricted`
proposals). The board replaces that with a reviewer UI whose decisions also feed process
tuning ("the process generates data that improves the process").

MVP pieces (full detail in `SESSION_TODO.md` → "SESSION AFTER CI — human review board"):
- `ghostc/review/store.py` — append-only `decisions.jsonl` (proposed vs reviewer action,
  level, approver, note, ts, op-id; latest supersedes, history kept = revision) + `summarize()`
  scorer-vs-human agreement.
- `ghostc-review` Streamlit app, `[review]` optional extra: **Review** tab (candidates →
  accept/ignore/escalate, writes `decisions.jsonl`) + **Process data** tab (metrics / eval /
  audit counts / agreement, read-only).
- `ghostc compile` + `discover` gain `--decisions <path>`; no file → current behavior
  (backward compatible). New `review.decision_recorded` audit event.
- `fixtures/decisions.example.jsonl` seeded so repro doesn't need Streamlit.
- Framing tie-in: this is the concrete form of "monitoring is first-class" + the Improvement
  Changelog — reviewer decisions vs. the scorer's proposals → threshold tuning, per-signal
  precision over runs.

Reproducibility guard: the pipeline consumes the decisions FILE; the app only writes it. A
judge reproduces the ghost from the seeded file without running the UI.

## Submission thesis (session 7, user's framing)

"Reduce the surface for **unintentional** data leaks, and prove third-party models can be used
on private code without disclosing what's private." Scoped: defeats *accidental* disclosure
and makes it measurable (leak count, target 0); NOT a guarantee against structural correlation
by a motivated adversary (`THREAT_MODEL.md` line ~49 already says this). Surfaced in
`OVERVIEW.md` ("## The goal"), `README.md` blockquote, `ARCHITECTURE.md` POC intro,
`GETTING_STARTED.md`, `VIDEO_SCRIPT.md` intro + hot-take.
