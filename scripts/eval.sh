#!/usr/bin/env bash
# `ghostc eval` is implemented — this wrapper just runs it on the built fixture.
# Full walkthrough: scripts/e2e.sh · manual steps + expected output: cli.md §7.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

[ -d workspace/real ] || ./fixtures/apply.sh
exec python -m ghostc eval --real workspace/real --config privacy.yaml "$@"
