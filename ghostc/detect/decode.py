"""Minimal de-obfuscation pass — string concat, ``[...].join()``, base64.

``adversary.js`` hides the vendor with ``'meri' + 'dianaero'``,
``['MERIDIAN','API','KEY'].join('_')`` and base64 blobs. Static string matching
cannot see through those, so this pass reconstructs the literal values and hands
them back for re-scanning.

Everything here is heuristic, so the caller only raises a signal when the
reconstructed text contains an **already-confirmed** entity stem — otherwise the
false-positive rate on ordinary code would be unacceptable. Nothing decoded here
is ever auto-transformed.
"""
from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass

_STR = r"(?:'([^'\n]*)'|\"([^\"\n]*)\")"
_CONCAT_RE = re.compile(_STR + r"(?:\s*\+\s*" + _STR + r")+")
_JOIN_RE = re.compile(
    r"\[\s*((?:" + _STR + r"\s*,?\s*)+)\]\s*\.\s*join\(\s*" + _STR + r"\s*\)")
_ELEM_RE = re.compile(_STR)
_B64_RE = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{16,}={0,2}(?![A-Za-z0-9+/=])")


@dataclass(frozen=True)
class Decoded:
    text: str            # the reconstructed literal
    line: int            # 1-based line of the construct in the source
    method: str          # "concat" | "join" | "base64"


def _line_of(source: str, pos: int) -> int:
    return source.count("\n", 0, pos) + 1


def _pieces(blob: str) -> list[str]:
    return [a if a is not None else b for a, b in _ELEM_RE.findall(blob)]


def _folded(m: re.Match[str]) -> str:
    parts: list[str] = []
    for a, b in _ELEM_RE.findall(m.group(0)):
        parts.append(a if a is not None else b)
    return "".join(parts)


def decoded_literals(source: str) -> list[Decoded]:
    """Reconstructed string values from concat / join / base64 constructs in *source*."""
    out: list[Decoded] = []

    for m in _CONCAT_RE.finditer(source):
        out.append(Decoded(_folded(m), _line_of(source, m.start()), "concat"))

    for m in _JOIN_RE.finditer(source):
        elems = _pieces(m.group(1))
        sep_a, sep_b = m.groups()[-2:]
        sep = sep_a if sep_a is not None else (sep_b or "")
        out.append(Decoded(sep.join(elems), _line_of(source, m.start()), "join"))

    for m in _B64_RE.finditer(source):
        blob = m.group(0)
        if len(blob) % 4:
            continue
        try:
            raw = base64.b64decode(blob, validate=True)
        except (binascii.Error, ValueError):
            continue
        try:
            txt = raw.decode("ascii")
        except UnicodeDecodeError:
            continue
        if txt.isprintable() and len(txt) >= 6:
            out.append(Decoded(txt, _line_of(source, m.start()), "base64"))

    # de-dupe, keep first sighting
    seen: set[tuple[str, str]] = set()
    uniq: list[Decoded] = []
    for d in out:
        key = (d.text, d.method)
        if key not in seen:
            seen.add(key)
            uniq.append(d)
    return uniq
