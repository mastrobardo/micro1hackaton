#!/usr/bin/env bash
# Short happy-path demo: fixture -> discover -> compile -> verify -> eval.
# For the full walkthrough incl. the fail-closed cases, use scripts/e2e.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if command -v ghostc >/dev/null 2>&1; then G=(ghostc)
elif python -c "import ghostc" >/dev/null 2>&1; then G=(python -m ghostc)
else echo 'run: pip install -e ".[dev]"  (venv active)' >&2; exit 2; fi

say() { printf '\n\e[1m== %s ==\e[0m\n' "$*"; }

say "1. base fixture + synthetic sensitive-entity layer"
[ -d ../node-express-boilerplate ] || \
  git clone --depth 1 https://github.com/hagopj13/node-express-boilerplate.git ../node-express-boilerplate
./fixtures/apply.sh

say "2. validate the privacy config"
"${G[@]}" validate-config --config privacy.yaml

say "3. discover — score + propose sensitive entities"
"${G[@]}" discover --repo workspace/real

say "4. compile — real repo -> privacy-safe ghost repo"
"${G[@]}" compile --repo workspace/real

say "5. verify — fail-closed leak / mapping / build gate"
"${G[@]}" verify --ghost workspace/ghost --mapping workspace/private/mapping.json

say "6. eval — the measured win (baseline vs compile)"
"${G[@]}" eval --real workspace/real

say "done"
echo "  ghost repo : workspace/ghost/            (+ workspace/ghost-spec.md)"
echo "  private    : workspace/private/{mapping.json,audit.jsonl,candidates.jsonl}"
echo "  report     : workspace/eval-report.{md,csv}"
