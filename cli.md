# ghostc CLI — manual test walkthrough

Copy-paste commands to exercise everything that works today. Run from the repo root
with the venv active. `discover` / `apply-patch` / `eval` are still stubs (see the last
section).

```bash
cd /Users/davide.arcinotti/learn/hackaton
python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
ghostc --version          # ghostc, version 0.1.0
ghostc --help             # lists 6 commands
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

Expected: 84 files scanned, 7 changed, 3 renamed, 13 entities detected
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

## 6. Determinism

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

## 7. Approval gate

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

## 8. Stubs (not implemented yet)

Each exits non-zero with a pointer to `PROGRESS.md`:

```bash
ghostc discover    --repo workspace/real
ghostc apply-patch --ghost-diff /dev/null --real workspace/real
ghostc eval
```
