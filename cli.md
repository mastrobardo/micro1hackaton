# ghostc CLI — manual test walkthrough

Copy-paste commands to exercise everything. Run from the repo root with the venv active.
All 7 commands are implemented.

**Automated:** `./scripts/e2e.sh` runs every section below in order (happy paths + the
fail-closed cases) and checks each result — `KEEP_GOING=1` to not stop on the first
mismatch, `SKIP_EVAL=1` to skip the slower eval step.

```bash
cd /Users/davide.arcinotti/learn/hackaton
python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
# optional: real embeddings for the semantic detection signal (~2GB torch)
# pip install -e ".[dev,semantic]"
ghostc --version          # ghostc, version 0.1.0
ghostc --help             # lists 7 commands
```

---

## 1. Validate the privacy config

```bash
ghostc validate-config --config privacy.yaml
```

Expected:

```
OK  privacy.yaml
  mapping_version: 1
  entities: 14  confidential=8  internal=2  restricted=4
```

Break it on purpose to see the schema gate:

```bash
python - <<'EOF'
import yaml, pathlib
c = yaml.safe_load(open("privacy.yaml"))
c["entities"][0].pop("ghost")            # remove a required field
pathlib.Path("/tmp/bad.yaml").write_text(yaml.safe_dump(c))
EOF
ghostc validate-config --config /tmp/bad.yaml   # -> INVALID + reason, exit 1
```

---

## 2. Build the fixture (real repo + synthetic sensitive layer)

```bash
./fixtures/apply.sh
ls workspace/real/src/integrations/    # skyRouteClient.js internalServices.js observability.js
ls workspace/real/infra/               # main.tf variables.tf
```

Needs the base repo at `../node-express-boilerplate`:

```bash
git clone --depth 1 https://github.com/hagopj13/node-express-boilerplate.git ../node-express-boilerplate
```

---

## 3. Compile — dry run (writes nothing)

```bash
ghostc compile --repo workspace/real --dry-run
```

Expected: 85 files scanned, 8 changed, 3 renamed, 13 entities detected
(`vendor_aerofeed` is absent by design — it is the target of the hard eval case).

---

## 4. Compile — for real

```bash
ghostc compile --repo workspace/real
```

Produces:

| Path | Boundary | What |
|---|---|---|
| `workspace/ghost/` | **crosses** | the ghost repo (fresh `git init` + one baseline commit) — mirrors the real tree and nothing else |
| `workspace/ghost-spec.md` | crosses (with the ghost) | entity → alias table, **no real values** — safe to share. Kept a sibling of the ghost, never inside it. |
| `workspace/private/mapping.json` | **never crosses** | 13 frozen `real ↔ ghost` entries + occurrences (holds cleartext real values) |
| `workspace/private/audit.jsonl` | never crosses | one event per step (`real_sha256` only, no cleartext) |

`compile` refuses to run if `--spec` / `--mapping` / `--audit` resolve inside `--out`, and
re-checks the ghost tree for stray metadata before the baseline commit.

Inspect:

```bash
cat workspace/ghost-spec.md
cat workspace/ghost/src/integrations/vendorAClient.js     # renamed from skyRouteClient.js
git -C workspace/ghost log --oneline                      # "ghost baseline (ghostc compile)"

python -c "import json; d=json.load(open('workspace/private/mapping.json')); \
print(len(d['entries']), 'entries'); \
[print(f\"  {e['entity_id']:24} {e['level']:12} -> {e['ghost'] or '<removed>'}\") for e in d['entries']]"

python -c "import json,collections; \
c=collections.Counter(json.loads(l)['event'] for l in open('workspace/private/audit.jsonl')); \
[print(f'  {k}: {v}') for k,v in sorted(c.items())]"
```

---

## 5. Verify (the fail-closed gate — primary metric is 0 leaks)

```bash
ghostc verify --ghost workspace/ghost --mapping workspace/private/mapping.json
```

Expected:

```
PASS  workspace/ghost
  [ok  ] leak_scan — no real value present in the ghost tree
  [ok  ] mapping_leak — no mapping store material in the ghost tree
  [skip] build — yarn / node_modules unavailable (yarn lint not run)
```

