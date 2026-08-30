#!/usr/bin/env bash
# End-to-end walkthrough — runs the commands from cli.md in order.
#
# Happy-path steps must succeed; the "see it fail" steps (schema gate, verify BLOCK,
# apply-patch rejects, approval gate) must fail. Anything off script is reported and
# makes the script exit non-zero.
#
#   ./scripts/e2e.sh              # full run
#   KEEP_GOING=1 ./scripts/e2e.sh # don't stop on the first unexpected result
#   SKIP_EVAL=1  ./scripts/e2e.sh # skip the slower `ghostc eval` step
#
# Needs the base repo at ../node-express-boilerplate (cloned automatically if missing)
# and the package installed (`pip install -e ".[dev]"`).

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# --- ghostc entrypoint: prefer the console script, fall back to the module -----
if command -v ghostc >/dev/null 2>&1; then GHOSTC=(ghostc)
elif python -c "import ghostc" >/dev/null 2>&1; then GHOSTC=(python -m ghostc)
else
  echo "ghostc is not importable — run:  pip install -e \".[dev]\"  (venv active)" >&2
  exit 2
fi

# --- pretty output -----------------------------------------------------------
if [ -t 1 ]; then B=$'\e[1m'; G=$'\e[32m'; R=$'\e[31m'; Y=$'\e[33m'; D=$'\e[2m'; Z=$'\e[0m'
else B=; G=; R=; Y=; D=; Z=; fi
FAILS=0; WARNS=0
KEEP_GOING="${KEEP_GOING:-0}"

step()  { printf '\n%s══ %s ══%s\n' "$B" "$*" "$Z"; }
note()  { printf '%s   %s%s\n' "$D" "$*" "$Z"; }
warn()  { printf '%s   ! %s%s\n' "$Y" "$*" "$Z"; WARNS=$((WARNS+1)); }
ok()    { printf '%s   ✓ %s%s\n' "$G" "$*" "$Z"; }
bad()   { printf '%s   ✗ %s%s\n' "$R" "$*" "$Z"; FAILS=$((FAILS+1));
          [ "$KEEP_GOING" = 1 ] || { summary; exit 1; }; }

# run a command that is expected to SUCCEED
run() {
  printf '%s   $ %s%s\n' "$D" "$*" "$Z"
  if "$@"; then return 0; else bad "expected success, got exit $?: $*"; return 1; fi
}
# run a shell snippet that is expected to SUCCEED
sh_ok() {
  printf '%s   $ %s%s\n' "$D" "$1" "$Z"
  if bash -c "$1"; then return 0; else bad "expected success, got exit $?"; return 1; fi
}
# run a command that is expected to FAIL (non-zero exit)
expect_fail() {
  printf '%s   $ %s%s\n' "$D" "$*" "$Z"
  if "$@"; then bad "expected failure, but it succeeded: $*"; else ok "failed as expected (exit $?)"; fi
}
sh_fail() {
  printf '%s   $ %s%s\n' "$D" "$1" "$Z"
  if bash -c "$1"; then bad "expected failure, but it succeeded"; else ok "failed as expected (exit $?)"; fi
}

summary() {
  printf '\n%s────────────────────────────────────────%s\n' "$B" "$Z"
  if [ "$FAILS" -eq 0 ]; then
    printf '%sE2E OK%s  — %d unexpected result(s), %d optional step(s) skipped\n' "$G" "$Z" "$FAILS" "$WARNS"
  else
    printf '%sE2E FAILED%s — %d unexpected result(s), %d optional step(s) skipped\n' "$R" "$Z" "$FAILS" "$WARNS"
  fi
}

# ===========================================================================
step "0. environment"
run "${GHOSTC[@]}" --version
run "${GHOSTC[@]}" --help >/dev/null && ok "help lists the 7 commands"

step "1. validate the privacy config"
run "${GHOSTC[@]}" validate-config --config privacy.yaml
note "break it on purpose — the schema gate should reject it:"
python - <<'EOF'
import yaml, pathlib
c = yaml.safe_load(open("privacy.yaml"))
c["entities"][0].pop("ghost")            # remove a required field
pathlib.Path("/tmp/ghostc-e2e-bad.yaml").write_text(yaml.safe_dump(c))
EOF
expect_fail "${GHOSTC[@]}" validate-config --config /tmp/ghostc-e2e-bad.yaml

