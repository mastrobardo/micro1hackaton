#!/usr/bin/env bash
# Run baseline (sed redaction) vs solution over the eval cases; emit the metric table.
# [STUB] until `ghostc eval` lands — see PROGRESS.md.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "eval harness not implemented yet."
echo "planned: python -m ghostc eval --cases eval/cases --config privacy.yaml"
echo "  -> workspace/eval-report.md  (leak count, task pass rate, approvals, time, cost)"
echo "  -> derived from workspace/audit.jsonl"
