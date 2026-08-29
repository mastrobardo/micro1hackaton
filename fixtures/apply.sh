#!/usr/bin/env bash
# Build workspace/real/ = base fixture repo + synthetic sensitive-entity layer.
# Idempotent. All injected content is fictional (see fixtures/README.md).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
BASE="${BASE_REPO:-$ROOT/../node-express-boilerplate}"
DEST="$ROOT/workspace/real"

if [ ! -d "$BASE" ]; then
  echo "base repo not found at $BASE" >&2
  echo "clone it first:" >&2
  echo "  git clone --depth 1 https://github.com/hagopj13/node-express-boilerplate.git \"$BASE\"" >&2
  exit 1
fi

echo "rebuilding $DEST from $BASE"
rm -rf "$DEST"
mkdir -p "$DEST"
# copy base repo without its git history
rsync -a --exclude '.git' --exclude 'node_modules' "$BASE"/ "$DEST"/

# overlay the synthetic layer
rsync -a "$HERE/inject/" "$DEST"/
mkdir -p "$DEST/infra"
rsync -a "$HERE/infra/" "$DEST/infra"/

# wire the injected env example into place (kept as .example, no real secrets committed)
cp "$HERE/inject/.env.northwind.example" "$DEST/.env.example.northwind"

echo "done. injected files:"
( cd "$DEST" && git init -q 2>/dev/null || true; \
  find src/integrations infra -type f 2>/dev/null | sed 's/^/  /' )
