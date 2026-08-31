"""The runnable webapp fixture: real builds + tests, and its compiled ghost
builds + tests + is leak-free.

This is the "it actually runs" proof the leak count alone can't give. node-gated:
skips cleanly when `node` is absent, so a clean-env `pytest` stays green.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from ghostc.config import load_config
from ghostc.scanning import anchored_scan

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_SRC = REPO_ROOT / "fixtures" / "webapp" / "app"
WEBAPP_CONFIG = REPO_ROOT / "fixtures" / "webapp" / "privacy.webapp.yaml"

# raw spellings that must never survive into the ghost webapp
WEBAPP_SEED_LITERALS = [
    "Northwind", "SkyRoute", "skyroute", "skyRoute", "booking-core",
    "northwind-internal", "api.northwind-internal.net", "Priya", "priya.nair",
    "sk_live_northwind_9f3ab7c21e5d4088",
]

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node not installed")


def _node_test(cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["node", "--test"], cwd=cwd, capture_output=True, text=True)


@pytest.fixture(scope="module")
def real_app(tmp_path_factory) -> Path:
    """A clean checkout of the template app (what fixtures/webapp/apply.sh stages)."""
    dest = tmp_path_factory.mktemp("webapp-real")
    shutil.copytree(APP_SRC, dest, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("node_modules", "dist", ".git", ".env"))
    return dest


@pytest.fixture(scope="module")
def ghost_app(tmp_path_factory, real_app) -> Path:
    from ghostc.compile import compile_repo

    out = tmp_path_factory.mktemp("webapp-ghost-out")
    ghost = out / "ghost"
    private = out / "private"
    compile_repo(
        str(real_app),
        config_path=str(WEBAPP_CONFIG),
        out=str(ghost),
        spec_path=str(out / "ghost-spec.md"),
        mapping_path=str(private / "mapping.json"),
        audit_path=str(private / "audit.jsonl"),
        candidates_path=str(private / "candidates.jsonl"),
    )
    return ghost


def test_real_app_tests_pass(real_app):
    r = _node_test(real_app)
    assert r.returncode == 0, r.stdout + r.stderr


def test_real_app_builds(real_app):
    r = subprocess.run(["node", "scripts/build.js"], cwd=real_app, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_ghost_app_tests_pass(ghost_app):
    r = _node_test(ghost_app)
    assert r.returncode == 0, r.stdout + r.stderr


def test_ghost_app_builds(ghost_app):
    r = subprocess.run(["node", "scripts/build.js"], cwd=ghost_app, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_ghost_app_is_leak_free(ghost_app):
    owner = {s: "seed" for s in WEBAPP_SEED_LITERALS}
    hits: list[str] = []
    for p in sorted(ghost_app.rglob("*")):
        if not p.is_file() or ".git" in p.parts:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for hit in anchored_scan(text, owner):
            hits.append(f"{p.relative_to(ghost_app).as_posix()}: {hit.text}")
    assert not hits, "real values leaked into the ghost webapp:\n" + "\n".join(hits)


def test_webapp_config_covers_the_apps_entities(real_app):
    """Every spelling the config declares actually appears in the template — except
    entities a not-yet-implemented ticket introduces (note marked ``[ticket:...]``)."""
    cfg = load_config(WEBAPP_CONFIG)
    corpus = "\n".join(
        p.read_text(encoding="utf-8")
        for p in APP_SRC.rglob("*")
        if p.is_file() and p.suffix in {".js", ".html", ".css", ".example", ".json"}
    )
    for e in cfg["entities"]:
        if "[ticket:" in e.get("note", ""):
            continue  # e.g. vendor_companyx — added by specs/001, not in the app yet
        assert e["real"] in corpus or any(
            m["value"] in corpus for m in e.get("match", [])
        ), f"{e['id']} ({e['real']}) not present in the template app"