Three checks, all fail-closed: **leak_scan** (`\b`-anchored, non-overlapping scan for every
`real` value in the mapping store + every seed spelling in `privacy.yaml`), **mapping_leak**
(any mapping-shaped file — real values / `real_sha256` — anywhere under the ghost), **build**
(`yarn lint`; `skipped` when the toolchain/deps are absent — `--require-build` turns that skip
into a block). Emits `verify.scan` + `verify.pass` / `verify.block` to the audit log; exits 1
on `BLOCK`.

Plant a leak to see it block:

```bash
echo '// SkyRoute Data Ltd' >> workspace/ghost/README.md
ghostc verify --ghost workspace/ghost --mapping workspace/private/mapping.json   # BLOCK, exit 1
ghostc compile --repo workspace/real >/dev/null   # rebuild the clean ghost
```

Ghost JS still parses:

```bash
for f in workspace/ghost/src/integrations/*.js; do node --check "$f" && echo "OK $f"; done
```

---

## 6. Baseline — the fair comparator

Dumb keyword redaction: the "simple script people use today". **Not** privacy-safe —
it exists only so `eval` has something honest to beat.

```bash
ghostc baseline --repo workspace/real
```

Produces `workspace/baseline-ghost/` (fresh `git init` + baseline commit) and
`workspace/baseline-spec.md`. Plain case-sensitive global replace of every configured
spelling → the kebab ghost alias (`REDACTED` for secrets), longest-first. No AST, no
casing engine, no compound splice, no mapping store (not reversible — the point).

See what a keyword `sed` gets wrong:

```bash
grep -n 'SKYROUTE\|BOOKING_CORE\|initvendor-c' workspace/baseline-ghost/src/integrations/*.js
# SKYROUTE_API_KEY / BOOKING_CORE_URL survive (casing variants); initDatadog -> initvendor-c (broken identifier)
```

---

## 7. Eval — the measured win

```bash
ghostc eval --real workspace/real       # builds both comparators, writes the report
```

Expected:

```
metric                                          baseline     compile
--------------------------------------------------------------------
residual entity occurrences (casing-aware)            28           0
strict token leaks (verify / groundtruth method)            0           0
...
PASS: compile residual=0, baseline residual=28
```

Two leak counts per tree: **casing-aware** (the compiler's own matchers run over the
tree in detector mode — the primary metric) and **strict** (`anchored_scan` over
configured spellings — the `verify` / `groundtruth.json` method). Strict reads 0/0
because every configured spelling on this fixture is an exact keyword, so a keyword
`sed` neutralises all of them — that blind spot is why the casing-aware detector is
the primary metric. MVP: no external agent, so task pass rate / approvals / wall-clock
/ tokens are `n/a`.

```bash
cat workspace/eval-report.md
cat workspace/eval-report.csv
python -c "import json,collections; c=collections.Counter(json.loads(l)['event'] \
  for l in open('workspace/private/audit.jsonl') if json.loads(l).get('component')=='eval'); \
  [print(f'  {k}: {v}') for k,v in sorted(c.items())]"
```

---

## 8. Apply-patch — ghost PR diff → real PR diff

The external agent works on the ghost and produces a diff. Translate it back:

```bash
# make a change in the ghost, capture the diff the agent would produce
(cd workspace/ghost && sed -i '' 's#function resolve(serviceKey) {#function resolve(serviceKey) {\
  console.log(process.env.SERVICE_A_URL);#' src/integrations/internalServices.js \
  && git diff > /tmp/ghost.diff && git checkout .)

ghostc apply-patch --ghost-diff /tmp/ghost.diff --mapping workspace/private/mapping.json
```

The real diff prints to stdout — `service-a` → `booking-core`, `SERVICE_A_URL` →
`BOOKING_CORE_URL`, context lines translated too so it applies. Summary (entities resolved,
any `LOSSY` multi-word names) goes to stderr. Add `--out real.diff` to write it, or
`--apply --real <repo>` to land it on a branch (`git apply --3way`).

Fail-closed rejects (exit 1, `patch.rejected` audit, nothing written):

