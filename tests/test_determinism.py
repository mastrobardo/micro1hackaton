"""fixtures/apply.sh is idempotent: two consecutive runs produce an identical tree.

Rebuilds workspace/real/ (from ../node-express-boilerplate) twice — the content is
deterministic by design, so the working tree is left exactly as it was.
"""
from __future__ import annotations

import hashlib
import subprocess

import pytest


def _manifest(root) -> dict[str, str]:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and ".git" not in p.relative_to(root).parts:
            out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@pytest.fixture(scope="module")
def base_repo(repo_root):
    base = repo_root.parent / "node-express-boilerplate"
    if not base.is_dir():
        pytest.skip("base repo ../node-express-boilerplate not cloned")
    return base


def test_apply_sh_is_idempotent(repo_root, base_repo):
    apply = repo_root / "fixtures" / "apply.sh"
    dest = repo_root / "workspace" / "real"

    subprocess.run(["bash", str(apply)], cwd=repo_root, check=True, capture_output=True)
    first = _manifest(dest)
    subprocess.run(["bash", str(apply)], cwd=repo_root, check=True, capture_output=True)
    second = _manifest(dest)

    assert first == second
    assert any(f.startswith("src/integrations/") for f in first)
    assert "infra/main.tf" in first
