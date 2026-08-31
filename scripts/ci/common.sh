# shellcheck shell=bash
# Shared settings + helpers for the ghostc CI scripts. `source` this; do not run it.
#
# Overridable via env: GH_OWNER, GHOST_REPO, REAL_REPO, SPEC, CONSULTANCY_BACKEND,
# GHOSTC_DEMO_ROOT, GHOSTC_METRICS_FILE, GHOSTC_PRIVATE_DIR.
set -euo pipefail

CI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$CI_DIR/../.." && pwd)"

GH_OWNER="${GH_OWNER:-mastrobardo}"
GHOST_REPO="${GHOST_REPO:-ghostc-demo-ghost}"
REAL_REPO="${REAL_REPO:-ghostc-demo-real}"
GHOST_SLUG="$GH_OWNER/$GHOST_REPO"
REAL_SLUG="$GH_OWNER/$REAL_REPO"
# push URLs — overridable so a self-hosted forge or a local dry-run can slot in
GHOST_REMOTE="${GHOST_REMOTE:-https://github.com/$GHOST_SLUG.git}"
REAL_REMOTE="${REAL_REMOTE:-https://github.com/$REAL_SLUG.git}"

SPEC="${SPEC:-001-add-companyx-integration}"
CONSULTANCY_BACKEND="${CONSULTANCY_BACKEND:-stub}"
CONFIG="fixtures/webapp/privacy.webapp.yaml"

DEMO_ROOT="${GHOSTC_DEMO_ROOT:-$(cd "$ROOT/.." && pwd)/ghostc-demo}"
REAL_TREE="$DEMO_ROOT/real"
GHOST_TREE="$DEMO_ROOT/ghost"
# boundary-internal artifacts (mapping = real values) stay in-repo, matching the
# `client-agent start` defaults — NOT under $DEMO_ROOT next to the ghost tree.
PRIV="${GHOSTC_PRIVATE_DIR:-$ROOT/.ghostc/webapp-private}"
METRICS="${GHOSTC_METRICS_FILE:-$ROOT/metrics/agent-runs.jsonl}"

if command -v ghostc >/dev/null 2>&1; then GHOSTC=(ghostc)
else GHOSTC=(python -m ghostc); fi

cd "$ROOT"

say() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }

# Stage the runnable webapp fixture outside the repo and compile it to a ghost tree.
ci_stage_and_compile() {
  say "stage real + compile ghost  ($DEMO_ROOT)"
  GHOSTC_DEMO_ROOT="$DEMO_ROOT" "$ROOT/fixtures/webapp/apply.sh"
  mkdir -p "$PRIV"
  "${GHOSTC[@]}" compile \
    --repo "$REAL_TREE" --config "$CONFIG" \
    --out "$GHOST_TREE" --spec "$DEMO_ROOT/ghost-spec.md" \
    --mapping "$PRIV/mapping.json" --audit "$PRIV/audit.jsonl" \
    --candidates "$PRIV/candidates.jsonl"
}

# The verified reduced flow: sanitized TASK.md -> ghost branch -> post-receive hook
# -> consultancy develops -> reverse-compile the impl onto a real-repo branch.
ci_run_flow() {
  say "client-agent start  (consultancy backend: $CONSULTANCY_BACKEND)"
  client-agent start "$SPEC" --consultancy-backend "$CONSULTANCY_BACKEND" \
    --config "$CONFIG" --ghost-tree "$GHOST_TREE" --real-repo "$REAL_TREE" \
    --mapping "$PRIV/mapping.json" --audit "$PRIV/audit.jsonl" --metrics-file "$METRICS"
  say "client-agent open-real-pr  (the 'webhook' — reverse compile)"
  client-agent open-real-pr "$SPEC" \
    --config "$CONFIG" --ghost-tree "$GHOST_TREE" --real-repo "$REAL_TREE" \
    --mapping "$PRIV/mapping.json" --audit "$PRIV/audit.jsonl" --metrics-file "$METRICS"
}

pub() { python -m client_agent.publish "$@" --metrics-file "$METRICS"; }