```bash
printf '%s\n' '--- a/x' '+++ b/x' '@@ -1 +1 @@' '+use service-z here' > /tmp/bad.diff
ghostc apply-patch --ghost-diff /tmp/bad.diff --mapping workspace/private/mapping.json
# REJECTED: unmapped ghost-alias-shaped token: service-z

printf '%s\n' '--- a/x' '+++ b/x' '@@ -1 +1 @@' '+contact Northwind Airlines' > /tmp/bad2.diff
ghostc apply-patch --ghost-diff /tmp/bad2.diff --mapping workspace/private/mapping.json
# REJECTED: unexpected real entity in the ghost diff: client_northwind
```

---

## 9. Determinism

Recompiling yields an identical mapping (bar timestamps):

```bash
cp workspace/private/mapping.json /tmp/m1.json
ghostc compile --repo workspace/real >/dev/null
python -c "
import json
def norm(p):
    d=json.load(open(p)); d.pop('updated',None); d.pop('created',None)
    for e in d['entries']: e.pop('first_seen_run',None)
    return json.dumps(d,sort_keys=True)
print('identical' if norm('/tmp/m1.json')==norm('workspace/private/mapping.json') else 'DRIFT')
"
```

---

## 10. Approval gate

`compile` refuses to run while a `restricted` entity from `discover`/`human` has no
`approved_by`:

```bash
python - <<'EOF'
import yaml, pathlib
c = yaml.safe_load(open("privacy.yaml"))
c["entities"].append({"id":"disc_test","real":"SomeClient","kind":"client",
    "level":"restricted","strategy":"synthetic_id","ghost":"client-z","source":"discovered"})
pathlib.Path("/tmp/pending.yaml").write_text(yaml.safe_dump(c))
EOF
ghostc compile --repo workspace/real --config /tmp/pending.yaml   # -> BLOCKED ..., exit 1
```

---

## 11. Discover — candidate scoring / entity proposal

Scans the real repo, scores every sensitive-entity candidate, proposes the unconfigured ones.
Writes `workspace/private/candidates.jsonl` + `discover.*` audit events. Never edits the repo.

```bash
ghostc discover --repo workspace/real
```

Expected (abridged):

```
files scanned:  85
candidates:     15  (auto 9  review 6  ignore 0)
semantic:       n-gram fallback          # or "sentence-transformers" with the [semantic] extra

Datadog                    →  1.00  exact + package / import + identifier token [auto]   vendor_datadog
SkyRoute Data Ltd          →  1.00  exact + package / import + identifier token [auto]   vendor_skyroute
Northwind Airlines         →  1.00  exact + package / import + identifier token [review] client_northwind   # restricted → review
Meridian Aero Systems      →  0.99  declared alias + identifier token + structural shape [review] (new)
gw.prod.contoso.internal   →  0.83  identifier token + structural shape                  [review] (new)

proposed entities (not in privacy.yaml): 2
  Meridian Aero Systems       0.99  vendor/internal            x93  [review]
  gw.prod.contoso.internal    0.83  infra_identifier/confidential  x8   [review]

recall (configured entities re-found from code): 100%
```

`Meridian` and `Contoso` live in `src/integrations/adversary.js` and are **not** in
`privacy.yaml` — `discover` finds them from code alone (alias list, `@meridianaero/flight-sdk`,
env-var laundering, `const flightProvider = client` chains, base64). It does **not** propose
`helmet` / `moment` / `swagger-jsdoc` / other OSS libraries.

### Threshold-driven compile

`compile` runs the same scan. Default (`detection.auto_alias: false` in `privacy.yaml`): the
ghost tree is byte-identical to the matcher-only output; `review` candidates go to
`workspace/private/candidates.jsonl` + `compile.candidate_review` audit. Turn it on to
neutralise the proposals too:

```bash
sed 's/auto_alias: false/auto_alias: true/' privacy.yaml > /tmp/aa.yaml
ghostc compile --repo workspace/real --config /tmp/aa.yaml --dry-run
# -> entities: 14  (adds disc_meridian_aero_systems -> vendor-e, x87 occurrences)
# a discovered *restricted* proposal would BLOCK instead, pending approved_by
```

Tune `detection.auto_threshold` / `review_threshold` in the `detection:` block, or pass
`ghostc discover --threshold 0.3` to widen the review net for one run.

**Import specifiers are kept, not aliased.** `require('@meridianaero/flight-sdk')` stays
verbatim (a renamed package would not resolve in the ghost) — `compile` reports it under
`import specifiers kept: N`, lists it in `workspace/ghost-spec.md` → "Dependency names left
un-aliased", and emits `compile.import_specifier_kept`. First-party specifiers (`./x`) still
rewrite. If a *seed* entity name is in a specifier, `compile` warns that `verify` will BLOCK —
set `rewrite_imports: true` on that entity, or exclude the file.

