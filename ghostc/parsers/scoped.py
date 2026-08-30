"""Fallback front-end for files with no grammar: .env*, .json, .yml/.yaml, .md,
Dockerfile, plain text.

No AST, so "scoped" means: matchers only ever fire on *configured* entity values
(literals, stems, regexes) — never on arbitrary strings or keys. Whole-file text
is treated as one node of kind "string".

``package.json`` is special-cased: the *keys* of ``dependencies`` /
``devDependencies`` / ``peerDependencies`` / ``optionalDependencies`` /
``resolutions`` are package specifiers — renaming them would break
``yarn install`` in the ghost — so they are kept verbatim (reported as
``Hit.kept``) exactly like an ``import``/``require`` specifier.
"""
from __future__ import annotations

import os
import re

from ghostc.matching import EntityMatcher, Hit, transform_text

# handled here when tree-sitter has no grammar for the extension
_TEXT_EXTS = {
    ".env", ".json", ".yml", ".yaml", ".md", ".txt", ".ini", ".toml", ".cfg",
    ".sh", ".xml", ".html", ".css", ".conf", ".properties", ".example",
}
_TEXT_NAMES = {"Dockerfile", ".env", ".gitignore", ".dockerignore", ".npmrc", ".nvmrc"}

_DEP_SECTIONS = (
    "dependencies", "devDependencies", "peerDependencies", "optionalDependencies",
    "bundledDependencies", "bundleDependencies", "resolutions", "overrides",
)
_KEY_RE = re.compile(r'"((?:@[^"/]+/)?[^"]+)"\s*:')


def handles(path: str) -> bool:
    name = os.path.basename(path)
    if name in _TEXT_NAMES or name.startswith(".env"):
        return True
    return os.path.splitext(name)[1].lower() in _TEXT_EXTS


def compile_source(source: str, matchers: list[EntityMatcher], rel: str = ""
                   ) -> tuple[str, list[Hit]]:
    if os.path.basename(rel) == "package.json":
        return _compile_package_json(source, matchers)
    new_text, hits = transform_text(source, "string", matchers)
    for h in hits:
        h.line = source.count("\n", 0, h.start) + 1
    return new_text, hits


def _matched_brace(text: str, open_idx: int) -> int:
    depth = 0
    for i in range(open_idx, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(text)


def _dep_key_spans(source: str) -> list[tuple[int, int]]:
    """(start, end) of each dependency-map key's *inner* text (between the quotes)."""
    spans: list[tuple[int, int]] = []
    for section in _DEP_SECTIONS:
        for m in re.finditer(r'"' + re.escape(section) + r'"\s*:\s*\{', source):
            close = _matched_brace(source, source.index("{", m.start()))
            body = source[m.end():close]
            off = m.end()
            for km in _KEY_RE.finditer(body):
                spans.append((off + km.start(1), off + km.end(1)))
    spans.sort()
    return spans


def _compile_package_json(source: str, matchers: list[EntityMatcher]
                          ) -> tuple[str, list[Hit]]:
    keep = _dep_key_spans(source)
    out: list[str] = []
    hits: list[Hit] = []
    pos = 0
    for s, e in keep:
        if s < pos:                       # nested / overlapping — skip
            continue
        seg = source[pos:s]
        nt, seg_hits = transform_text(seg, "string", matchers, base=pos)
        out.append(nt)
        hits.extend(seg_hits)

        key = source[s:e]
        _, key_hits = transform_text(key, "import_specifier", matchers, base=s)
        for h in key_hits:
            if h.kept:
                hits.append(h)
        out.append(key)                   # dependency key kept verbatim
        pos = e

    tail_nt, tail_hits = transform_text(source[pos:], "string", matchers, base=pos)
    out.append(tail_nt)
    hits.extend(tail_hits)

    rebuilt = "".join(out)
    for h in hits:
        # line numbers are relative to the *original* source (offsets are stable up
        # to each kept key, and kept keys are unchanged length)
        h.line = source.count("\n", 0, min(h.start, len(source))) + 1
    return rebuilt, hits
