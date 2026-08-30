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

# call callees whose first string argument is a module specifier
_SPEC_CALLS = {
    "require", "import", "require.resolve", "jest.mock", "jest.unmock",
    "jest.doMock", "jest.dontMock", "jest.requireActual", "jest.requireMock",
    "jest.setMock", "import.meta.resolve",
}


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


def _spec_string_ranges(root, data: bytes) -> set[tuple[int, int]]:
    """Byte ranges of string / fragment nodes that are a module specifier
    (`import ... from 'x'`, `require('x')`, `jest.mock('x')`, ...)."""
    ranges: set[tuple[int, int]] = set()

    def mark(node) -> None:
        if node is None:
            return
        frags = [c for c in node.children if c.type in _STRING]
        for f in frags:
            ranges.add((f.start_byte, f.end_byte))
        if not frags and node.type in _STRING | {"string"}:
            ranges.add((node.start_byte, node.end_byte))

    def walk(n) -> None:
        if n.type in ("import_statement", "export_statement"):
            mark(n.child_by_field_name("source"))
        elif n.type == "call_expression":
            fn = n.child_by_field_name("function")
            args = n.child_by_field_name("arguments")
            if fn is not None and args is not None:
                name = data[fn.start_byte:fn.end_byte].decode("utf-8", "replace")
                if name in _SPEC_CALLS or fn.type == "import":
                    for a in args.named_children:
                        mark(a)
                        break
        for c in n.children:
            walk(c)

    walk(root)
    return ranges


def compile_source(source: str, matchers: list[EntityMatcher], lang: str
                   ) -> tuple[str, list[Hit]]:
    """Return (rewritten source, hits). Deterministic for a given (source, config)."""
    parser = get_parser(lang)
    data = source.encode("utf-8")
    tree = parser.parse(data)
    spec_ranges = _spec_string_ranges(tree.root_node, data)

    edits: list[tuple[int, int, bytes]] = []
    hits: list[Hit] = []

    def visit(node) -> None:
        kind = _kind_of(node.type)
        if kind is not None:
            text = data[node.start_byte:node.end_byte].decode("utf-8")
            if kind == "string" and (node.start_byte, node.end_byte) in spec_ranges:
                kind = "import_specifier"
            new_text, node_hits = transform_text(text, kind, matchers)
            line = node.start_point[0] + 1
            changed = new_text != text
            if changed:
                edits.append((node.start_byte, node.end_byte, new_text.encode("utf-8")))
            for h in node_hits:
                if changed or h.kept:      # keep parity: only real edits + kept specifiers
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