## 12. Screen — the outbound gate for entities the config never named

`compile` and `compile-spec` are **closed-world**: they substitute the entities
`privacy.yaml` + `mapping.json` name, and their fail-closed leak scan looks for those same
real spellings. A partner nobody ever configured is invisible to both and crosses
untouched. `screen` is the second gate — it scores the compiler's *output*, so every
finding is by construction something the closed world did not cover.

```bash
# the clean path: the seeded spec compiles and screens clean
ghostc compile-spec --task specs/001-add-companyx-integration.md \
    --config fixtures/webapp/privacy.webapp.yaml \
    --mapping .ghostc/webapp-private/mapping.json --out /tmp/ghost-task.md
ghostc screen --text /tmp/ghost-task.md \
    --config fixtures/webapp/privacy.webapp.yaml \
    --mapping .ghostc/webapp-private/mapping.json \
    --candidates .ghostc/webapp-private/candidates.jsonl
# screen:      CLEAN  (/tmp/ghost-task.md, mode=block)
# findings:    0 flagged / 0 scored
```

Now the spec that exists to be blocked (`specs/002-onboard-halcyon-cargo.md` — a ticket
naming a partner that is *not* in the config):

```bash
ghostc compile-spec --task specs/002-onboard-halcyon-cargo.md \
    --config fixtures/webapp/privacy.webapp.yaml \
    --mapping .ghostc/webapp-private/mapping.json --out /tmp/h.md
ghostc screen --text /tmp/h.md --config fixtures/webapp/privacy.webapp.yaml \
    --mapping .ghostc/webapp-private/mapping.json \
    --candidates .ghostc/webapp-private/candidates.jsonl ; echo "exit=$?"
```

```
screen:      BLOCK  (/tmp/h.md, mode=block)
findings:    4 flagged / 4 scored
adjudicator: off

  surface                                 score  action  kind/level                     evidence
  hal_live_9f8e7d6c5b4a3210                0.55  review  secret/restricted              structural shape
  HAL-CF-2026-01                           0.45  review  infra_identifier/confidential  structural shape
  gw.prod.halcyon.internal                 0.45  review  domain/confidential            structural shape
  dispatch.lead@halcyonfreight.example     0.35  review  person/restricted              structural shape

BLOCKED: 4 unscreened finding(s) in the outbound /tmp/h.md; strongest: structural shape @ 0.55
exit=1
```

`ghostc screen` is the deterministic layer only — `ghostc` proper stays LLM-free. Inside
the agent workflow the same call gets a **client-side LLM adjudicator**
(`client_agent/screen_llm.py`), which is shown the real task and the ghost task and asked
which spellings still refer to something real. On the same input it adds:

```
  hal_live_9f8e7d6c5b4a3210                0.81  review  secret/restricted   llm + structural shape
  ...
  Halcyon Freight                          0.58  review  vendor/internal     llm
  HalcyonClient                            0.51  review  vendor/internal     llm
  halcyonClient.js                         0.45  review  vendor/internal     llm
```

The last three are the point. The deterministic detector proposes an unconfigured entity
only from an **anchor** (a scoped package, an internal host, a declared alias list, graph
taint) — which is exactly what keeps `helmet` and `swagger-jsdoc` out of `discover`'s
proposals, and exactly why a partner's name in an English sentence is invisible to it.

### The rules that keep the model honest

- **It may accuse, never decide.** Every surface it names is re-anchored into the outbound
  text with `anchored_scan` before it can score — a claim that only exists in the real half
  of its prompt, or in its imagination, is dropped and counted (`screen_llm_dropped`).
- **Its signal is capped at 0.60**, below `detection.auto_threshold`. An accusation can send
  something to human review; it can never clear or transform anything. Nor can any other
  screen signal: none of them are *hard* signals, so `classify` can only return
  `review` / `ignore` here.
- **Availability never weakens the gate silently.** `--screen-llm best-effort` (default)
  runs it when a client key is present and records `screen_llm: skipped` when it is not —
  the deterministic layer still gates. `--screen-llm required` refuses to run without a
  real model; `off` removes the layer.

