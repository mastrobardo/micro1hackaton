"""Deterministic stand-in for the consultancy coding agent (Phase C replaces this).

The real Phase C agent is a Claude tool-loop that checks out the ghost task branch,
implements ``TASK.md``, commits, and opens a ghost PR — with a boundary guard that
refuses to run if the mapping store or the real repo is reachable. Until then this
simulator does the mechanical part (branch off the task branch, make a small
deterministic edit derived from the ghost task, open a PR) so the client graph has
a real ghost PR to reverse-compile.

It only ever emits **ghost aliases that already exist in the mapping** — so the
reverse patch compiler's fail-closed checks pass — and never touches real state.
"""
from __future__ import annotations

from bridge.forge import Forge
from bridge.trace import traceable


@traceable(run_type="chain", name="consultancy:sim")
def run_consultancy(forge: Forge, repo: str, *, task_branch: str, impl_branch: str,
                    task_id: str, ghost_task: str, substitutions: list[dict],
                    title: str | None = None) -> str:
    """Branch off *task_branch*, implement (stub), open a ghost PR. Returns the PR id."""
    lines = [f"# Implementation notes — {task_id}", "", "## Touched aliases", ""]
    if substitutions:
        lines += [f"- `{s['ghost'] or '<removed>'}` ({s['kind']}, {s['level']})"
                  for s in substitutions]
    else:
        lines.append("- (none — task referenced no ghost entity)")
    lines.append("")

    forge.create_branch(repo, impl_branch, base=task_branch)
    forge.commit_file(repo, impl_branch, f"docs/ghost-tasks/{task_id}.md",
                      "\n".join(lines), f"implement: {task_id}")
    forge.push(repo, impl_branch)
    pr = forge.open_pr(repo, branch=impl_branch, base=task_branch,
                       title=title or f"[ghost] {task_id}",
                       body="Implemented from the sanitized TASK.md. (simulated agent)")
    return pr.id