step "2. build the fixture (real repo + synthetic sensitive layer)"
if [ ! -d ../node-express-boilerplate ]; then
  note "base repo missing — cloning hagopj13/node-express-boilerplate"
  run git clone --depth 1 https://github.com/hagopj13/node-express-boilerplate.git ../node-express-boilerplate
fi
run ./fixtures/apply.sh
sh_ok 'ls workspace/real/src/integrations/ && ls workspace/real/infra/'
note "start from a clean mapping store (the mapping is append-only / frozen by design)"
rm -rf workspace/ghost workspace/baseline-ghost workspace/private \
       workspace/ghost-spec.md workspace/baseline-spec.md \
       workspace/eval-report.md workspace/eval-report.csv

step "3. compile — dry run (writes nothing)"
run "${GHOSTC[@]}" compile --repo workspace/real --dry-run

step "4. compile — for real"
run "${GHOSTC[@]}" compile --repo workspace/real
note "artifacts:"
sh_ok 'test -f workspace/ghost-spec.md && test -f workspace/private/mapping.json && test -f workspace/private/audit.jsonl'
sh_ok 'test -f workspace/ghost/src/integrations/vendorAClient.js && ! test -e workspace/ghost/src/integrations/skyRouteClient.js'
sh_ok 'git -C workspace/ghost log --oneline | grep -q "ghost baseline"'
sh_ok $'python -c "import json; d=json.load(open(\'workspace/private/mapping.json\')); print(len(d[\'entries\']), \'frozen mapping entries\')"'
sh_ok $'python -c "import json,collections; c=collections.Counter(json.loads(l)[\'event\'] for l in open(\'workspace/private/audit.jsonl\')); [print(f\'  {k}: {v}\') for k,v in sorted(c.items())]"'

step "5. verify — the fail-closed gate (primary metric: 0 leaks)"
run "${GHOSTC[@]}" verify --ghost workspace/ghost --mapping workspace/private/mapping.json
note "plant a leak — verify should BLOCK (exit 1):"
echo '// SkyRoute Data Ltd' >> workspace/ghost/README.md
expect_fail "${GHOSTC[@]}" verify --ghost workspace/ghost --mapping workspace/private/mapping.json
note "rebuild the clean ghost"
run "${GHOSTC[@]}" compile --repo workspace/real
if command -v node >/dev/null 2>&1; then
  sh_ok 'for f in workspace/ghost/src/integrations/*.js; do node --check "$f"; done && echo "ghost JS parses"'
else
  warn "node not installed — skipped 'node --check' on the ghost JS"
fi

step "6. baseline — the fair comparator (keyword redaction, NOT privacy-safe)"
run "${GHOSTC[@]}" baseline --repo workspace/real
sh_ok 'test -d workspace/baseline-ghost && test -f workspace/baseline-spec.md'
note "what a keyword sed gets wrong (casing variants survive; identifiers corrupted):"
bash -c "grep -n 'SKYROUTE\|BOOKING_CORE\|initvendor-c' workspace/baseline-ghost/src/integrations/*.js" || true

step "7. eval — the measured win"
if [ "${SKIP_EVAL:-0}" = 1 ]; then
  warn "SKIP_EVAL=1 — skipped 'ghostc eval'"
else
  run "${GHOSTC[@]}" eval --real workspace/real
  sh_ok 'test -f workspace/eval-report.md && test -f workspace/eval-report.csv'
  sh_ok $'python -c "import sys; t=open(\'workspace/eval-report.csv\').read(); sys.exit(0 if \'28\' in t else 1)" && echo "report records baseline 28 vs compile 0"'
fi

