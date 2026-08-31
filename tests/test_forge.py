"""LocalBareForge: branch / commit / push / PR / checkout round-trips over real git."""
from __future__ import annotations

import subprocess

from bridge.forge import LocalBareForge


def _forge(tmp_path) -> LocalBareForge:
    return LocalBareForge(tmp_path / "remotes")


def test_branch_commit_pr_roundtrip(tmp_path):
    forge = _forge(tmp_path)
    forge.ensure_repo("ghost")
    branch = "ghostc/task/add-fares"
    forge.create_branch("ghost", branch)
    forge.commit_file("ghost", branch, "TASK.md", "# Ghost task\n\nDo the thing.\n", "add task")

    pr = forge.open_pr("ghost", branch=branch, base="main", title="add fares", body="ghost task")

    assert pr.id == "1"
    assert "TASK.md" in pr.diff and "Do the thing" in pr.diff
    assert forge.pr_diff("ghost", "1") == pr.diff
    assert [p.id for p in forge.list_prs("ghost")] == ["1"]
    assert forge.get_pr("ghost", "1").branch == branch


def test_pr_ref_is_pushed_to_the_bare(tmp_path):
    forge = _forge(tmp_path)
    forge.ensure_repo("ghost")
    forge.create_branch("ghost", "b1")
    forge.commit_file("ghost", "b1", "x.txt", "hi\n", "c1")
    pr = forge.open_pr("ghost", branch="b1", base="main", title="t", body="b")

    refs = subprocess.run(["git", "for-each-ref", "--format=%(refname)"],
                          cwd=tmp_path / "remotes" / "ghost.git",
                          capture_output=True, text=True).stdout
    assert pr.ref in refs


def test_checkout_materialises_the_branch(tmp_path):
    forge = _forge(tmp_path)
    forge.ensure_repo("ghost")
    forge.create_branch("ghost", "b1")
    forge.commit_file("ghost", "b1", "TASK.md", "hello\n", "c1")
    forge.push("ghost", "b1")

    dest = forge.checkout("ghost", "b1", tmp_path / "co")
    assert (dest / "TASK.md").read_text() == "hello\n"


def test_seed_from_replaces_main_with_a_tree(tmp_path):
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    (src / "a.txt").write_text("A\n")
    (src / "sub" / "b.txt").write_text("B\n")

    forge = _forge(tmp_path)
    forge.seed_from("ghost", src, message="seed ghost")

    dest = forge.checkout("ghost", "main", tmp_path / "co")
    assert (dest / "a.txt").read_text() == "A\n"
    assert (dest / "sub" / "b.txt").read_text() == "B\n"
    assert not (dest / ".ghostkeep").exists()


def test_two_prs_get_sequential_ids(tmp_path):
    forge = _forge(tmp_path)
    forge.ensure_repo("ghost")
    for i in (1, 2):
        forge.create_branch("ghost", f"b{i}")
        forge.commit_file("ghost", f"b{i}", f"f{i}.txt", f"{i}\n", f"c{i}")
        pr = forge.open_pr("ghost", branch=f"b{i}", base="main", title=f"t{i}", body="b")
        assert pr.id == str(i)
    assert [p.id for p in forge.list_prs("ghost")] == ["1", "2"]
