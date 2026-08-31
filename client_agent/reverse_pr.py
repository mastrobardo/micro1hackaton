"""``client-agent open-real-pr`` — the reverse-compile "webhook".

Runs INSIDE the company trust boundary, **separately** from ``client-agent start``.
It simulates a forge webhook: once the consultancy has developed the ghost task
branch, this takes that branch's implementation diff, reverse-compiles it through
the mapping store (:func:`ghostc.patch.reverse_patch`), and opens a **decoded
("clear") branch on the real repo** for human review.

Only the client side can do this — reversing needs the cleartext mapping store and
``ghostc``, both of which the consultancy is walled off from
(``tests/test_boundary.py``). The consultancy's job ends at "push ghost code onto
``ghostc/task/<id>``".

    ghost repo:  ghostc/task/<id>   (handoff commit + consultancy commits)
         │  git diff <handoff>..origin/<branch>   (excl. TASK.md / IMPL_NOTES.md)
         ▼
    reverse_patch (mapping)          ── fail closed on a Rejection ──▶ no branch
         ▼
    real repo:   ghostc/real/<decoded-id>   + PR_BODY.md   (commit as ghostc-client)

Fail-closed: on a :class:`ghostc.patch.Rejection` (unmapped alias, a real value
already in the ghost diff, version mismatch) nothing is written to the real repo,
an ``agent.real_pr_blocked`` audit event + an ``outcome="rejected"`` metrics row
are recorded, and the caller gets a non-zero exit.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

from bridge.env import load_env
from bridge.llm import configure_langsmith
from bridge.metrics import record_run
from bridge.trace import traceable
from client_agent import localgit
from ghostc.audit import AuditLog, new_operation_id
from ghostc.mapping import MappingStore
from ghostc.patch import Rejection as PatchRejection
from ghostc.patch import reverse_patch

_WORKFLOW_ARTIFACTS = ("TASK.md", "IMPL_NOTES.md")


class NotReady(Exception):
    """The ghost task branch has no consultancy implementation to reverse yet."""


def _kebab(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def decode_slug(slug: str, mapping: dict) -> str:
    """Reverse-compile ghost aliases embedded in a branch/spec slug.

    ``add-partner-a-integration`` → ``add-companyx-integration`` when the mapping
    has ``partner-a`` ↔ ``CompanyX``. A slug with no alias in it is returned
    unchanged. Longest ghost alias first so ``vendor-a-b`` beats ``vendor-a``.
    """
    pairs = sorted(
        ((e["ghost"], _kebab(e["real"])) for e in mapping.get("entries", []) if e.get("ghost")),
        key=lambda p: len(p[0]), reverse=True,
    )
    out = slug
    for ghost, real in pairs:
        out = re.sub(rf"(?<![a-z0-9]){re.escape(ghost)}(?![a-z0-9])", real, out)
    return out


def _handoff_commit(ghost: Path, ref: str) -> str:
    """The commit that ADDED ``TASK.md`` on *ref* — the client's handoff commit."""
    shas = localgit.git(ghost, "log", "--format=%H", "--diff-filter=A", ref,
                        "--", "TASK.md", check=False).split()
    return shas[-1] if shas else ""


