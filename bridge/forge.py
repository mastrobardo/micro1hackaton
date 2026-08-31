"""A minimal git "forge" the agent workflow talks to instead of GitHub.

:class:`LocalBareForge` backs the client <-> consultancy handoff with **local bare
repositories** (real git, no network): a bare repo per side under ``root``, a
working clone the forge commits through, and a "pull request" represented as a
JSON record plus a pushed ``refs/ghostc/pr/<id>`` ref. This keeps the whole loop
offline and reproducible.

The :class:`Forge` protocol is the seam: a GitHub-backed implementation (``gh``
CLI) can be dropped in later without touching the graph.
"""
from __future__ import annotations

import json
import os
import subprocess
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "ghostc", "GIT_AUTHOR_EMAIL": "ghost@local",
    "GIT_COMMITTER_NAME": "ghostc", "GIT_COMMITTER_EMAIL": "ghost@local",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
}


def _git(cwd: Path, *args: str) -> str:
    res = subprocess.run(["git", *args], cwd=cwd, env={**os.environ, **_GIT_ENV},
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}:\n{res.stderr.strip()}")
    return res.stdout


@dataclass
class PullRequest:
    id: str
    repo: str                 # forge repo name, e.g. "ghost" | "real"
    branch: str
    base: str
    title: str
    body: str
    head_sha: str
    diff: str
    ref: str                  # refs/ghostc/pr/<id>
    created: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class Forge(Protocol):
    def ensure_repo(self, name: str) -> Path: ...
    def seed_from(self, name: str, tree: Path, message: str = ...) -> str: ...
    def create_branch(self, name: str, branch: str, base: str = ...) -> None: ...
    def commit_file(self, name: str, branch: str, path: str, content: str,
                    message: str) -> str: ...
    def push(self, name: str, branch: str) -> None: ...
    def apply_diff(self, name: str, branch: str, diff: str, message: str) -> str: ...
    def checkout(self, name: str, ref: str, dest: Path) -> Path: ...
    def open_pr(self, name: str, *, branch: str, base: str, title: str,
                body: str) -> PullRequest: ...
    def get_pr(self, name: str, pr_id: str) -> PullRequest: ...
    def pr_diff(self, name: str, pr_id: str) -> str: ...
    def list_prs(self, name: str) -> list[PullRequest]: ...


