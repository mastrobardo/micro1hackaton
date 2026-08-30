"""Fallback front-end for files with no grammar: .env*, .json, .yml/.yaml, .md,
Dockerfile, plain text.

No AST, so "scoped" means: matchers only ever fire on *configured* entity values
(literals, stems, regexes) — never on arbitrary strings or keys. Whole-file text
is treated as one node of kind "string".
"""
from __future__ import annotations

import os

from ghostc.matching import EntityMatcher, Hit, transform_text

# handled here when tree-sitter has no grammar for the extension
_TEXT_EXTS = {
    ".env", ".json", ".yml", ".yaml", ".md", ".txt", ".ini", ".toml", ".cfg",
    ".sh", ".xml", ".html", ".css", ".conf", ".properties", ".example",
}
_TEXT_NAMES = {"Dockerfile", ".env", ".gitignore", ".dockerignore", ".npmrc", ".nvmrc"}


def handles(path: str) -> bool:
    name = os.path.basename(path)
    if name in _TEXT_NAMES or name.startswith(".env"):
        return True
    return os.path.splitext(name)[1].lower() in _TEXT_EXTS


def compile_source(source: str, matchers: list[EntityMatcher]) -> tuple[str, list[Hit]]:
    new_text, hits = transform_text(source, "string", matchers)
    for h in hits:
        h.line = source.count("\n", 0, h.start) + 1
    return new_text, hits
