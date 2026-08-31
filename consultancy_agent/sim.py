"""Deterministic stand-in for the consultancy coding agent (used by the graph).

The real agent (:mod:`consultancy_agent.agent`) is a Claude tool-loop, started by
the ghost bare repo's ``post-receive`` hook. This simulator does the mechanical
part in-process so the client graph has something to observe without spawning a
subprocess or an LLM:

* ``open_pr=True`` (the full ``run-task`` pipeline): branch ``ghostc/impl/<id>``
  off the task branch, one deterministic edit, open a **ghost PR** whose diff the
  client reverse-compiles.
* ``open_pr=False`` (the reduced, hook-style flow): commit the edit **on the same
  feature branch**, push, return the branch name. No impl branch, no PR.

It only ever emits **ghost aliases that already exist in the mapping** — so the
reverse patch compiler's fail-closed checks pass — and never touches real state.
"""
from __future__ import annotations

from bridge.forge import Forge
from bridge.trace import traceable


def _notes(task_id: str, substitutions: list[dict]) -> str:
    lines = [f"# Implementation notes — {task_id}", "", "## Touched aliases", ""]
    if substitutions:
        lines += [f"- `{s['ghost'] or '<removed>'}` ({s['kind']}, {s['level']})"
                  for s in substitutions]
    else:
        lines.append("- (none — task referenced no ghost entity)")
    return "\n".join(lines) + "\n"


@traceable(run_type="chain", name="consultancy:sim")
def run_consultancy(forge: Forge, repo: str, *, task_branch: str, task_id: str,
                    ghost_task: str, substitutions: list[dict],
                    impl_branch: str | None = None, title: str | None = None,
                    open_pr: bool = True) -> str:
    """Implement the (stub) work. Returns the ghost PR id, or — when *open_pr* is
    False — the feature branch name the commit was pushed to."""
    body = _notes(task_id, substitutions)

    if not open_pr:
        forge.commit_file(repo, task_branch, f"docs/ghost-tasks/{task_id}.md",
                          body, f"impl: {task_id}")
        forge.push(repo, task_branch)
        return task_branch

    impl_branch = impl_branch or f"ghostc/impl/{task_id}"
    forge.create_branch(repo, impl_branch, base=task_branch)
    forge.commit_file(repo, impl_branch, f"docs/ghost-tasks/{task_id}.md",
                      body, f"implement: {task_id}")
    forge.push(repo, impl_branch)
    pr = forge.open_pr(repo, branch=impl_branch, base=task_branch,
                       title=title or f"[ghost] {task_id}",
                       body="Implemented from the sanitized TASK.md. (simulated agent)")
    return pr.id
