"""ghostc command-line interface.

Implemented:  validate-config, discover, compile, compile-spec, verify, baseline,
              apply-patch, eval   (the LangGraph agent workflow is `ghostc-agent`)
"""
from __future__ import annotations

from pathlib import Path

import click

from ghostc import __version__
from ghostc.config import ConfigError, entities_needing_approval, load_config


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
@click.option("--config", "config_path", default="privacy.yaml", show_default=True,
              type=click.Path())
@click.option("--out", "out_path", default="workspace/private/candidates.jsonl",
              show_default=True, type=click.Path(),
              help="Ranked candidates, one JSON object per line. Boundary-internal.")
@click.option("--audit", "audit_path", default="workspace/private/audit.jsonl",
              show_default=True, type=click.Path())
@click.option("--threshold", type=float, default=None,
              help="Override detection.review_threshold for this run.")
@click.option("--decisions", "decisions_path", default=None, type=click.Path(),
              help="Human review log (decisions.jsonl): annotate each proposal with "
                   "the reviewer's call + show scorer-vs-human agreement.")
@click.option("--json", "as_json", is_flag=True, help="Emit the candidate list as JSON.")
def discover(repo: str, config_path: str, out_path: str, audit_path: str,
             threshold: float | None, decisions_path: str | None, as_json: bool) -> None:
    """Scan REPO, score sensitive-entity candidates, propose the unconfigured ones."""
    from ghostc.discover import discover_repo

    try:
        load_config(config_path)
    except ConfigError as exc:
        raise SystemExit(f"INVALID CONFIG\n{exc}")

    result = discover_repo(repo, config_path=config_path, out=out_path,
                           audit_path=audit_path, threshold=threshold,
                           decisions_path=decisions_path)
    if as_json:
        import json

        click.echo(json.dumps([c.to_dict() for c in result.scan.candidates], indent=2))
    else:
        click.echo(result.summary())


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
@click.option("--candidates", "candidates_path",
              default="workspace/private/candidates.jsonl", show_default=True,
              type=click.Path(),
              help="Detection candidates + review queue — boundary-internal.")
@click.option("--decisions", "decisions_path", default=None, type=click.Path(),
              help="Human review log (ghostc-review -> decisions.jsonl): clears "
                   "approved `restricted` entities + compiles accepted proposals. "
                   "Omit for today's behaviour.")
@click.option("--no-detect", is_flag=True,
              help="Skip the candidate-scoring pass (matchers only, no review queue).")
@click.option("--dry-run", is_flag=True, help="Compute and report; write nothing.")
def compile(repo: str, config_path: str, out: str, spec_path: str, mapping_path: str,
            audit_path: str, candidates_path: str, decisions_path: str | None,
            no_detect: bool, dry_run: bool) -> None:
    """Compile REPO into a privacy-safe ghost repo + ghost spec."""
    from ghostc.compile import compile_repo

    try:
        cfg = load_config(config_path)
    except ConfigError as exc:
        raise SystemExit(f"INVALID CONFIG\n{exc}")

    cleared: set[str] = set()
    if decisions_path and Path(decisions_path).exists():
        from ghostc.review.store import DecisionStore
        cleared = DecisionStore(decisions_path).cleared_restricted()

    pending = [e for e in entities_needing_approval(cfg) if e["id"] not in cleared]
    if pending:
        names = ", ".join(e["id"] for e in pending)
        raise SystemExit(
            f"BLOCKED: {len(pending)} restricted entity(ies) awaiting human approval: {names}\n"
            "Clear them in `ghostc-review` (--decisions) or add `approved_by:` in the config."
        )

    result = compile_repo(repo, config_path=config_path, out=out, spec_path=spec_path,
                          mapping_path=mapping_path, audit_path=audit_path,
                          candidates_path=candidates_path, decisions_path=decisions_path,
                          detect=not no_detect, dry_run=dry_run)
    click.echo(result.summary())


@main.command("compile-spec")
@click.option("--task", "task_path", required=True, type=click.Path(),
              help="Real implementation task text: a file path, or '-' for stdin.")
@click.option("--config", "config_path", default="privacy.yaml", show_default=True,
              type=click.Path())
@click.option("--mapping", "mapping_path", default="workspace/private/mapping.json",
              show_default=True, type=click.Path(),
              help="Substitution source — boundary-internal, never crosses.")
@click.option("--out", "out_path", default="workspace/ghost-task.md", show_default=True,
              type=click.Path(),
              help="Sanitized TASK.md — this is what crosses to the consultancy side.")
@click.option("--audit", "audit_path", default="workspace/private/audit.jsonl",
              show_default=True, type=click.Path())
@click.option("--json", "as_json", is_flag=True, help="Emit the ghost task as JSON.")
def compile_spec(task_path: str, config_path: str, mapping_path: str, out_path: str,
                 audit_path: str, as_json: bool) -> None:
    """Compile a real implementation task into a sanitized ghost TASK.md. Fail closed."""
    from pathlib import Path

    from ghostc.spec import Rejection
    from ghostc.spec import compile_spec as _compile_spec

    try:
        load_config(config_path)
    except ConfigError as exc:
        raise SystemExit(f"INVALID CONFIG\n{exc}")

    text = (click.get_text_stream("stdin").read() if task_path == "-"
            else Path(task_path).read_text(encoding="utf-8"))

    try:
        spec = _compile_spec(text, config_path=config_path, mapping_path=mapping_path,
                             audit_path=audit_path, out_path=out_path)
    except Rejection as rej:
        raise SystemExit(f"REJECTED (fail closed)\n  {rej}")

    if as_json:
        import json

        click.echo(json.dumps(
            {"operation_id": spec.operation_id, "ghost_task": spec.ghost_task,
             "substitutions": [s.to_dict() for s in spec.substitutions]}, indent=2))
    else:
        click.echo(spec.summary())
        click.echo(f"  -> {out_path}")


