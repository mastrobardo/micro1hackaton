"""Casing-aware alias rendering.

Each entity has one canonical kebab alias (``service-a``). A real token can appear
in many casings — ``booking-core`` (string), ``bookingCore`` (identifier),
``BOOKING_CORE_URL`` (env var). :func:`analyze` breaks an occurrence into lowercase
*segments* with their character spans plus a :class:`Style`; :func:`splice_span`
finds an entity's segment run inside a token and returns just that sub-range
re-cased, so several entities in one compound token are each rewritten in place.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+|[0-9]+")
_SEPS = ("_", "-", ".", " ")


@dataclass(frozen=True)
class Style:
    sep: str          # one of _SEPS, or "" for camel/pascal/single-run
    case: str         # "lower" | "upper" | "title" | "camel" | "pascal"


@dataclass(frozen=True)
class Segment:
    text: str         # lowercased
    start: int
    end: int


def analyze(token: str) -> tuple[list[Segment], Style]:
    """Break *token* into lowercase :class:`Segment`s + the :class:`Style` to rebuild it."""
    for sep in _SEPS:
        if sep in token:
            segs = [Segment(m.group(0).lower(), m.start(), m.end())
                    for m in re.finditer(f"[^{re.escape(sep)}]+", token)]
            return segs, Style(sep, _case_of([s.group(0)
                                              for s in re.finditer(f"[^{re.escape(sep)}]+", token)]))

    if token.isupper():
        return [Segment(token.lower(), 0, len(token))], Style("", "upper")
    if token.islower():
        return [Segment(token, 0, len(token))], Style("", "lower")
    segs = [Segment(m.group(0).lower(), m.start(), m.end()) for m in _CAMEL_RE.finditer(token)]
    return segs, Style("", "pascal" if token[:1].isupper() else "camel")


def render(segments: list[str], style: Style, lead_upper: bool | None = None) -> str:
    """Render *segments* in *style*. *lead_upper* overrides the first segment's case
    for camel/pascal contexts (used when splicing mid-identifier)."""
    if style.sep in _SEPS:
        if style.case == "upper":
            parts = [s.upper() for s in segments]
        elif style.case == "title":
            parts = [s.capitalize() for s in segments]
        else:
            parts = [s.lower() for s in segments]
        return style.sep.join(parts)

    # sep == ""  → camel / pascal / bare run
    if style.case in ("camel", "pascal"):
        first_upper = (style.case == "pascal") if lead_upper is None else lead_upper
        head = segments[0].capitalize() if first_upper else segments[0].lower()
        return head + "".join(s.capitalize() for s in segments[1:])
    # bare lower / upper single run: a multi-segment ghost needs a separator to stay legible
    if len(segments) > 1:
        joiner = "-"
        return joiner.join(s.upper() if style.case == "upper" else s.lower() for s in segments)
    return segments[0].upper() if style.case == "upper" else segments[0].lower()


def splice_span(token: str, stem: list[str], ghost_segments: list[str]
                ) -> tuple[int, int, str] | None:
    """If *stem* is a contiguous segment run of *token*, return
    (char_start, char_end, replacement) for just that run, re-cased in *token*'s style.
    """
    segs, style = analyze(token)
    n = len(stem)
    lows = [s.text for s in segs]
    for i in range(len(lows) - n + 1):
        if lows[i:i + n] == stem:
            cstart, cend = segs[i].start, segs[i + n - 1].end
            lead_upper = token[cstart].isupper() if cstart < len(token) else None
            return cstart, cend, render(ghost_segments, style, lead_upper)
    return None


def render_like(sample: str, ghost_segments: list[str]) -> str:
    """Render *ghost_segments* in the style detected from a matched literal *sample*."""
    _, style = analyze(sample)
    return render(ghost_segments, style)


def _case_of(parts: list[str]) -> str:
    alpha = [p for p in parts if any(c.isalpha() for c in p)]
    if alpha and all(p.isupper() for p in alpha):
        return "upper"
    if alpha and all(p[:1].isupper() for p in alpha):
        return "title"
    return "lower"
