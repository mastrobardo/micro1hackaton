#!/usr/bin/env bash
# Push the reduced-flow branches to the throwaway GitHub repos and open (or update)
# the two PRs a judge inspects:
#
#   ghostc-demo-ghost :  ghostc/task/<id>            the sanitized task branch
#   ghostc-demo-real  :  ghostc/real/<decoded-id>    the reverse-compiled real PR
#
# Run AFTER the flow (`ci_run_flow`, i.e. `client-agent start` + `open-real-pr`);
# `scripts/ci/run-local.sh` and the CI workflow do that first. Idempotent.
#
# `ghostc compile` mints a fresh root commit each run, so `main` on each throwaway
# repo is force-pushed to track the current compile — the PR diff is then just the
# task's change. These are disposable demo repos; that is fine.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

gh auth setup-git
[ -f "$METRICS" ] || { echo "no metrics at $METRICS — run the flow first" >&2; exit 2; }

TASK_ID="$(pub resolve --field task_id)"
GHOST_BRANCH="$(pub resolve --field ghost_branch)"
REAL_BRANCH="$(pub resolve --field real_branch)"
BASE="$(pub resolve --field base)"
[ -n "$REAL_BRANCH" ] || { echo "no real branch in metrics — did open-real-pr succeed?" >&2; exit 2; }

say "publish  task=$TASK_ID  base=$BASE"
echo "  ghost: $GHOST_BRANCH -> $GHOST_SLUG"
echo "  real : $REAL_BRANCH -> $REAL_SLUG"

git -C "$GHOST_TREE" push -f "$GHOST_REMOTE" \
  "HEAD:refs/heads/$BASE" "refs/heads/$GHOST_BRANCH:refs/heads/$GHOST_BRANCH"
git -C "$REAL_TREE" push -f "$REAL_REMOTE" \
  "HEAD:refs/heads/$BASE" "refs/heads/$REAL_BRANCH:refs/heads/$REAL_BRANCH"

open_or_update() {  # <slug> <head-branch> <side>
  local slug="$1" head="$2" side="$3"
  local body; body="$(pub body --side "$side")"
  if gh pr view "$head" --repo "$slug" >/dev/null 2>&1; then
    gh pr edit "$head" --repo "$slug" --title "$(pub title --side "$side")" --body "$body"
  else
    gh pr create --repo "$slug" --base "$BASE" --head "$head" \
      --title "$(pub title --side "$side")" --body "$body"
  fi
  gh pr view "$head" --repo "$slug" --json url --jq '"  -> " + .url'
}

say "open / update PRs"
open_or_update "$GHOST_SLUG" "$GHOST_BRANCH" ghost
open_or_update "$REAL_SLUG"  "$REAL_BRANCH"  real
