#!/usr/bin/env python3
"""Fail the CI job on a leak-count regression.

Reads ``ghostc eval``'s CSV (``metric,baseline,compile,improvement``) and asserts
the primary row — casing-aware residual real-entity occurrences — is **0** for
``compile`` and strictly better than the keyword baseline.

    python scripts/ci/check_leak_gate.py workspace/eval-report.csv [max_compile_residual]

``max_compile_residual`` defaults to 0 (also read from $GHOSTC_LEAK_MAX).
"""
from __future__ import annotations

import csv
import os
import sys

_PRIMARY = "Residual entity occurrences (casing-aware)"


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: check_leak_gate.py <eval-report.csv> [max_compile_residual]",
              file=sys.stderr)
        return 2
    path = argv[0]
    cap = int(argv[1] if len(argv) > 1 else os.environ.get("GHOSTC_LEAK_MAX", "0"))

    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    row = next((r for r in rows if r["metric"].startswith(_PRIMARY)), None)
    if row is None:
        print(f"leak gate: primary metric row not found in {path}", file=sys.stderr)
        return 2

    baseline, compile_ = int(row["baseline"]), int(row["compile"])
    print(f"leak gate: baseline={baseline}  compile={compile_}  cap={cap}")
    if compile_ > cap:
        print(f"::error::leak-count regression — compile residual {compile_} > {cap}")
        return 1
    if baseline <= compile_:
        print(f"::error::baseline ({baseline}) no longer worse than compile "
              f"({compile_}) — the eval no longer demonstrates the win")
        return 1
    print("leak gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
