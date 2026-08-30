"""Regenerate tests/expected/groundtruth.json from the built fixture.

Run after fixtures/apply.sh when the injected layer legitimately changes:
    python -m tests.gen_groundtruth
"""
from __future__ import annotations

import json
from pathlib import Path

from ghostc.config import load_config
from tests.conftest import read_tree, scan_entity_hits

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "expected" / "groundtruth.json"


def main() -> None:
    cfg = load_config(ROOT / "privacy.yaml")
    seeds = [e for e in cfg["entities"] if e.get("source", "seed") == "seed"]
    corpus = "\n".join(read_tree(ROOT / "workspace" / "real",
                                 skip_dirs=(".git", "node_modules")).values())
    hits = scan_entity_hits(corpus, seeds)
    absent = sorted(e["id"] for e in seeds if e["id"] not in hits)
    doc = {
        "_comment": "Leak-metric baseline. Regenerate with `python -m tests.gen_groundtruth`.",
        "absent_by_design": absent,
        "occurrences": dict(sorted(hits.items())),
    }
    OUT.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(hits)} entities, absent_by_design={absent}")


if __name__ == "__main__":
    main()
