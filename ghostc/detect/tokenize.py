"""Detection-layer tokenizer.

``ghostc.matching`` only splits on ``-`` / ``_``. The detector has to see the
entity stem inside URLs (``api.meridianaero.example``), namespaces
(``flight-cache:meridian:v4``), paths (``/etc/contoso/vendors/meridian``), scoped
packages (``@meridianaero/flight-sdk``) and camelCase symbols alike, so this
tokenizer splits on ``- _ . : / @`` *and* camel-case boundaries.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[-_.:/@][A-Za-z0-9]+)+|[A-Za-z0-9]{2,}")
_SEP_RE = re.compile(r"[-_.:/@]+")
_CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")
_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def segments(token: str) -> list[str]:
    """Lowercase sub-parts of *token*: separator split, then camel-case split."""
    out: list[str] = []
    for part in _SEP_RE.split(token):
        if not part:
            continue
        out.extend(m.group(0).lower() for m in _CAMEL_RE.finditer(part))
    return out


def words(text: str) -> list[str]:
    """Lowercase alphanumeric words of a free-text string (name / prose)."""
    return [m.group(0).lower() for m in _WORD_RE.finditer(text)]


@dataclass(frozen=True)
class Token:
    text: str
    start: int
    end: int
    segments: tuple[str, ...]

    @property
    def norm(self) -> str:
        """Canonical kebab form of the token — the aggregation key for a proposal."""
        return "-".join(self.segments)


def tokens(text: str) -> list[Token]:
    out: list[Token] = []
    for m in _TOKEN_RE.finditer(text):
        segs = tuple(segments(m.group(0)))
        if segs:
            out.append(Token(m.group(0), m.start(), m.end(), segs))
    return out


def contains_run(haystack: list[str], needle: list[str]) -> int | None:
    """Index where *needle* appears as a contiguous run in *haystack*, else None."""
    if not needle or len(needle) > len(haystack):
        return None
    for i in range(len(haystack) - len(needle) + 1):
        if haystack[i:i + len(needle)] == needle:
            return i
    return None
