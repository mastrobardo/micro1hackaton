#!/usr/bin/env bash
# Stage the runnable "real" repo OUTSIDE this tool repo.
#
#   fixtures/webapp/app/   -- version-controlled template (source of truth)
#   $GHOSTC_DEMO_ROOT/real -- a clean checkout of it, where you run + compile it
#
# Default GHOSTC_DEMO_ROOT is a sibling of this repo (../ghostc-demo), matching how
# ../node-express-boilerplate sits beside it. Override with the env var.
# The app is self-contained (zero runtime deps). Idempotent.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
SRC="$HERE/app"
DEMO_ROOT="${GHOSTC_DEMO_ROOT:-$(cd "$ROOT/.." && pwd)/ghostc-demo}"
DEST="$DEMO_ROOT/real"

echo "template : $SRC"
echo "real     : $DEST"
mkdir -p "$DEST"
rm -rf "$DEST"
mkdir -p "$DEST"
rsync -a \
  --exclude '.git' --exclude 'node_modules' --exclude 'dist' --exclude '.env' \
  "$SRC"/ "$DEST"/

# the real (un-sanitized) ticket ships beside the code
mkdir -p "$DEST/tasks"
rsync -a "$HERE/tasks/" "$DEST/tasks"/

# fresh git baseline — compile / apply-patch want a repo with one commit
(
  cd "$DEST"
  git init -q
  git add -A
  git -c user.email=fixture@example.com -c user.name=fixture commit -q -m "webapp fixture baseline"
)

echo "done. files:"
( cd "$DEST" && find src public test tasks -type f | sed 's/^/  /' )
echo
echo "run it:   ( cd \"$DEST\" && npm ci && npm test && PORT=3000 npm start )"
echo "demo:     ./scripts/demo-webapp.sh"
 