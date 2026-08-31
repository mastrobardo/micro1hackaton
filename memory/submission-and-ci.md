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

## CI PHASE — DONE (session 8, 2026-08-31)

`.github/workflows/agent-workflow.yml` + `scripts/ci/*` + `client_agent/publish.py` +
`tests/test_ci_publish.py` (13). `pytest` 281 pass / 1 skip.

**Decisions (user, session 8):**
- **Publish step on the verified reduced flow**, NOT a `Forge`-seam rebuild. The reduced flow
  (`client-agent start` / `open-real-pr` — the demo path) never used `bridge.forge`; that seam
  is only in the full `run-task` simulator pipeline. So CI keeps the verified code untouched
  and adds `scripts/ci/publish-prs.sh` = `git push` the finished branches + `gh pr create`.
- **Two PUBLIC throwaway repos under `mastrobardo`**: `ghostc-demo-ghost`, `ghostc-demo-real`.
- **Stub consultancy in CI**; real Claude only via `workflow_dispatch` input +
  `ANTHROPIC_API_KEY` secret.

**What shipped:**
- `checks` job — offline gate: `compile`/`verify`/`eval`/`pytest` + `scripts/ci/check_leak_gate.py`
  (fails if compile residual > 0, or baseline no longer > compile). Eval report +
  `metrics/agent-runs.jsonl` uploaded as artifacts.
- `roundtrip` job — reduced flow (stub) → `publish-prs.sh` force-pushes `main` + the ghost
  `ghostc/task/<id>` and real `ghostc/real/<decoded>` branches to the demo repos and opens/updates
  the two PRs. `if:` skips it on `pull_request` and when a dispatch sets `run_roundtrip=false`.
  Needs `GH_PAT` (a `mastrobardo` PAT, `repo` scope — `GITHUB_TOKEN` is single-repo only).
- `consultancy_agent/agent.py::_scripted_impl` — now writes **one small real file** (the first
  `src/…`/`test/…` path the sanitized TASK.md names, with a stub class) **plus** `IMPL_NOTES.md`,
  so the fully-offline reverse (`open-real-pr` with `--consultancy-backend stub`) produces a
  non-empty real PR. Previously it wrote only `IMPL_NOTES.md` → `open-real-pr` hit `NotReady`.
- `client_agent/publish.py` — **stdlib-only** (no `[agents]` extra): `resolve` (task_id /
  ghost_branch / real_branch / base from the newest metrics rows), `title`, `body` (ghost +
  real PR markdown). Unit-tested with no network / no `gh`.
- `scripts/ci/`: `common.sh` (shared vars + `ci_stage_and_compile` / `ci_run_flow` / `pub`
  helpers; `GHOST_REMOTE`/`REAL_REMOTE` overridable for a local dry-run or self-hosted forge),
  `init-demo-repos.sh` (one-time: `gh repo create` + seed `main`), `publish-prs.sh`,
  `run-local.sh` (dry-run the roundtrip locally), `check_leak_gate.py`.

**Verified locally** end-to-end: bare-repo stand-ins for the two GitHub repos + a fake `gh` on
PATH → `publish-prs.sh` pushes both branches, updates `main`, invokes `gh pr create` with the
right body. Both PR diffs are minimal (ghost: `TASK.md` + `IMPL_NOTES.md` +
`partnerAClient.js`; real: `PR_BODY.md` + `companyXClient.js`), `entities_resolved =
[vendor_companyx]`, real branch leak-scan clean.

**Known / watch:** `publish-prs.sh` force-pushes `main` on the demo repos every run because
`ghostc compile` mints a fresh root commit each time. The repos are disposable so this is
fine; the stable-base fix is a reproducible `ghostc compile` baseline commit (fixed
`GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE`).

**Manual, one-time (user):** `gh auth switch` to `mastrobardo` (the local `gh` is logged into
`davide-arcinotti_iagl`) → `scripts/ci/init-demo-repos.sh` → add repo secrets `GH_PAT` and
(for live runs) `ANTHROPIC_API_KEY`.

## HUMAN REVIEW BOARD — DONE (session 9, 2026-08-31)

`ghostc/review/{store,model,app}.py` + `--decisions` on `compile`/`discover` +
`fixtures/decisions.example.jsonl` + `tests/test_review_{store,model,decisions,app}.py`
(~22) + `[review]` extra + `ghostc-review` script + schema (`review.decision_recorded`
event, `review` component). `pytest` ~302/1.

- **`DecisionStore`** (`store.py`) — append-only `decisions.jsonl`, one record per key
  (`entity_id`, or `sha256:<surface>` for an unconfigured proposal), latest-wins + full
  history. `accepted()` / `ignored_keys()` / `cleared_restricted()` (latest `accept` +
  `approved_by`) / `summarize()` (scorer-vs-human agreement: scorer flagged ∧ human kept,
  or both ignore). `record(..., audit=AuditLog)` emits a **hash-only**
  `review.decision_recorded` (component `review`).
- **`ghostc compile --decisions <path>`** — `_augment_with_decisions` in `compile.py`:
  accepted unconfigured surface → synthetic `source: human` entity (reuses the
  `_augment_with_auto_candidates` pattern); `accept` + `approved_by` for an existing
  restricted entity → sets `approved_by` on it. CLI `pending` gate subtracts
  `cleared_restricted()`. **No `--decisions` = byte-identical to before.**
- **`discover --decisions`** — annotates each proposal with the reviewer's call +
  prints the agreement stat.
- **`ghostc-review`** (`app.py`, `[review]` extra = `streamlit>=1.30`) — `main()` re-execs
  `streamlit run app.py`. Review tab (accept / ignore / escalate → `decisions.jsonl`, live
  `privacy.yaml` delta) + Process-data dashboard tab (metrics / eval-report.csv /
  audit-event counts / agreement — read-only). Decision logic in `model.py` (streamlit-free,
  unit-tested).
- **Seeded** `fixtures/decisions.example.jsonl` — accept *Meridian* → `vendor-e` (0
  residue), ignore *Contoso* (0.83). `ghostc compile --repo workspace/real --config
  privacy.yaml --decisions fixtures/decisions.example.jsonl` reproduces the reviewed ghost
  with no Streamlit.

Design (user, session 7): the pipeline consumes the **file**, the UI only writes it —
keeps the reviewed ghost reproducible offline. This is the concrete form of "monitoring is
first-class" — reviewer decisions vs. the scorer's proposals → the agreement stat feeds
threshold tuning over runs.

**Known:** `cleared_restricted()` ignores the entity's level (only ever intersected with
`entities_needing_approval`, so harmless). `model.entity_from_decision` ≈
`compile._augment_with_decisions` synthetic-entity build — keep in sync or unify later.

## Submission thesis (session 7, user's framing)

"Reduce the surface for **unintentional** data leaks, and prove third-party models can be used
on private code without disclosing what's private." Scoped: defeats *accidental* disclosure
and makes it measurable (leak count, target 0); NOT a guarantee against structural correlation
by a motivated adversary (`THREAT_MODEL.md` line ~49 already says this). Surfaced in
`OVERVIEW.md` ("## The goal"), `README.md` blockquote, `ARCHITECTURE.md` POC intro,
`GETTING_STARTED.md`, `VIDEO_SCRIPT.md` intro + hot-take.
