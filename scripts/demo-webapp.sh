#!/usr/bin/env bash
# Runnable end-to-end demo: real repo -> ghost repo, both served side by side.
#
#   ./scripts/demo-webapp.sh            # build, compile, serve real :3000 + ghost :3001
#   REAL_PORT=4000 GHOST_PORT=4001 ./scripts/demo-webapp.sh
#   DEMO_NO_SERVE=1 ./scripts/demo-webapp.sh   # build + compile + health diff, no servers
#
# real  -> $GHOSTC_DEMO_ROOT/real   (default ../ghostc-demo/real, a sibling of this repo)
# ghost -> $GHOSTC_DEMO_ROOT/ghost
# boundary-internal artifacts stay in-repo under workspace/webapp-private/.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DEMO_ROOT="${GHOSTC_DEMO_ROOT:-$(cd "$ROOT/.." && pwd)/ghostc-demo}"
REAL="$DEMO_ROOT/real"
GHOST="$DEMO_ROOT/ghost"
REAL_PORT="${REAL_PORT:-3000}"
GHOST_PORT="${GHOST_PORT:-3001}"

if command -v ghostc >/dev/null 2>&1; then G=(ghostc)
elif python -c "import ghostc" >/dev/null 2>&1; then G=(python -m ghostc)
else echo 'run: pip install -e ".[dev]"  (venv active)' >&2; exit 2; fi

say() { printf '\n\e[1m== %s ==\e[0m\n' "$*"; }

say "1. stage the real repo (outside this tool repo)"
GHOSTC_DEMO_ROOT="$DEMO_ROOT" ./fixtures/webapp/apply.sh

say "2. compile real -> privacy-safe ghost"
"${G[@]}" compile \
  --repo "$REAL" \
  --config fixtures/webapp/privacy.webapp.yaml \
  --out "$GHOST" \
  --spec "$DEMO_ROOT/ghost-spec.md" \
  --mapping   workspace/webapp-private/mapping.json \
  --audit     workspace/webapp-private/audit.jsonl \
  --candidates workspace/webapp-private/candidates.jsonl

say "3. verify the ghost is leak-free"
"${G[@]}" verify --ghost "$GHOST" --mapping workspace/webapp-private/mapping.json

say "4. tests — both trees"
( cd "$REAL"  && node --test ) >/tmp/ghostc-demo-real-test.log  2>&1 && echo "  real  : npm test OK  ($(grep -c '^ok ' /tmp/ghostc-demo-real-test.log) tests)"
( cd "$GHOST" && node --test ) >/tmp/ghostc-demo-ghost-test.log 2>&1 && echo "  ghost : npm test OK  ($(grep -c '^ok ' /tmp/ghostc-demo-ghost-test.log) tests)"

if [ "${DEMO_NO_SERVE:-0}" = 1 ]; then
  say "done (DEMO_NO_SERVE=1) — start manually:"
  echo "  ( cd \"$REAL\"  && PORT=$REAL_PORT  npm start )"
  echo "  ( cd \"$GHOST\" && PORT=$GHOST_PORT npm start )"
  exit 0
fi

say "5. serve both"
PORT=$REAL_PORT  node "$REAL/src/server.js"  & REAL_PID=$!
PORT=$GHOST_PORT node "$GHOST/src/server.js" & GHOST_PID=$!
trap 'kill $REAL_PID $GHOST_PID 2>/dev/null || true' EXIT INT TERM

# wait for both to answer
for url in "http://localhost:$REAL_PORT/api/health" "http://localhost:$GHOST_PORT/api/health"; do
  for _ in $(seq 1 40); do curl -sf "$url" >/dev/null 2>&1 && break; sleep 0.1; done
done

say "6. same endpoint, two trust levels"
printf '\n  \e[1mREAL   http://localhost:%s\e[0m\n' "$REAL_PORT"
curl -s "http://localhost:$REAL_PORT/api/health"  | sed 's/^/    /'
printf '\n  \e[1mGHOST  http://localhost:%s\e[0m\n' "$GHOST_PORT"
curl -s "http://localhost:$GHOST_PORT/api/health" | sed 's/^/    /'

cat <<EOF

  Open both in a browser:
    real  -> http://localhost:$REAL_PORT
    ghost -> http://localhost:$GHOST_PORT

  ghost repo  : $GHOST
  ghost spec  : $DEMO_ROOT/ghost-spec.md
  mapping     : workspace/webapp-private/mapping.json   (never leaves this repo)

  Ctrl-C to stop both servers.
EOF
wait