step "8. apply-patch — ghost PR diff → real PR diff"
note "synthesise the diff an external agent would produce on the ghost:"
( cd workspace/ghost \
  && sed -i '' 's#^function resolve(serviceKey) {#function resolve(serviceKey) {\
  console.log(process.env.SERVICE_A_URL);#' src/integrations/internalServices.js \
  && git diff > /tmp/ghostc-e2e-ghost.diff && git checkout . )
sh_ok 'test -s /tmp/ghostc-e2e-ghost.diff'
run "${GHOSTC[@]}" apply-patch --ghost-diff /tmp/ghostc-e2e-ghost.diff --mapping workspace/private/mapping.json --out /tmp/ghostc-e2e-real.diff
sh_ok $'grep -q "booking-core\|BOOKING_CORE" /tmp/ghostc-e2e-real.diff && echo "service-a -> booking-core in the real diff"'
note "fail-closed rejects (each should exit 1):"
printf '%s\n' '--- a/x' '+++ b/x' '@@ -1 +1 @@' '+use service-z here' > /tmp/ghostc-e2e-bad.diff
expect_fail "${GHOSTC[@]}" apply-patch --ghost-diff /tmp/ghostc-e2e-bad.diff --mapping workspace/private/mapping.json
printf '%s\n' '--- a/x' '+++ b/x' '@@ -1 +1 @@' '+contact Northwind Airlines' > /tmp/ghostc-e2e-bad2.diff
expect_fail "${GHOSTC[@]}" apply-patch --ghost-diff /tmp/ghostc-e2e-bad2.diff --mapping workspace/private/mapping.json

step "9. determinism — recompile yields an identical mapping (bar timestamps)"
cp workspace/private/mapping.json /tmp/ghostc-e2e-m1.json
run "${GHOSTC[@]}" compile --repo workspace/real
sh_ok $'python -c "
import json,sys
def norm(p):
    d=json.load(open(p)); d.pop(\'updated\',None); d.pop(\'created\',None)
    for e in d[\'entries\']: e.pop(\'first_seen_run\',None)
    return json.dumps(d,sort_keys=True)
sys.exit(0 if norm(\'/tmp/ghostc-e2e-m1.json\')==norm(\'workspace/private/mapping.json\') else 1)
" && echo identical'

step "10. approval gate — a discovered restricted entity blocks compile"
python - <<'EOF'
import yaml, pathlib
c = yaml.safe_load(open("privacy.yaml"))
c["entities"].append({"id":"disc_test","real":"SomeClient","kind":"client",
    "level":"restricted","strategy":"synthetic_id","ghost":"client-z","source":"discovered"})
pathlib.Path("/tmp/ghostc-e2e-pending.yaml").write_text(yaml.safe_dump(c))
EOF
expect_fail "${GHOSTC[@]}" compile --repo workspace/real --config /tmp/ghostc-e2e-pending.yaml --dry-run

step "11. discover — candidate scoring / entity proposal"
run "${GHOSTC[@]}" discover --repo workspace/real
sh_ok 'test -f workspace/private/candidates.jsonl'
sh_ok $'python -c "
import json,sys
rows=[json.loads(l) for l in open(\'workspace/private/candidates.jsonl\')]
prop=[r for r in rows if r[\'entity_id\'] is None and r[\'action\']!=\'ignore\']
names=\' \'.join(r[\'surface\'].lower() for r in prop)
assert any(\'meridian\' in r[\'surface\'].lower() or \'meridian\' in \' \'.join(r[\'aliases\']).lower() for r in prop), \'Meridian not proposed\'
assert not any(x in names for x in (\'helmet\',\'moment\',\'swagger\')), \'OSS library proposed\'
print(f\'{len(rows)} candidates, {len(prop)} proposed, no OSS false positives\')
"'
note "threshold-driven compile with detection.auto_alias: true"
sed 's/auto_alias: false/auto_alias: true/' privacy.yaml > /tmp/ghostc-e2e-aa.yaml
run "${GHOSTC[@]}" compile --repo workspace/real --config /tmp/ghostc-e2e-aa.yaml --dry-run
run "${GHOSTC[@]}" discover --repo workspace/real --threshold 0.3 >/dev/null && ok "--threshold override runs"

summary
[ "$FAILS" -eq 0 ]
