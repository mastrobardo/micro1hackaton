"""``client-agent open-real-pr`` — the reverse-compile "webhook".

Builds a ghost repo whose ``ghostc/task/<id>`` branch has a client handoff commit
(``TASK.md``) plus a consultancy implementation commit, then reverse-compiles that
implementation onto a decoded branch on the real repo.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("langgraph")
pytest.importorskip("dotenv")

from client_agent.reverse_pr import NotReady, decode_slug, open_real_pr   # noqa: E402
from ghostc.mapping import MappingStore                                    # noqa: E402
from ghostc.patch import Rejection                                        # noqa: E402

CLIENT = {"GIT_AUTHOR_NAME": "ghostc-client", "GIT_AUTHOR_EMAIL": "client@ghostc.local",
          "GIT_COMMITTER_NAME": "ghostc-client", "GIT_COMMITTER_EMAIL": "client@ghostc.local"}
DEV = {"GIT_AUTHOR_NAME": "Consultancy Dev", "GIT_AUTHOR_EMAIL": "dev@consultancy.example",
       "GIT_COMMITTER_NAME": "Consultancy Dev", "GIT_COMMITTER_EMAIL": "dev@consultancy.example"}

GHOST_PROBE = (
    "// service-a health probe (added by the consultancy)\n"
    'const NAME = "service-a";\n'
    "function serviceAPing() { return NAME; }\n"
    "module.exports = { serviceAPing };\n"
)


def _git(cwd: Path, *args: str, ident: dict | None = None) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env |= (ident or CLIENT)
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True, env=env).stdout.strip()


def _rows(path: str) -> list[dict]:
    p = Path(path)
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] \
        if p.exists() else []


@pytest.fixture
def bench(tmp_path, privacy_yaml):
    demo = tmp_path / "ghostc-demo"
    ghost, real, bare = demo / "ghost", demo / "real", demo / "ghost.git"

    # --- real repo: the un-sanitized pre-image -----------------------------
    (real / "src").mkdir(parents=True)
    (real / "README.md").write_text("# booking-core service\n", encoding="utf-8")
    _git(real, "init", "-q", "-b", "main")
    _git(real, "add", "-A")
    _git(real, "commit", "-q", "-m", "real baseline")

    # --- ghost repo + bare origin ---------------------------------------
    (ghost / "src").mkdir(parents=True)
    (ghost / "README.md").write_text("# service-a\n", encoding="utf-8")
    _git(ghost, "init", "-q", "-b", "main")
    _git(ghost, "add", "-A")
    _git(ghost, "commit", "-q", "-m", "ghost baseline (ghostc compile)")
    _git(bare.parent, "init", "--bare", "-q", "-b", "main", bare.name)
    _git(ghost, "remote", "add", "origin", str(bare))
    _git(ghost, "push", "-q", "origin", "main")

    # --- ghostc/task/<id>: client handoff, then consultancy impl ---------
    branch = "ghostc/task/002-add-probe"
    _git(ghost, "checkout", "-q", "-b", branch)
    (ghost / "TASK.md").write_text("# TASK\nAdd a health probe for service-a.\n",
                                   encoding="utf-8")
    _git(ghost, "add", "TASK.md")
    _git(ghost, "commit", "-q", "-m", "task: 002-add-probe")            # ghostc-client
    _git(ghost, "push", "-q", "origin", branch)

    (ghost / "src" / "serviceAProbe.js").write_text(GHOST_PROBE, encoding="utf-8")
    _git(ghost, "add", "-A")
    _git(ghost, "commit", "-q", "-m", "impl: 002-add-probe", ident=DEV)
    _git(ghost, "push", "-q", "origin", branch)
    _git(ghost, "checkout", "-q", "main")

    private = tmp_path / "private"
    store = MappingStore(private / "mapping.json")
    store.upsert(entity_id="svc_booking_core", real="booking-core", ghost="service-a",
                 kind="internal_service", level="confidential", strategy="semantic_alias")
    store.save()

    return {
        "kw": dict(task_id="002-add-probe", spec_slug="002-add-service-a-probe",
                   config_path=str(privacy_yaml), ghost_tree=str(ghost),
                   real_repo=str(real), mapping_path=str(private / "mapping.json"),
                   audit_path=str(private / "audit.jsonl"),
                   scratch_dir=str(tmp_path / "scratch")),
        "ghost": ghost, "real": real, "branch": branch,
        "metrics": os.environ["GHOSTC_METRICS_FILE"],
    }


def test_decode_slug_reverse_compiles_aliases():
    mapping = {"entries": [{"ghost": "partner-a", "real": "CompanyX"},
                           {"ghost": "service-a", "real": "booking-core"}]}
    assert decode_slug("add-partner-a-integration", mapping) == "add-companyx-integration"
    assert decode_slug("probe-service-a", mapping) == "probe-booking-core"
    assert decode_slug("001-no-alias-here", mapping) == "001-no-alias-here"


def test_open_real_pr_lands_a_decoded_branch_on_the_real_repo(bench):
    real = bench["real"]
    row = open_real_pr(**bench["kw"])

    assert row["outcome"] == "ok"
    assert row["real_branch"] == "ghostc/real/002-add-booking-core-probe"   # decoded
    assert row["entities_resolved"] == ["svc_booking_core"]
    assert row["lossy_entities"] == []                       # booking-core is one clean token
    assert row["files"] == 1

    # a real branch on the real repo, authored by the client, worktree back on main
    _git(real, "rev-parse", "--verify", "ghostc/real/002-add-booking-core-probe")
    log = _git(real, "log", "--format=%s|%an", "ghostc/real/002-add-booking-core-probe"
               ).splitlines()
    assert log[0].split("|") == ["reverse-pr: 002-add-probe", "ghostc-client"]
    assert _git(real, "rev-parse", "--abbrev-ref", "HEAD") == "main"

    show = _git(real, "show", "ghostc/real/002-add-booking-core-probe")
    assert "booking-core" in show and "service-a" not in show      # reversed
    assert "serviceA" not in show and "bookingCore" in show        # identifier reversed too
    files = _git(real, "show", "--name-only", "--format=",
                 "ghostc/real/002-add-booking-core-probe")
    # reverse_patch renames sensitive path components too (service-a -> booking-core)
    assert "src/bookingCoreProbe.js" in files and "PR_BODY.md" in files
    assert "TASK.md" not in files                                 # workflow artifact excluded

    body = _git(real, "show", "ghostc/real/002-add-booking-core-probe:PR_BODY.md")
    assert "HUMAN REVIEW REQUIRED" in body and "002-add-probe" in body

    # metrics + audit
    rows = [r for r in _rows(bench["metrics"]) if r["command"] == "open-real-pr"]
    assert rows and rows[-1]["outcome"] == "ok" and rows[-1]["role"] == "client"
    ev = [json.loads(l)["event"] for l in
          Path(bench["kw"]["audit_path"]).read_text(encoding="utf-8").splitlines() if l.strip()]
    assert "agent.real_pr_opened" in ev and "approval.requested" in ev


def test_not_ready_when_the_consultancy_has_not_developed_the_branch(bench):
    # roll the task branch back to just the handoff commit (parent of the impl commit)
    ghost, branch = bench["ghost"], bench["branch"]
    handoff = _git(ghost, "rev-parse", f"origin/{branch}~1")
    _git(ghost, "push", "-q", "-f", "origin", f"{handoff}:refs/heads/{branch}")

    with pytest.raises(NotReady):
        open_real_pr(**bench["kw"])
    assert not (bench["real"] / ".git" / "refs" / "heads" / "ghostc").exists()
    rows = [r for r in _rows(bench["metrics"]) if r["command"] == "open-real-pr"]
    assert rows and rows[-1]["outcome"] == "rejected"


def test_fail_closed_when_a_real_value_is_present_in_the_ghost_diff(bench):
    ghost, branch = bench["ghost"], bench["branch"]
    _git(ghost, "checkout", "-q", branch)
    # a real value leaks into the ghost side — reverse_patch must refuse
    (ghost / "src" / "leak.js").write_text('const x = "booking-core";\n', encoding="utf-8")
    _git(ghost, "add", "-A")
    _git(ghost, "commit", "-q", "-m", "oops", ident=DEV)
    _git(ghost, "push", "-q", "origin", branch)
    _git(ghost, "checkout", "-q", "main")

    with pytest.raises(Rejection):
        open_real_pr(**bench["kw"])
    # nothing written to the real repo
    assert "ghostc/real" not in _git(bench["real"], "branch", "--list", "ghostc/real/*")
    rows = [r for r in _rows(bench["metrics"]) if r["command"] == "open-real-pr"]
    assert rows and rows[-1]["outcome"] == "rejected"
    assert "reverse-patch" in rows[-1]["reason"]
