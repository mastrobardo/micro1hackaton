"""The consultancy side must not be able to import the privileged side."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = ("ghostc", "client_agent")


def _py_files(pkg: str) -> list[Path]:
    return sorted((ROOT / pkg).rglob("*.py"))


@pytest.mark.parametrize("path", _py_files("consultancy_agent"),
                         ids=lambda p: p.name)
def test_no_forbidden_import_statement(path: Path):
    src = path.read_text(encoding="utf-8")
    for name in FORBIDDEN:
        assert f"import {name}" not in src and f"from {name}" not in src, \
            f"{path.relative_to(ROOT)} imports {name} — boundary violation"


@pytest.mark.parametrize("mod", ["consultancy_agent.sim", "consultancy_agent.agent",
                                 "consultancy_agent.cli", "consultancy_agent._hook"])
def test_importing_consultancy_does_not_pull_the_privileged_side(mod: str):
    code = (f"import {mod}, sys; "
            "bad=[m for m in sys.modules if m=='ghostc' or m.startswith('ghostc.') "
            "or m=='client_agent' or m.startswith('client_agent.')]; "
            "print(bad); sys.exit(1 if bad else 0)")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 0, f"{mod} pulled in {r.stdout.strip()}"
