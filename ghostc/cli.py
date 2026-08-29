"""ghostc command-line interface.

Implemented today:  validate-config
Stubs (see PROGRESS.md):  discover, compile, verify, apply-patch, eval
"""
from __future__ import annotations

import sys

import click

from ghostc import __version__
from ghostc.config import ConfigError, entities_needing_approval, load_config

_STUB = (
    "not yet implemented — this is the scaffold. "
    "See PROGRESS.md for the build order and SESSION_TODO.md for what's next."
)


@click.group()
@click.version_option(__version__, prog_name="ghostc")
def main() -> None:
    """Privacy compiler + agent workflow: real repo <-> privacy-safe ghost repo."""


@main.command("validate-config")
@click.option("--config", "config_path", default="privacy.yaml", show_default=True,
              type=click.Path())
def validate_config(config_path: str) -> None:
    """Validate privacy.yaml against the schema and summarise it."""
    try:
        cfg = load_config(config_path)
    except ConfigError as exc:
        raise SystemExit(f"INVALID\n{exc}")

    ents = cfg.get("entities", [])
    by_level: dict[str, int] = {}
    for e in ents:
        by_level[e["level"]] = by_level.get(e["level"], 0) + 1

    click.echo(f"OK  {config_path}")
    click.echo(f"  mapping_version: {cfg['mapping_version']}")
    click.echo(f"  entities: {len(ents)}  " +
               "  ".join(f"{k}={v}" for k, v in sorted(by_level.items())))

    pending = entities_needing_approval(cfg)
    if pending:
        click.echo(f"  AWAITING HUMAN APPROVAL: {len(pending)} restricted entity(ies)")
        for e in pending:
            click.echo(f"    - {e['id']} ({e['kind']})")


@main.command()
@click.option("--repo", required=True, type=click.Path())
@click.option("--config", "config_path", default="privacy.yaml", type=click.Path())
def discover(repo: str, config_path: str) -> None:
    """Scan REPO, propose sensitive entities, reuse existing mapping identities."""
    raise SystemExit(f"ghostc discover: {_STUB}")


@main.command()
@click.option("--repo", required=True, type=click.Path())
@click.option("--config", "config_path", default="privacy.yaml", type=click.Path())
@click.option("--out", default="workspace/ghost", type=click.Path())
@click.option("--dry-run", is_flag=True)
def compile(repo: str, config_path: str, out: str, dry_run: bool) -> None:
    """Compile REPO into a privacy-safe ghost repo + ghost spec."""
    raise SystemExit(f"ghostc compile: {_STUB}")


@main.command()
@click.option("--ghost", required=True, type=click.Path())
@click.option("--mapping", default="workspace/mapping.json", type=click.Path())
def verify(ghost: str, mapping: str) -> None:
    """Leak scan + build gate over the ghost repo. Fail closed."""
    raise SystemExit(f"ghostc verify: {_STUB}")


@main.command("apply-patch")
@click.option("--ghost-diff", required=True, type=click.Path())
@click.option("--mapping", default="workspace/mapping.json", type=click.Path())
@click.option("--real", required=True, type=click.Path())
def apply_patch(ghost_diff: str, mapping: str, real: str) -> None:
    """Translate a ghost PR diff into a real PR diff. Reject ambiguous mappings."""
    raise SystemExit(f"ghostc apply-patch: {_STUB}")


@main.command("eval")
@click.option("--cases", default="eval/cases", type=click.Path())
@click.option("--config", "config_path", default="privacy.yaml", type=click.Path())
def eval_(cases: str, config_path: str) -> None:
    """Run baseline vs solution over the eval cases; emit the metric table."""
    raise SystemExit(f"ghostc eval: {_STUB}")


if __name__ == "__main__":
    main()
