#!/usr/bin/env bash
# Dry-run the CI "agent round-trip" job locally: stage + compile the webapp
# fixture, run the verified reduced flow, reverse-compile onto the real repo, then
# push both branches and open the two PRs.
#
#   scripts/ci/run-local.sh                       # deterministic stub consultancy
#   CONSULTANCY_BACKEND=claude scripts/ci/run-local.sh   # live Claude consultancy
#
# Needs the [agents] extra (`pip install -e ".[agents]"`) and `gh` able to push to
# the demo repos (run scripts/ci/init-demo-repos.sh once first).
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

command -v client-agent >/dev/null 2>&1 || {
  echo "client-agent not found — pip install -e \".[agents]\"" >&2; exit 2; }

mkdir -p "$(dirname "$METRICS")"

ci_stage_and_compile
ci_run_flow
"$CI_DIR/publish-prs.sh"

say "done"
echo "  metrics: $METRICS"
