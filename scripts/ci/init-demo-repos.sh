#!/usr/bin/env bash
# One-time setup for the CI demo. Creates the two PUBLIC throwaway GitHub repos the
# workflow opens PRs against and seeds `main` on each from a fresh compile.
# Idempotent — safe to re-run (re-seeds `main`).
#
#   GH_OWNER=mastrobardo scripts/ci/init-demo-repos.sh
#
# Needs `gh` authenticated as (or GH_TOKEN for) $GH_OWNER with repo-create rights.
# `gh` here may be logged into a different account — run `gh auth switch` first or
# export GH_TOKEN=<a $GH_OWNER PAT with 'repo' scope>.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

gh auth setup-git

for slug in "$GHOST_SLUG" "$REAL_SLUG"; do
  if gh repo view "$slug" >/dev/null 2>&1; then
    echo "exists : $slug"
  else
    gh repo create "$slug" --public \
      --description "ghostc demo — throwaway; the opened PRs are the deliverable" \
      --disable-wiki
    echo "created: $slug"
  fi
done

ci_stage_and_compile

say "seed main on both repos (fresh compile output)"
git -C "$REAL_TREE"  push -f "$REAL_REMOTE"  HEAD:refs/heads/main
git -C "$GHOST_TREE" push -f "$GHOST_REMOTE" HEAD:refs/heads/main

cat <<EOF

done.
  ghost : https://github.com/$GHOST_SLUG
  real  : https://github.com/$REAL_SLUG

next: add repo secrets for the workflow (Settings > Secrets and variables > Actions
on THIS repo):
  GH_PAT             a $GH_OWNER PAT with 'repo' scope — lets CI push branches +
                     open PRs on the two demo repos above
  ANTHROPIC_API_KEY  only needed to run the workflow with consultancy_backend=claude
EOF
