"""LangGraph channel schema for the client workflow.

Kept free of any ``langgraph`` import so the contract is testable without the
``[agents]`` extra installed.

Boundary note: ``real_task`` and ``real_diff`` are boundary-internal. Only
``ghost_task`` / ``ghost_branch`` / the ghost PR ever cross to the consultancy
side; the sanitized ``TASK.md`` (rendered by :func:`ghostc.spec.render_task_md`)
is what gets committed onto the ghost branch.
"""
from __future__ import annotations

from typing import Any, TypedDict


class TaskState(TypedDict, total=False):
    task_id: str
    operation_id: str

    real_task: str                 # boundary-internal
    ghost_task: str                # crosses
    substitutions: list[dict]      # [{entity_id, ghost, kind, level, count}] — no real values

    ghost_branch: str
    ghost_pr: dict[str, Any] | None
    real_diff: str                 # boundary-internal
    real_pr: dict[str, Any] | None

    approvals: list[dict[str, Any]]
    metrics: dict[str, Any]
    rejected: str | None           # set (with a reason) when a fail-closed gate tripped


def new_state(task_id: str, real_task: str) -> TaskState:
    return TaskState(
        task_id=task_id, real_task=real_task, approvals=[], metrics={},
        ghost_pr=None, real_pr=None, rejected=None,
    )
