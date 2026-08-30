"""Turn privacy.yaml entities into deterministic occurrence finders.

A matcher only ever fires on a *configured* entity — never on an arbitrary
identifier or string. Three match kinds:

* ``stem``    — a lowercase segment list; matches a contiguous segment run inside
                an identifier / hyphen-or-underscore token, re-cased in place.
                Several entities in one compound token are each spliced separately.
* ``literal`` — a case-sensitive exact substring (for prose in strings / comments).
* ``regex``   — escape hatch; whole match → the canonical kebab ghost.

``transform_text`` applies all matchers to one node's text: candidates are ranked
longest-span-first (a domain literal beats an inner token), ``remove`` and higher
sensitivity win ties, and picks are non-overlapping.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ghostc.aliasing import analyze, render_like, splice_span

# a token we scan for inside string / comment text: letters/digits joined by - or _
# ('.' is NOT a joiner, so "booking-core.internal" yields the token "booking-core")
_SCAN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*")
_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*$")

# kinds whose real spellings vary by casing → drive them through the segment engine
_SEGMENT_KINDS = {"vendor", "client", "internal_service", "person"}
_NAME_SHAPED = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:[ _-][A-Za-z0-9]+)*$")
_LEVEL_RANK = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}


@dataclass
class Hit:
    start: int
    end: int
    real: str
    ghost: str
    entity_id: str
    level: str
    remove: bool = False
    line: int = 0

    @property
    def rank(self) -> tuple:
        # used only to break span-length ties: remove first, then sensitivity, then id
        return (0 if self.remove else 1, -_LEVEL_RANK.get(self.level, 0), self.entity_id)


@dataclass
class EntityMatcher:
    entity_id: str
    kind: str
    level: str
    strategy: str
    ghost: str                       # canonical kebab; "" when strategy == remove
    remove: bool
    ghost_segments: list[str]
    stems: list[list[str]] = field(default_factory=list)
    literals: list[str] = field(default_factory=list)
    regexes: list[re.Pattern] = field(default_factory=list)

    @property
    def use_segments(self) -> bool:
        return self.kind in _SEGMENT_KINDS

    def _seg_hits(self, token: str, base: int) -> list[Hit]:
        """Sub-span hits for every stem that matches a segment run in *token*."""
        if self.remove or not self.use_segments:
            return []
        out: list[Hit] = []
        for stem in self.stems:
            span = splice_span(token, stem, self.ghost_segments)
            if span is None:
                continue
            cs, ce, repl = span
            if repl != token[cs:ce]:
                out.append(Hit(base + cs, base + ce, token[cs:ce], repl,
                               self.entity_id, self.level, self.remove))
        return out

    def identifier_hits(self, token: str, base: int = 0) -> list[Hit]:
        return self._seg_hits(token, base)

    def text_hits(self, text: str, base: int) -> list[Hit]:
        hits: list[Hit] = []
        for rx in self.regexes:
            for m in rx.finditer(text):
                hits.append(Hit(base + m.start(), base + m.end(), m.group(0),
                                self.ghost, self.entity_id, self.level, self.remove))
        for lit in self.literals:
            repl = "" if self.remove else (
                render_like(lit, self.ghost_segments)
                if self.use_segments and _NAME_SHAPED.match(lit) else self.ghost)
            i = text.find(lit)
            while i != -1:
                hits.append(Hit(base + i, base + i + len(lit), lit, repl,
                                self.entity_id, self.level, self.remove))
                i = text.find(lit, i + len(lit))
        if self.use_segments and not self.remove:
            for m in _SCAN_RE.finditer(text):
                hits.extend(self._seg_hits(m.group(0), base + m.start()))
        return hits


def build_matchers(config: dict) -> list[EntityMatcher]:
    out: list[EntityMatcher] = []
    for e in config.get("entities", []):
        remove = e["strategy"] == "remove"
        ghost = e.get("ghost", "")
        ghost_segments = ghost.split("-") if ghost else []
        stems: list[list[str]] = []
        literals: list[str] = [e["real"]]
        regexes: list[re.Pattern] = []

        if e["kind"] in _SEGMENT_KINDS and _TOKEN_RE.match(e["real"]):
            stems.append(_seg(e["real"]))
        for m in e.get("match", []):
            if m["kind"] == "identifier":
                stems.append(_seg(m["value"]))
            elif m["kind"] == "literal":
                literals.append(m["value"])
            elif m["kind"] == "regex":
                regexes.append(re.compile(m["value"]))

        out.append(EntityMatcher(
            entity_id=e["id"], kind=e["kind"], level=e["level"], strategy=e["strategy"],
            ghost=ghost, remove=remove, ghost_segments=ghost_segments,
            stems=_dedup(stems), literals=_dedup_longest_first(literals), regexes=regexes,
        ))
    return out


def transform_text(text: str, node_kind: str, matchers: list[EntityMatcher],
                   base: int = 0) -> tuple[str, list[Hit]]:
    """Apply every matcher to one node's *text*. Returns (new_text, picked hits).

    node_kind: "identifier" | "string" | "comment" | "filename".
    """
    candidates: list[Hit] = []
    if node_kind == "identifier":
        for m in matchers:
            candidates.extend(m.identifier_hits(text, base))
    else:
        for m in matchers:
            candidates.extend(m.text_hits(text, base))
    if not candidates:
        return text, []

    candidates.sort(key=lambda h: (-(h.end - h.start), h.start, h.rank))
    picked: list[Hit] = []
    taken: list[tuple[int, int]] = []
    for h in candidates:
        if any(not (h.end <= ts or h.start >= te) for ts, te in taken):
            continue
        taken.append((h.start, h.end))
        picked.append(h)

    buf = text
    for h in sorted(picked, key=lambda h: h.start, reverse=True):
        s, e = h.start - base, h.end - base
        buf = buf[:s] + h.ghost + buf[e:]
    picked.sort(key=lambda h: h.start)
    return buf, picked


def _seg(token: str) -> list[str]:
    segs, _ = analyze(token)
    return [s.text for s in segs]


def _dedup(stems: list[list[str]]) -> list[list[str]]:
    seen: set[tuple[str, ...]] = set()
    out = []
    for s in stems:
        t = tuple(s)
        if t not in seen:
            seen.add(t)
            out.append(s)
    return out


def _dedup_longest_first(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(values), key=len, reverse=True)