### Policy + the review loop

```bash
ghostc screen --text /tmp/h.md ... --mode warn      # score and report, never gate
ghostc screen --text /tmp/h.md ... --threshold 0.6  # raise the bar for one run
ghostc screen --text /tmp/h.md ... --out workspace/private/screen-findings.jsonl
ghostc-review --candidates workspace/private/screen-findings.jsonl   # triage them
```

The findings file is the `Candidate` shape, so the session-9 review board reads it with no
new code. A reviewer `ignore` in `decisions.jsonl` suppresses that surface permanently
(`--decisions <path>`); an `accept` deliberately keeps blocking — an accepted entity belongs
in `privacy.yaml`, and until it is there the compiler still cannot substitute it.

**`restricted` never crosses unreviewed.** The email shape weighs 0.35 — under
`review_threshold` — because in a *repo* an address is usually a package author. In an
outbound ticket it is a person, so a structural hit at a `restricted` level is queued even
when the noisy-OR score is below the line. (That floor is deliberately not extended to the
adjudicator: a shape is a fact about the text, a model's claim is an opinion.)

## 13. Agent workflow — spec file → ghost branch → consultancy develops (reduced flow)

Needs the `[agents]` extra (`pip install -e ".[agents]"`); offline with `--consultancy-backend stub`.

```bash
# build the ghost repo + mapping the flow reads (boundary-internal -> gitignored .ghostc/,
# NOT under ../ghostc-demo/ next to the ghost tree). workspace/ is deprecated.
./fixtures/webapp/apply.sh                     # -> ../ghostc-demo/real
ghostc compile --repo ../ghostc-demo/real --config fixtures/webapp/privacy.webapp.yaml \
    --out ../ghostc-demo/ghost --spec ../ghostc-demo/ghost-spec.md \
    --mapping .ghostc/webapp-private/mapping.json \
    --audit  .ghostc/webapp-private/audit.jsonl \
    --candidates .ghostc/webapp-private/candidates.jsonl

# a spec file lives in specs/ ; task-id in its header must be boundary-neutral
# (it becomes the ghost branch name the consultancy side can see).
client-agent start 001-add-companyx-integration --consultancy-backend stub
# first run also sets up, beside ../ghostc-demo/ghost:
#   ghost.git/          bare "origin" + post-receive hook   (the git-server stand-in)
#   ghost-consultancy/  the consultancy's own clone of ghost.git
# plan -> compile_spec (CompanyX -> PartnerA, Northwind -> Client A, ... ; leak-scanned, fail-closed)
#      -> handoff: in ../ghostc-demo/ghost, branch ghostc/task/001-add-second-provider,
#                  commit TASK.md as `ghostc-client`, `git push -f origin`  ── fires ──▶
#            └─ ghost.git/hooks/post-receive:
#               consultancy-agent start --repo ../ghostc-demo/ghost-consultancy --branch <ref>
#               (commits as `Consultancy Dev`, pushes)
#      -> await_consultancy: fetch the branch back into ../ghostc-demo/ghost, record it
#      -> emit_metrics   (STOP — no ghost PR, no reverse-patch, no real PR)

git -C ../ghostc-demo/ghost log --stat ghostc/task/001-add-second-provider   # inspect it
```

Two git identities on the branch: `ghostc-client <client@ghostc.local>` (the `task:` handoff
commit) and `Consultancy Dev <dev@consultancy.example>` (the `impl:` commit — override with
`CONSULTANCY_GIT_NAME` / `CONSULTANCY_GIT_EMAIL`).

`--full` runs the whole pipeline instead (ghost PR → reverse-patch → verify → consistency →
real-repo PR; still uses a synthesized `LocalBareForge` under `.ghostc/agent`). The
consultancy side uses `role="consultancy"` for its Claude key + LangSmith project
(`ghostc-consultancy`); the client uses `role="client"`. Set `CONSULTANCY_ANTHROPIC_API_KEY` /
`CLIENT_ANTHROPIC_API_KEY` (or one bare `ANTHROPIC_API_KEY`) and the matching `*_LANGSMITH_*`
vars in `.env` — see `.env.example`.

```bash
ghostc-agent print-graph        # regenerate client_agent/graph.md (full + reduced diagrams)
```
