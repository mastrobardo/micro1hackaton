"""Language front-ends for node-scoped transformation.

tree-sitter grammars: javascript, typescript, tsx, hcl.
Fallback (`.yml`, `.json`, `.env*`, `.md`, Dockerfile): a scoped matcher that only
replaces configured entity values — never arbitrary strings or identifiers.

Each parser exposes:
    occurrences(source: str, entity_matchers) -> list[Occurrence]
    rewrite(source: str, edits) -> str        # deterministic, byte-stable
"""