class LocalBareForge:
    """File-backed forge. ``root`` holds ``<name>.git`` bares + ``work/<name>`` clones."""

    def __init__(self, root: str | Path, default_base: str = "main") -> None:
        # Absolute: git runs with cwd set to a working clone / a bare repo, so every
        # bare-repo path handed to `git` (clone source, hook targets) must not be
        # relative to the process's cwd.
        self.root = Path(root).resolve()
        self.default_base = default_base
        (self.root / "work").mkdir(parents=True, exist_ok=True)

    # -- paths --------------------------------------------------------------
    def _bare(self, name: str) -> Path:
        return self.root / f"{name}.git"

    def _work(self, name: str) -> Path:
        return self.root / "work" / name

    def _pr_dir(self, name: str) -> Path:
        d = self._bare(name) / "ghostc-prs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # -- repo lifecycle --------------------------------------------------
    def ensure_repo(self, name: str) -> Path:
        bare = self._bare(name)
        if not bare.exists():
            bare.mkdir(parents=True)
            _git(bare, "init", "--bare", "-q", "-b", self.default_base)
            _git(bare, "symbolic-ref", "HEAD", f"refs/heads/{self.default_base}")
        work = self._work(name)
        if not (work / ".git").exists():
            work.mkdir(parents=True, exist_ok=True)
            _git(work, "clone", "-q", str(bare), ".")
            if not _git(work, "branch", "--list").strip():
                (work / ".ghostkeep").write_text("", encoding="utf-8")
                _git(work, "add", "-A")
                _git(work, "commit", "-q", "-m", "init")
                _git(work, "branch", "-M", self.default_base)
                _git(work, "push", "-q", "-u", "origin", self.default_base)
        return bare

    def seed_from(self, name: str, tree: Path, message: str = "seed") -> str:
        """Replace ``main`` with the contents of *tree* (a real directory)."""
        import shutil

        self.ensure_repo(name)
        work = self._work(name)
        _git(work, "checkout", "-q", self.default_base)
        for child in work.iterdir():
            if child.name == ".git":
                continue
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        for child in Path(tree).iterdir():
            if child.name == ".git":
                continue
            dst = work / child.name
            shutil.copytree(child, dst) if child.is_dir() else shutil.copy2(child, dst)
        _git(work, "add", "-A")
        _git(work, "commit", "-q", "--allow-empty", "-m", message)
        _git(work, "push", "-q", "origin", self.default_base)
        return _git(work, "rev-parse", "HEAD").strip()

    # -- branches / commits -------------------------------------------
    def create_branch(self, name: str, branch: str, base: str | None = None) -> None:
        base = base or self.default_base
        work = self._work(name)
        _git(work, "fetch", "-q", "origin")
        _git(work, "checkout", "-q", "-B", branch, f"origin/{base}")

    def commit_file(self, name: str, branch: str, path: str, content: str,
                    message: str) -> str:
        work = self._work(name)
        _git(work, "checkout", "-q", branch)
        target = work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        _git(work, "add", "-A")
        _git(work, "commit", "-q", "-m", message)
        return _git(work, "rev-parse", "HEAD").strip()

    def push(self, name: str, branch: str) -> None:
        _git(self._work(name), "push", "-q", "origin", branch)

    def apply_diff(self, name: str, branch: str, diff: str, message: str) -> str:
        """Apply a raw unified diff onto *branch* in the working clone and commit."""
        work = self._work(name)
        _git(work, "checkout", "-q", branch)
        p = subprocess.run(["git", "apply", "--3way", "--whitespace=nowarn", "-"],
                           cwd=work, env={**os.environ, **_GIT_ENV},
                           input=diff, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"git apply failed in {work}:\n{(p.stderr or p.stdout).strip()}")
        _git(work, "add", "-A")
        _git(work, "commit", "-q", "-m", message)
        return _git(work, "rev-parse", "HEAD").strip()

    def checkout(self, name: str, ref: str, dest: Path) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        _git(dest.parent, "clone", "-q", str(self._bare(name)), dest.name)
        _git(dest, "checkout", "-q", ref)
        return dest

    # -- pull requests --------------------------------------------------
    def open_pr(self, name: str, *, branch: str, base: str | None = None,
                title: str, body: str) -> PullRequest:
        base = base or self.default_base
        work = self._work(name)
        _git(work, "checkout", "-q", branch)
        _git(work, "fetch", "-q", "origin")
        head_sha = _git(work, "rev-parse", "HEAD").strip()
        diff = _git(work, "diff", f"origin/{base}...{branch}")

        pr_id = str(len(list(self._pr_dir(name).glob("*.json"))) + 1)
        ref = f"refs/ghostc/pr/{pr_id}"
        _git(work, "push", "-q", "origin", branch)
        _git(work, "push", "-q", "origin", f"HEAD:{ref}")

        pr = PullRequest(
            id=pr_id, repo=name, branch=branch, base=base, title=title, body=body,
            head_sha=head_sha, diff=diff, ref=ref,
            created=datetime.now(timezone.utc).isoformat(),
        )
        (self._pr_dir(name) / f"{pr_id}.json").write_text(
            json.dumps(pr.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return pr

    def get_pr(self, name: str, pr_id: str) -> PullRequest:
        rec = json.loads((self._pr_dir(name) / f"{pr_id}.json").read_text(encoding="utf-8"))
        return PullRequest(**rec)

    def pr_diff(self, name: str, pr_id: str) -> str:
        return self.get_pr(name, pr_id).diff

    def list_prs(self, name: str) -> list[PullRequest]:
        out = [self.get_pr(name, p.stem) for p in sorted(self._pr_dir(name).glob("*.json"))]
        return sorted(out, key=lambda pr: int(pr.id))


def new_pr_token() -> str:
    return uuid.uuid4().hex[:8]
