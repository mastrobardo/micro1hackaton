"""`ghostc-mcp` — ghostc's deterministic capabilities as MCP tools.

For the client-side LLM planning/consistency agent to call, and for external reuse
(Claude Desktop, Claude Code). The `client_agent` graph's fixed pipeline nodes
still call `ghostc.*` in-process — this server is the LLM-driven surface, not a
replacement for that.

Every fail-closed condition returns ``{"ok": false, "error": ...}`` — never a
partial ghost artefact. Needs the ``[mcp]`` extra (``pip install -e '.[mcp]'``).
"""
from __future__ import annotations

import json
from pathlib import Path

try:
    from mcp.server.mcpserver import MCPServer
except ModuleNotFoundError as exc:  # pragma: no cover - exercised via ghostc-mcp
    raise SystemExit(
        "ghostc-mcp needs the [mcp] extra:  pip install -e '.[mcp]'\n"
        f"  ({exc})") from exc

server = MCPServer("ghostc", instructions=(
    "Deterministic privacy-compiler tools. compile_spec sanitizes an implementation "
    "task; screen scores outbound text for entities the config never named; discover "
    "scores sensitive-entity candidates in a repo; verify leak-scans a ghost tree; "
    "apply_patch reverse-compiles a ghost PR diff to a real diff. All fail closed."))


@server.tool()
def compile_spec(task: str, config_path: str = "privacy.yaml",
                 mapping_path: str = "workspace/private/mapping.json",
                 audit_path: str = "workspace/private/audit.jsonl") -> dict:
    """Rewrite a real implementation task into a sanitized ghost task. Fail closed:
    if any real value would survive, returns an error and no ghost task."""
    from ghostc.spec import Rejection, compile_spec as _compile_spec

    try:
        gs = _compile_spec(task, config_path=config_path, mapping_path=mapping_path,
                           audit_path=audit_path)
    except Rejection as rej:
        return {"ok": False, "error": str(rej), "rejected": True}
    return {"ok": True, "operation_id": gs.operation_id, "ghost_task": gs.ghost_task,
            "substitutions": [s.to_dict() for s in gs.substitutions]}


@server.tool()
def screen(text: str, real_text: str = "", config_path: str = "privacy.yaml",
           mapping_path: str = "workspace/private/mapping.json",
           candidates_path: str = "workspace/private/candidates.jsonl",
           decisions_path: str = "",
           audit_path: str = "workspace/private/audit.jsonl") -> dict:
    """Score outbound text for sensitive entities `privacy.yaml` never named — the
    second gate after compile_spec's closed-world substitution. Returns the scored
    findings and whether they block; it never rewrites anything.

    `real_text` is accepted for symmetry with the client agent's LLM adjudicator but
    is not scanned here: this tool is the deterministic layer only."""
    from ghostc.screen import screen_text

    res = screen_text(text, real_text=real_text or None, config_path=config_path,
                      mapping_path=mapping_path, candidates_path=candidates_path,
                      decisions_path=decisions_path or None, audit_path=audit_path)
    return {"ok": True, "operation_id": res.operation_id, "blocked": res.blocked,
            "reason": res.reason, "metrics": res.metrics(),
            "findings": [c.to_dict() for c in res.findings]}


@server.tool()
def discover(repo: str, config_path: str = "privacy.yaml",
             out: str = "workspace/private/candidates.jsonl",
             audit_path: str = "workspace/private/audit.jsonl") -> dict:
    """Scan REPO, score sensitive-entity candidates, propose the unconfigured ones."""
    from ghostc.discover import discover_repo

    res = discover_repo(repo, config_path=config_path, out=out, audit_path=audit_path)
    return {"ok": True, "operation_id": res.operation_id, "metrics": res.metrics,
            "candidates": [c.to_dict() for c in res.scan.candidates],
            "proposals": [c.to_dict() for c in res.proposals]}


@server.tool()
def verify(ghost: str, mapping_path: str = "workspace/private/mapping.json",
           config_path: str = "privacy.yaml", require_build: bool = False) -> dict:
    """Leak-scan a ghost tree (real values / mapping-shaped files / build gate). Fail closed."""
    from ghostc.verify import verify_ghost

    res = verify_ghost(ghost, mapping_path, config_path=config_path,
                       require_build=require_build)
    return {"ok": res.ok,
            "checks": [{"name": c.name, "status": c.status, "detail": c.detail}
                       for c in res.checks]}


@server.tool()
def apply_patch(ghost_diff_path: str,
                mapping_path: str = "workspace/private/mapping.json",
                config_path: str = "privacy.yaml",
                audit_path: str = "workspace/private/audit.jsonl") -> dict:
    """Reverse-compile a ghost PR diff into a real PR diff. Fail closed on any
    unmapped ghost alias, real value in the ghost diff, or version mismatch."""
    from ghostc.patch import Rejection, reverse_patch

    if not Path(ghost_diff_path).exists():
        return {"ok": False, "error": f"ghost diff not found: {ghost_diff_path}"}
    try:
        res = reverse_patch(ghost_diff_path, mapping_path, config_path=config_path,
                            do_apply=False, audit_path=audit_path)
    except Rejection as rej:
        return {"ok": False, "error": str(rej), "rejected": True}
    return {"ok": True, "real_diff": res.real_diff,
            "entities_resolved": res.entities_resolved,
            "lossy_entities": res.lossy_entities,
            "files": res.files, "hunks": res.hunks}


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
