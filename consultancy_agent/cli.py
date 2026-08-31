"""``consultancy-agent`` — the external coding agent CLI.

    consultancy-agent start --repo <ghost-checkout> --branch ghostc/task/<id> \
                            [--backend auto|claude|stub]

Normally invoked by the ``post-receive`` hook on the ghost bare repo (see
``bridge.forge.install_consultancy_hook`` / ``consultancy_agent._hook``), but it is
a plain entrypoint you can run by hand against any ghost checkout.

Boundary: this package may import ``bridge`` only — never ``ghostc`` /
``client_agent`` (``tests/test_boundary.py``).
"""
from __future__ import annotations

import click

from bridge.env import load_env


@click.group()
def main() -> None:
    """External coding agent: implement TASK.md on the ghost feature branch, push. No PR."""
    load_env()


@main.command("start")
@click.option("--repo", required=True, type=click.Path(exists=True, file_okay=False),
              help="A checkout of the ghost feature branch (TASK.md at its root).")
@click.option("--branch", required=True, help="The feature branch to implement + push, "
              "e.g. ghostc/task/001-add-companyx-integration.")
@click.option("--backend", type=click.Choice(["auto", "claude", "stub"]),
              default="auto", show_default=True,
              help="auto: Claude if CONSULTANCY_ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY) is set.")
@click.option("--task-file", default="TASK.md", show_default=True)
def start_cmd(repo: str, branch: str, backend: str, task_file: str) -> None:
    from consultancy_agent.agent import run

    res = run(repo, branch, backend=backend, task_file=task_file)
    click.echo(f"consultancy: {res.commit[:10]} on {branch}  "
               f"({res.files_changed} files, {res.steps} steps, backend={res.backend})")
    if res.summary:
        click.echo(f"  {res.summary}")


if __name__ == "__main__":
    main()