def _git_apply(real: Path, diff: str, *flags: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(
        ["git", "-C", str(real), "apply", "--whitespace=nowarn", *flags],
        input=diff, capture_output=True, text=True, env=env)


@traceable(run_type="chain", name="client.open_real_pr")
def open_real_pr(*, task_id: str, spec_slug: str, config_path: str, ghost_tree: str,
                 real_repo: str, mapping_path: str, audit_path: str,
                 ghost_branch: str | None = None, real_branch: str | None = None,
                 base: str | None = None, metrics_file: str | None = None,
                 scratch_dir: str = ".ghostc/scratch") -> dict:
    """Reverse-compile the ghost task branch's impl diff onto a fresh real-repo
    branch. Returns the metrics row. Raises ``SystemExit`` (precondition) /
    :class:`ghostc.patch.Rejection` (fail-closed) / :class:`NotReady`."""
    load_env()
    configure_langsmith(role="client")
    started = time.time()

    ghost, real = Path(ghost_tree).resolve(), Path(real_repo).resolve()
    for p, label in ((ghost / ".git", "ghost repo"), (real / ".git", "real repo")):
        if not p.is_dir():
            raise SystemExit(f"{label} is not a git repo: {p.parent}")
    if not Path(mapping_path).exists():
        raise SystemExit(f"mapping store not found: {mapping_path}")

    mapping = MappingStore(mapping_path).data
    mapping_version = mapping.get("mapping_version", 1)
    audit = AuditLog(audit_path, new_operation_id())

    ghost_branch = ghost_branch or f"ghostc/task/{task_id}"
    base = base or localgit.default_branch(real)
    real_branch = real_branch or f"ghostc/real/{decode_slug(spec_slug or task_id, mapping)}"

    def _reject_row(outcome: str, reason: str, **extra) -> dict:
        row = {"role": "client", "command": "open-real-pr", "flow": "reverse-pr",
               "task_id": task_id, "ghost_branch": ghost_branch, "real_branch": real_branch,
               "outcome": outcome, "reason": reason,
               "wall_clock_s": round(time.time() - started, 3), **extra}
        record_run(row, path=metrics_file)
        audit.emit("agent.metrics", "client_agent", details=row)
        return row

    localgit.git(ghost, "fetch", "-q", "origin")
    ref = f"origin/{ghost_branch}"
    if not localgit.git(ghost, "rev-parse", "--verify", "-q", ref, check=False):
        raise SystemExit(f"ghost branch not found on origin: {ghost_branch} "
                         "(run `client-agent start <spec>` first)")
    handoff = _handoff_commit(ghost, ref)
    if not handoff:
        raise SystemExit(f"no TASK.md handoff commit on {ghost_branch} — is this a "
                         "ghostc task branch?")

    ghost_diff = localgit.git(
        ghost, "diff", f"{handoff}..{ref}", "--", ".",
        *(f":(exclude){a}" for a in _WORKFLOW_ARTIFACTS), check=False)
    if not ghost_diff.strip():
        audit.emit("agent.real_pr_blocked", "client_agent", decision="block",
                   details={"task_id": task_id, "reason": "consultancy diff empty"})
        _reject_row("rejected", "consultancy has not developed the ghost branch yet")
        raise NotReady(f"{ghost_branch}: no consultancy changes on top of the TASK.md commit")

    scratch = Path(scratch_dir)
    scratch.mkdir(parents=True, exist_ok=True)
    diff_path = scratch / f"{task_id}.ghost-impl.diff"
    diff_path.write_text(ghost_diff + "\n", encoding="utf-8")

    try:
        res = reverse_patch(str(diff_path), mapping_path, config_path=config_path,
                            mapping_version=mapping_version, do_apply=False,
                            audit_path=audit_path)
    except PatchRejection as rej:
        audit.emit("agent.real_pr_blocked", "client_agent", decision="block",
                   details={"task_id": task_id, "reason": rej.reason, "detail": rej.detail})
        _reject_row("rejected", f"reverse-patch: {rej}")
        raise

    # --- open the decoded branch on the real repo ---------------------------
    localgit.git(real, "checkout", "-q", "-B", real_branch, base)
    chk = _git_apply(real, res.real_diff, "--check", "--3way")
    if chk.returncode != 0:
        chk = _git_apply(real, res.real_diff, "--check")
    if chk.returncode != 0:
        localgit.git(real, "checkout", "-q", base, check=False)
        localgit.git(real, "branch", "-D", real_branch, check=False)
        detail = (chk.stderr or chk.stdout).strip()[:400]
        audit.emit("agent.real_pr_blocked", "client_agent", decision="block",
                   details={"task_id": task_id, "reason": "real diff does not apply",
                            "detail": detail})
        _reject_row("rejected", "real diff does not apply cleanly to the real repo")
        raise PatchRejection("real diff does not apply", detail)

    app = _git_apply(real, res.real_diff, "--3way")
    if app.returncode != 0:
        app = _git_apply(real, res.real_diff)
    localgit.git(real, "add", "-A")
    body = _pr_body(task_id, ghost_branch, real_branch, res)
    (real / "PR_BODY.md").write_text(body, encoding="utf-8")
    localgit.git(real, "add", "PR_BODY.md")
    localgit.git(real, "commit", "-q", "-m", f"reverse-pr: {task_id}",
                 ident=localgit.CLIENT_IDENT)
    sha = localgit.git(real, "rev-parse", "HEAD")
    localgit.git(real, "checkout", "-q", base)

    audit.emit("agent.real_pr_opened", "client_agent",
               details={"task_id": task_id, "branch": real_branch, "commit": sha,
                        "base": base, "files": res.files, "hunks": res.hunks,
                        "entities_resolved": res.entities_resolved})
    audit.emit("approval.requested", "orchestrator", actor="system", decision="pending",
               details={"gate": "real_pr_review", "branch": real_branch})

    row = {"role": "client", "command": "open-real-pr", "flow": "reverse-pr",
           "task_id": task_id, "outcome": "ok", "ghost_branch": ghost_branch,
           "ghost_handoff": handoff, "real_repo": str(real), "real_branch": real_branch,
           "real_commit": sha, "base": base,
           "entities_resolved": res.entities_resolved,
           "lossy_entities": res.lossy_entities, "files": res.files, "hunks": res.hunks,
           "wall_clock_s": round(time.time() - started, 3)}
    record_run(row, path=metrics_file)
    audit.emit("agent.metrics", "client_agent", details=row)
    return row


def _pr_body(task_id: str, ghost_branch: str, real_branch: str, res) -> str:
    lossy = (f"- **Lossy (verify prose casing):** {', '.join(res.lossy_entities)}\n"
             if res.lossy_entities else "")
    return (
        f"# [real] {task_id}\n\n"
        f"Reverse-compiled from the ghost task branch `{ghost_branch}` "
        f"(consultancy implementation) → `{real_branch}`.\n\n"
        f"- **Entities resolved:** {', '.join(res.entities_resolved) or '(none)'}\n"
        f"{lossy}"
        f"- **Translated:** {res.files} file(s), {res.hunks} hunk(s)\n\n"
        "**HUMAN REVIEW REQUIRED** before merge — check the diff matches the "
        "original ticket and introduces no new real-world entity.\n"
    )
