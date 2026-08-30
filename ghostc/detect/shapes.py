"""Structural-shape detection — stdlib ``re`` only.

Shapes are *review-only* evidence: a match says "this string is shaped like a
secret / account id / internal host", never "transform it". They carry a modest
weight and, on their own, keep a candidate in the human-review queue.

Generalised on purpose: the fixture configures the literal ``sk_live_…`` key, but
``adversary.js`` uses ``mas_live_…`` — the shape has to catch the family, not the
one spelling.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_L = r"(?<![A-Za-z0-9])"     # left token boundary (no leading alnum)
_R = r"(?![A-Za-z0-9])"      # right token boundary

_SHAPES: list[tuple[str, re.Pattern[str]]] = [
    ("rfc1918_ip", re.compile(
        _L + r"(?:10(?:\.\d{1,3}){3}"
        r"|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}"
        r"|192\.168(?:\.\d{1,3}){2})" + _R)),
    ("aws_account_id", re.compile(_L + r"\d{12}" + _R)),
    ("aws_access_key_id", re.compile(_L + r"AKIA[0-9A-Z]{16}" + _R)),
    ("prefixed_secret", re.compile(
        _L + r"[a-z][a-z0-9]{1,15}_(?:live|test|prod|sk|pk)_[A-Za-z0-9]{12,}" + _R)),
    ("named_secret", re.compile(
        _L + r"[a-z][a-z0-9-]{2,}-(?:client-secret|api-key|secret)-[A-Za-z0-9]{6,}" + _R)),
    ("jwt", re.compile(
        _L + r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}" + _R)),
    ("contract_id", re.compile(_L + r"[A-Z]{2,5}-[A-Z]{2,3}-\d{4}-\d{2,4}" + _R)),
    ("tenant_id", re.compile(_L + r"tenant-[a-z0-9]+(?:-[a-z0-9]+)+" + _R)),
    ("internal_host", re.compile(
        r"(?<![A-Za-z0-9.-])(?:[a-z0-9-]+\.){1,}(?:internal|intranet|corp|local)"
        r"(?:\.[a-z]{2,})?" + _R)),
    ("scoped_npm_package", re.compile(
        r"(?<![A-Za-z0-9._-])@[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9._-]*")),
    ("email", re.compile(
        _L + r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}" + _R)),
]

# weight the *shape* signal carries per kind (noisy-OR contribution; review-only)
_WEIGHT = {
    "rfc1918_ip": 0.40,
    "aws_account_id": 0.30,       # 12 digits is common — weak on its own
    "aws_access_key_id": 0.55,
    "prefixed_secret": 0.55,
    "named_secret": 0.50,
    "jwt": 0.50,
    "contract_id": 0.45,
    "tenant_id": 0.45,
    "internal_host": 0.45,
    "scoped_npm_package": 0.45,
    "email": 0.35,
}


@dataclass(frozen=True)
class ShapeHit:
    kind: str
    text: str
    start: int
    end: int

    @property
    def weight(self) -> float:
        return _WEIGHT.get(self.kind, 0.40)


def shape_hits(text: str) -> list[ShapeHit]:
    hits: list[ShapeHit] = []
    for kind, rx in _SHAPES:
        for m in rx.finditer(text):
            hits.append(ShapeHit(kind, m.group(0), m.start(), m.end()))
    hits.sort(key=lambda h: (h.start, -(h.end - h.start)))
    return hits
