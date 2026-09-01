#!/usr/bin/env bash
# Build the submission zip.
#
#   ./scripts/make-submission.sh            # -> dist/ghostc-submission-<sha>.zip
#   OUT=/tmp/x.zip ./scripts/make-submission.sh
#
# Contents = every file git tracks or would track (`git ls-files -co --exclude-standard`),
# read from the WORKING TREE so uncommitted edits and new files are included, plus an
# `evidence/` directory holding the generated artifacts that back the report's claims.
#
# Ground rule 08 — credentials and private information stay out of the submission. That is
# enforced three ways, not assumed:
#   1. the file list comes from git's ignore rules, so `.env`, `.venv/`, `workspace/` and
#      `.ghostc/` cannot be swept in by a glob;
#   2. a pre-flight scan refuses to build if a live-key pattern appears in any staged file;
#   3. a post-build scan re-checks the actual zip and deletes it on any hit.
#
# The mapping store is deliberately NOT included: THREAT_MODEL.md says it must never cross a
# boundary, and a submission zip is a boundary. The audit log IS included — it carries
# `real_sha256`, never a real value.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

B=$'\e[1m'; G=$'\e[32m'; R=$'\e[31m'; Y=$'\e[33m'; DIM=$'\e[2m'; Z=$'\e[0m'
say()  { printf '\n%s== %s%s\n' "$B" "$*" "$Z"; }
ok()   { printf '  %s✓%s %s\n' "$G" "$Z" "$*"; }
warn() { printf '  %s!%s %s\n' "$Y" "$Z" "$*"; }
die()  { printf '\n%sABORT:%s %s\n\n' "$R" "$Z" "$*" >&2; exit 1; }

SHA="$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
DIRTY=""; git diff --quiet 2>/dev/null || DIRTY="-dirty"
OUT="${OUT:-$ROOT/dist/ghostc-submission-${SHA}${DIRTY}.zip}"
STAGE="$(mktemp -d)/ghostc"
trap 'rm -rf "$(dirname "$STAGE")"' EXIT

# Live-credential shapes. Deliberately NOT matching the synthetic detector fixtures
# (`sk_live_northwind_…`, `mas_live_…`, `AKIA0123456789ABCDEF`) which are test data.
KEYPAT='sk-ant-api[A-Za-z0-9_-]{15,}|lsv2_(pt|sk)_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----'

# ------------------------------------------------------------------ 1. collect the files

say "1. collect (git ignore rules decide — not a glob)"
# read into an array without `mapfile` — macOS ships bash 3.2
FILES=()
while IFS= read -r f; do [ -n "$f" ] && FILES+=("$f"); done \
  < <(git ls-files --cached --others --exclude-standard)
[ "${#FILES[@]}" -gt 0 ] || die "no files listed — is this a git repo?"
ok "${#FILES[@]} files"

for f in "${FILES[@]}"; do
  case "$f" in
    .env|*/.env|.env.local|*/.env.local) die "refusing: '$f' is in the file list" ;;
  esac
done
ok "no .env in the list"

# Tracked, but not part of what we are submitting. Not secrets — just noise:
# the organisers' own brief, and the odd stray artifact.
KEEP=()
DROPPED=0
for f in "${FILES[@]}"; do
  case "$f" in
    *"First Hackathon"*.pdf|*.zip) DROPPED=$((DROPPED + 1)); continue ;;
  esac
  KEEP+=("$f")
done
FILES=("${KEEP[@]}")
[ "$DROPPED" -gt 0 ] && ok "dropped $DROPPED non-submission file(s) (the brief PDF)"

say "2. pre-flight secret scan"
HITS="$(grep -lIE "$KEYPAT" -- "${FILES[@]}" 2>/dev/null || true)"
[ -z "$HITS" ] || die "live-credential pattern in:"$'\n'"$HITS"
ok "no live-credential patterns in any staged file"

# ------------------------------------------------------------------------- 3. stage

say "3. stage"
mkdir -p "$STAGE"
for f in "${FILES[@]}"; do
  mkdir -p "$STAGE/$(dirname "$f")"
  cp -p "$f" "$STAGE/$f"
done
ok "source tree staged"

# ---------------------------------------------------------------------- 4. evidence

say "4. evidence (ground rule 09 — claims connected to artifacts)"
EV="$STAGE/evidence"
mkdir -p "$EV"
add_ev() {  # add_ev <src> <dest-name> <what it is>
  if [ -f "$1" ]; then cp -p "$1" "$EV/$2"; ok "$2 — $3"
  else warn "missing: $1  (regenerate: $4)"; fi
}
add_ev workspace/eval-report.md        eval-report.md        "primary metric, per-case table" "ghostc eval --real workspace/real"
add_ev workspace/eval-report.csv       eval-report.csv       "aggregate metrics"              "ghostc eval --real workspace/real"
add_ev workspace/eval-report-cases.csv eval-report-cases.csv "13 scored cases, machine-readable" "ghostc eval --real workspace/real"
add_ev workspace/ghost-spec.md         ghost-spec.md         "what crosses the boundary"      "ghostc compile --repo workspace/real"
add_ev workspace/private/audit.jsonl   audit-pipeline.jsonl  "pipeline audit trail (hashes only)" "ghostc compile/eval"
add_ev .ghostc/webapp-private/audit.jsonl audit-agent-run.jsonl "the real Claude agent round-trip" "client-agent start --consultancy-backend claude"
add_ev metrics/agent-runs.jsonl        agent-runs.jsonl      "one row per agent run"          "client-agent start / open-real-pr"

cat > "$EV/README.md" <<'EOF'
# Evidence

