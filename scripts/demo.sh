#!/usr/bin/env bash
# End-to-end demo. Steps marked [STUB] print what they *will* do until implemented.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== 1. base fixture =="
[ -d ../node-express-boilerplate ] || \
  git clone --depth 1 https://github.com/hagopj13/node-express-boilerplate.git ../node-express-boilerplate

echo "== 2. inject synthetic sensitive-entity layer =="
./fixtures/apply.sh

echo "== 3. validate privacy config =="
python -m ghostc validate-config --config privacy.yaml

echo "== 4. discover entities =="        # [STUB]
python -m ghostc discover --repo workspace/real --config privacy.yaml || true

echo "== 5. compile -> ghost repo =="    # [STUB]
python -m ghostc compile --repo workspace/real --config privacy.yaml --out workspace/ghost || true

echo "== 6. verify (leak scan + build gate) =="  # [STUB]
python -m ghostc verify --ghost workspace/ghost --mapping workspace/mapping.json || true

echo "== 7. (manual) run external coding agent on workspace/ghost, produce a ghost PR diff =="
echo "== 8. reverse-compile ghost diff -> real diff =="  # [STUB]
echo "== 9. eval report =="
echo "   see workspace/eval-report.md once 'ghostc eval' lands"
