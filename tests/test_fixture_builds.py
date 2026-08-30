"""The injected fixture layer is valid source in its own right.

Toolchain-gated: each check skips if its tool is missing, so a clean-env run is
still green. CI with node + terraform exercises them for real.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_injected_javascript_parses(real_repo):
    js_files = sorted((real_repo / "src" / "integrations").glob("*.js"))
    assert js_files
    for js in js_files:
        r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
        assert r.returncode == 0, f"{js.name}: {r.stderr}"


@pytest.mark.skipif(not shutil.which("terraform"), reason="terraform not installed")
def test_injected_terraform_validates(real_repo, tmp_path):
    work = tmp_path / "infra"
    shutil.copytree(real_repo / "infra", work)
    init = subprocess.run(["terraform", f"-chdir={work}", "init", "-backend=false", "-input=false"],
                          capture_output=True, text=True)
    if init.returncode != 0:
        pytest.skip(f"terraform init unavailable offline: {init.stderr.strip()[:200]}")
    r = subprocess.run(["terraform", f"-chdir={work}", "validate"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(not shutil.which("yarn"), reason="yarn not installed")
def test_lint_injected_sources_if_deps_present(real_repo):
    if not (real_repo / "node_modules").is_dir():
        pytest.skip("node_modules not installed in the fixture")
    r = subprocess.run(["yarn", "lint", "src/integrations"], cwd=real_repo,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