# `ghostc run-task` (the LangGraph agent workflow) now lives in `client_agent.cli`
# as the `ghostc-agent` entrypoint — `ghostc` proper stays LLM-/langgraph-free.


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


@main.command()
@click.option("--repo", required=True, type=click.Path())
@click.option("--config", "config_path", default="privacy.yaml", show_default=True,
              type=click.Path())
@click.option("--out", default="workspace/baseline-ghost", show_default=True,
              type=click.Path(), help="Baseline repo — the keyword-redaction comparator.")
@click.option("--spec", "spec_path", default="workspace/baseline-spec.md",
              show_default=True, type=click.Path())
@click.option("--audit", "audit_path", default="workspace/private/audit.jsonl",
              show_default=True, type=click.Path())
@click.option("--dry-run", is_flag=True, help="Compute and report; write nothing.")
def baseline(repo: str, config_path: str, out: str, spec_path: str, audit_path: str,
             dry_run: bool) -> None:
    """Dumb keyword redaction — the fair baseline `eval` compares `compile` against."""
    from ghostc.baseline import baseline_repo

    try:
        load_config(config_path)
    except ConfigError as exc:
        raise SystemExit(f"INVALID CONFIG\n{exc}")

    result = baseline_repo(repo, config_path=config_path, out=out, spec_path=spec_path,
                           audit_path=audit_path, dry_run=dry_run)
    click.echo(result.summary())


@main.command("apply-patch")
@click.option("--ghost-diff", required=True, type=click.Path(exists=True))
@click.option("--mapping", "mapping_path", default="workspace/private/mapping.json",
              show_default=True, type=click.Path())
@click.option("--config", "config_path", default="privacy.yaml", show_default=True,
              type=click.Path())
@click.option("--real", "real_repo", default=None, type=click.Path(),
              help="Real repo to apply the translated diff into (with --apply).")
@click.option("--out", "out_path", default=None, type=click.Path(),
              help="Write the real diff here (default: stdout).")
@click.option("--mapping-version", type=int, default=None,
              help="Reject if the store's mapping_version differs.")
@click.option("--apply", "do_apply", is_flag=True,
              help="git apply --3way the translated diff onto a new branch in --real.")
@click.option("--branch", default="ghostc/reverse-patch", show_default=True)
@click.option("--audit", "audit_path", default="workspace/private/audit.jsonl",
              show_default=True, type=click.Path())
def apply_patch(ghost_diff: str, mapping_path: str, config_path: str,
                real_repo: str | None, out_path: str | None, mapping_version: int | None,
                do_apply: bool, branch: str, audit_path: str) -> None:
    """Translate a ghost PR diff into a real PR diff. Fail closed on ambiguity."""
    from ghostc.patch import Rejection, reverse_patch

    try:
        load_config(config_path)
    except ConfigError as exc:
        raise SystemExit(f"INVALID CONFIG\n{exc}")

    try:
        result = reverse_patch(ghost_diff, mapping_path, config_path=config_path,
                               real_repo=real_repo, mapping_version=mapping_version,
                               do_apply=do_apply, branch=branch, audit_path=audit_path)
    except Rejection as rej:
        raise SystemExit(f"REJECTED (fail closed)\n  {rej}")

    if out_path:
        from pathlib import Path

        Path(out_path).write_text(result.real_diff, encoding="utf-8")
        click.echo(result.summary())
    elif do_apply:
        click.echo(result.summary())
    else:
        click.echo(result.real_diff, nl=False)
        click.echo(result.summary(), err=True)


@main.command("eval")
@click.option("--real", default="workspace/real", show_default=True, type=click.Path())
@click.option("--config", "config_path", default="privacy.yaml", show_default=True,
              type=click.Path())
@click.option("--baseline-out", default="workspace/baseline-ghost", show_default=True,
              type=click.Path())
@click.option("--compile-out", default="workspace/ghost", show_default=True,
              type=click.Path())
@click.option("--report", default="workspace/eval-report", show_default=True,
              type=click.Path(), help="Writes <report>.md and <report>.csv.")
@click.option("--audit", "audit_path", default="workspace/private/audit.jsonl",
              show_default=True, type=click.Path())
def eval_(real: str, config_path: str, baseline_out: str, compile_out: str,
          report: str, audit_path: str) -> None:
    """Baseline keyword redaction vs `compile`: residual-leak metric (MVP, no agent)."""
    from ghostc.eval import run_eval

    try:
        load_config(config_path)
    except ConfigError as exc:
        raise SystemExit(f"INVALID CONFIG\n{exc}")

    result = run_eval(real, config_path=config_path, baseline_out=baseline_out,
                      compile_out=compile_out, report=report, audit_path=audit_path)
    click.echo(result.summary())


if __name__ == "__main__":
    main()
