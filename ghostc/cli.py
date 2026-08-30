"""ghostc command-line interface.

Implemented today:  validate-config, compile
Stubs (see PROGRESS.md):  discover, verify, apply-patch, eval
"""
from __future__ import annotations

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
@click.option("--config", "config_path", default="privacy.yaml", show_default=True,
              type=click.Path())
@click.option("--out", default="workspace/ghost", show_default=True, type=click.Path(),
              help="Ghost repo — the only output that crosses the privacy boundary.")
@click.option("--spec", "spec_path", default="workspace/ghost-spec.md",
              show_default=True, type=click.Path(),
              help="Ghost spec — crosses alongside the ghost; kept a sibling, never inside it.")
@click.option("--mapping", "mapping_path", default="workspace/private/mapping.json",
              show_default=True, type=click.Path(),
              help="Mapping store — boundary-internal, holds real values. Never crosses.")
@click.option("--audit", "audit_path", default="workspace/private/audit.jsonl",
              show_default=True, type=click.Path(), help="Audit log — boundary-internal.")
@click.option("--dry-run", is_flag=True, help="Compute and report; write nothing.")
def compile(repo: str, config_path: str, out: str, spec_path: str, mapping_path: str,
            audit_path: str, dry_run: bool) -> None:
    """Compile REPO into a privacy-safe ghost repo + ghost spec."""
    from ghostc.compile import compile_repo

    try:
        cfg = load_config(config_path)
    except ConfigError as exc:
        raise SystemExit(f"INVALID CONFIG\n{exc}")

    pending = entities_needing_approval(cfg)
    if pending:
        names = ", ".join(e["id"] for e in pending)
        raise SystemExit(
            f"BLOCKED: {len(pending)} restricted entity(ies) awaiting human approval: {names}\n"
            "Add `approved_by:` in the config before compiling."
        )

    result = compile_repo(repo, config_path=config_path, out=out, spec_path=spec_path,
                          mapping_path=mapping_path, audit_path=audit_path,
                          dry_run=dry_run)
    click.echo(result.summary())


@main.command()
@click.option("--ghost", required=True, type=click.Path())
@click.option("--mapping", "mapping_path", default="workspace/private/mapping.json",
              show_default=True, type=click.Path())
@click.option("--config", "config_path", default="privacy.yaml", show_default=True,
              type=click.Path())
@click.option("--audit", "audit_path", default="workspace/private/audit.jsonl",
              show_default=True, type=click.Path())
@click.option("--operation-id", default=None, help="Correlate with a prior compile run.")
@click.option("--require-build", is_flag=True,
              help="Treat an unrunnable yarn lint as a block (fail closed on the build gate too).")
def verify(ghost: str, mapping_path: str, config_path: str, audit_path: str,
           operation_id: str | None, require_build: bool) -> None:
    """Leak scan + mapping-leak scan + build gate over the ghost repo. Fail closed."""
    from ghostc.audit import AuditLog
    from ghostc.verify import verify_ghost

    result = verify_ghost(ghost, mapping_path, config_path=config_path,
                          require_build=require_build)

    audit = AuditLog(audit_path, operation_id)
    audit.emit("verify.scan", "verifier", subject={"file": str(result.ghost)},
               details={c.name: c.status for c in result.checks})
    if result.ok:
        audit.emit("verify.pass", "verifier", subject={"file": str(result.ghost)})
    else:
        audit.emit("verify.block", "verifier", subject={"file": str(result.ghost)},
                   decision="block", details={"reasons": [c.name for c in result.checks
                                                          if c.status == "fail"]})

    click.echo(result.summary())
    if not result.ok:
        raise SystemExit(1)


@main.command("apply-patch")
@click.option("--ghost-diff", required=True, type=click.Path())
@click.option("--mapping", default="workspace/private/mapping.json", type=click.Path())
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