Generated artifacts backing the claims in `README.md` and `CHANGELOG.md`. Everything here
is reproducible from a clean checkout — `GETTING_STARTED.md` gives the exact commands.

| file | what it shows | regenerate with |
|---|---|---|
| `eval-report.md` | the primary metric and the 13-case table; baseline 7/13 clean vs `compile` 13/13, residual 28 → 0 | `ghostc eval --real workspace/real --config privacy.yaml` |
| `eval-report.csv` | the aggregate metric rows | same |
| `eval-report-cases.csv` | one row per case, machine-readable | same |
| `ghost-spec.md` | exactly what crosses the privacy boundary, incl. surfaces left verbatim pending review | `ghostc compile --repo workspace/real --config privacy.yaml` |
| `audit-pipeline.jsonl` | every deterministic step; the eval report is derived from this | `ghostc compile` / `eval` |
| `audit-agent-run.jsonl` | the real Claude agent round-trip, including a fail-closed **block** and its retry | `client-agent start <spec> --consultancy-backend claude` |
| `agent-runs.jsonl` | one row per agent run — outcome, wall-clock, tests, build | the agent workflow |

Rendered, human-readable versions of the last two are in **`../trajectories/`**.

## Deliberately not included

**`workspace/private/mapping.json`** — the mapping store. `THREAT_MODEL.md` lists it as the
one artifact that must never cross a boundary, because it holds `real -> ghost` in cleartext.
A submission zip is a boundary, so it is omitted. Every entity in it is fictional and it
regenerates in seconds (`ghostc compile`), so nothing here depends on shipping it.

The audit logs above *are* included: they carry `real_sha256`, never a real value. The entity
*ids* they reference (`vendor_skyroute`) come from `privacy.yaml`, which is itself part of the
submission — they are labels chosen by the operator, not extracted secrets.

**The base fixture** (`hagopj13/node-express-boilerplate`, MIT) is not vendored — it is
unmodified upstream and `GETTING_STARTED.md` step 1 clones it. Ground rule 02: everything in
this zip was written for the competition; that repo is the one pre-existing input.

**Generated trees** (`workspace/real`, `workspace/ghost`, `workspace/baseline-ghost`,
`../ghostc-demo/`) are omitted — they are outputs, rebuilt by `./fixtures/apply.sh` and the
pipeline commands.
EOF
ok "evidence/README.md — what each artifact proves, and what is omitted and why"

# ------------------------------------------------------------------------ 5. manifest

say "5. entry point for judges"
cat > "$STAGE/START-HERE.md" <<EOF
# Start here

**ghostc** — a privacy-safe bridge that lets external AI coding agents work on private code
without any sensitive value crossing the company trust boundary.

Built for the micro1 Agentic Workflows Hackathon. Commit \`$SHA\`, packaged $(date -u '+%Y-%m-%d %H:%M UTC').

## Read in this order

1. **\`README.md\`** — the user, the bottleneck, the result.
2. **\`GETTING_STARTED.md\`** — reproduction from a clean environment: exact commands,
   expected output, runtimes and costs. **This is the one to run.**
3. **\`CHANGELOG.md\`** — the Improvement Changelog: baseline → final, each iteration tied
   to evidence, plus removed experiments and the hot take.
4. **\`trajectories/\`** — one agent trajectory per agent (deliverable 04).
5. **\`evidence/\`** — the generated artifacts behind every number above.

## The 60-second version

\`\`\`bash
git clone --depth 1 https://github.com/hagopj13/node-express-boilerplate.git ../node-express-boilerplate
python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
./fixtures/apply.sh
ghostc eval --real workspace/real --config privacy.yaml
\`\`\`

Expect: **baseline 28 residual leaks / 7 of 13 cases clean** vs **compile 0 / 13 of 13**.
Then \`pytest -q\` → 324 passed, 2 skipped. Neither needs an API key or a network call
after the clone.

## Note on credentials

No credentials are in this archive (ground rule 08). \`.env.example\` is a template with
empty values; the mapping store is omitted on purpose — see \`evidence/README.md\`.
EOF
ok "START-HERE.md"

# --------------------------------------------------------------------------- 6. zip

say "6. zip"
mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"
( cd "$(dirname "$STAGE")" && zip -q -r -X "$OUT" "$(basename "$STAGE")" )
ok "$OUT"

# ------------------------------------------------------------------------- 7. verify

say "7. verify the artifact itself"
LIST="$(unzip -Z1 "$OUT")"
N="$(printf '%s\n' "$LIST" | wc -l | tr -d ' ')"

for bad in '/\.env$' '/\.venv/' '/workspace/' '/\.ghostc/' 'mapping\.json' '/\.git/'; do
  if printf '%s\n' "$LIST" | grep -qE "$bad"; then
    rm -f "$OUT"; die "zip contains '$bad' — deleted the archive"
  fi
done
ok "no .env, .venv, workspace/, .ghostc/, mapping.json or .git/"

VERIFY="$(mktemp -d)"
unzip -qq "$OUT" -d "$VERIFY"
if grep -rlIE "$KEYPAT" "$VERIFY" >/dev/null 2>&1; then
  rm -f "$OUT"; rm -rf "$VERIFY"; die "live-credential pattern inside the zip — deleted it"
fi
rm -rf "$VERIFY"
ok "post-build secret scan clean"

printf '\n%s%s%s\n' "$B" "$OUT" "$Z"
printf '  %s files · %s\n' "$N" "$(du -h "$OUT" | cut -f1)"
[ -n "$DIRTY" ] && printf '  %sbuilt from a dirty tree — commit first if you want a clean sha%s\n' "$Y" "$Z"
printf '\n'
