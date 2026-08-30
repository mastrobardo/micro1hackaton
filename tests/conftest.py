"""Shared fixtures + helpers for the ghostc test suite.

Fixture-dependent tests (`workspace/real/` must be built by `fixtures/apply.sh`,
which needs the base repo at `../node-express-boilerplate`) skip cleanly when the
fixture is absent, so `pytest -q` is green from a clean checkout.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ghostc.scanning import anchored_scan

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_LITERALS = [
    # raw spellings that must never survive into the ghost (superset of cli.md's list)
    "Northwind", "SkyRoute", "skyroute", "AeroFeed", "aerofeed", "Datadog", "datadoghq",
    "Sentry", "booking-core", "pricing-svc", "fare-cache", "northwind-internal",
    "10.20.4.7", "nwa-prod-eu-west-1", "447015923388", "sk_live", "Priya", "priya.nair",
]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def privacy_yaml() -> Path:
    return REPO_ROOT / "privacy.yaml"


@pytest.fixture(scope="session")
def config(privacy_yaml) -> dict:
    from ghostc.config import load_config

    return load_config(privacy_yaml)


@pytest.fixture(scope="session")
def seed_entities(config) -> list[dict]:
    return [e for e in config["entities"] if e.get("source", "seed") == "seed"]


@pytest.fixture(scope="session")
def real_repo() -> Path:
    """`workspace/real/` — the built fixture. Skips the test if it is not present."""
    p = REPO_ROOT / "workspace" / "real"
    if not (p / "src" / "integrations").is_dir():
        pytest.skip("fixture not built — run ./fixtures/apply.sh (needs ../node-express-boilerplate)")
    return p


@pytest.fixture(scope="session")
def compiled(tmp_path_factory, real_repo, privacy_yaml) -> SimpleNamespace:
    """Run `compile_repo` once into a throwaway dir; expose the result + artifact paths."""
    from ghostc.compile import compile_repo

    out = tmp_path_factory.mktemp("compiled")
    ghost = out / "ghost"
    spec = out / "ghost-spec.md"          # crosses alongside the ghost (sibling)
    private = out / "private"             # boundary-internal, never crosses
    res = compile_repo(
        str(real_repo),
        config_path=str(privacy_yaml),
        out=str(ghost),
        spec_path=str(spec),
        mapping_path=str(private / "mapping.json"),
        audit_path=str(private / "audit.jsonl"),
        candidates_path=str(private / "candidates.jsonl"),
    )
    return SimpleNamespace(
        result=res, root=out, ghost=ghost, spec=spec,
        mapping=private / "mapping.json",
        audit=private / "audit.jsonl",
    )


# -- helpers -----------------------------------------------------------------

def read_tree(root: Path, skip_dirs=(".git",)) -> dict[str, str]:
    """rel-path -> text for every UTF-8 file under *root* (binary files skipped)."""
    out: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file() or set(p.relative_to(root).parts) & set(skip_dirs):
            continue
        try:
            out[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            pass
    return out


def entity_spellings(entity: dict) -> list[str]:
    out = [entity["real"]]
    for m in entity.get("match", []):
        if m["kind"] in ("literal", "identifier"):
            out.append(m["value"])
    return sorted(set(out), key=len, reverse=True)


def scan_entity_hits(corpus: str, entities: list[dict]) -> dict[str, int]:
    """Per-entity count of spellings in *corpus*, via the shared `anchored_scan` primitive."""
    owner: dict[str, str] = {}
    for e in entities:
        for s in entity_spellings(e):
            owner.setdefault(s, e["id"])
    counts: dict[str, int] = {}
    for hit in anchored_scan(corpus, owner):
        eid = owner[hit.text]
        counts[eid] = counts.get(eid, 0) + 1
    return counts


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
