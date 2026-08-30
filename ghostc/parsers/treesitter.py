"""tree-sitter front-end: JS / TS / TSX / HCL.

We only ever edit the text of a small, fixed set of node types — identifiers,
string *content* (not the quotes), and comments — so structure and formatting are
preserved byte-for-byte everywhere else. Edits are applied back-to-front so byte
offsets stay valid.
"""
from __future__ import annotations

import os

from tree_sitter_language_pack import get_parser

from ghostc.matching import EntityMatcher, Hit, transform_text

LANG_BY_EXT = {
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".mts": "typescript", ".cts": "typescript",
    ".tsx": "tsx",
    ".tf": "hcl", ".hcl": "hcl", ".tfvars": "hcl",
}

_IDENT = {
    "identifier", "property_identifier", "shorthand_property_identifier",
    "shorthand_property_identifier_pattern", "type_identifier",
}
_STRING = {"string_fragment", "template_literal"}   # inner content, no delimiters
_COMMENT = {"comment"}


def language_for(path: str) -> str | None:
    return LANG_BY_EXT.get(os.path.splitext(path)[1].lower())


def _kind_of(node_type: str) -> str | None:
    if node_type in _IDENT:
        return "identifier"
    if node_type in _STRING:
        return "string"
    if node_type in _COMMENT:
        return "comment"
    return None


def compile_source(source: str, matchers: list[EntityMatcher], lang: str
                   ) -> tuple[str, list[Hit]]:
    """Return (rewritten source, hits). Deterministic for a given (source, config)."""
    parser = get_parser(lang)
    data = source.encode("utf-8")
    tree = parser.parse(data)

    edits: list[tuple[int, int, bytes]] = []
    hits: list[Hit] = []

    def visit(node) -> None:
        kind = _kind_of(node.type)
        if kind is not None:
            text = data[node.start_byte:node.end_byte].decode("utf-8")
            new_text, node_hits = transform_text(text, kind, matchers)
            if new_text != text:
                edits.append((node.start_byte, node.end_byte, new_text.encode("utf-8")))
                line = node.start_point[0] + 1
                for h in node_hits:
                    h.line = line
                    hits.append(h)
            return  # identifiers / fragments / comments are leaves for our purposes
        for child in node.children:
            visit(child)

    visit(tree.root_node)

    out = data
    for start, end, replacement in sorted(edits, key=lambda e: e[0], reverse=True):
        out = out[:start] + replacement + out[end:]
    return out.decode("utf-8"), hits
