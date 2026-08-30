"""The result shape of the detection pass + the score-combination rule.

A :class:`Candidate` is one *entity* the detector believes appears in the repo —
configured (``entity_id`` set) or newly proposed (``entity_id is None``). Every
distinct spelling that pointed at it is an :class:`Occurrence`; every piece of
evidence is a :class:`Signal`.

``score`` combines the signals with a **noisy-OR**::

    score = 1 - Π(1 - wᵢ)

so independent weak signals accumulate and a single ``exact`` signal (weight 1.0)
short-circuits to ``1.00``. ``action`` is then derived from the score, the
privacy level, and whether the evidence is *structural* (see
:func:`has_hard_evidence`) rather than purely lexical/semantic.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Signals whose presence makes a high score trustworthy enough to auto-transform.
# Fuzzy / semantic / shape / acronym evidence alone never crosses into ``auto``.
_HARD_SIGNALS = {"exact", "stem", "import_ref", "symbol_context"}
_GRAPH_HARD_MIN = 0.9

# Short label per signal, joined to form the "evidence" column of the report.
_LABEL = {
    "exact": "exact",
    "stem": "identifier token",
    "import_ref": "package / import",
    "symbol_context": "symbol + repo context",
    "graph": "reference graph",
    "alias_enum": "declared alias",
    "acronym": "acronym",
    "fuzzy": "lexical + AST",
    "shape": "structural shape",
    "decoded": "decoded literal",
    "semantic": "semantic",
    "weak": "weak / no evidence",
}


@dataclass(frozen=True)
class Signal:
    """One piece of evidence. ``weight`` is an independent probability in [0, 1]."""

    name: str
    weight: float
    detail: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "weight": round(self.weight, 4), "detail": self.detail}


@dataclass(frozen=True)
class Occurrence:
    file: str
    line: int
    surface: str
    node_kind: str = ""          # identifier | string | comment | filename | env | import

    def to_dict(self) -> dict:
        return {"file": self.file, "line": self.line,
                "surface": self.surface, "node_kind": self.node_kind}


@dataclass
class Candidate:
    surface: str                              # representative spelling
    entity_id: str | None                     # configured entity, or None for a proposal
    kind: str | None
    level: str | None
    score: float
    signals: list[Signal]
    action: str                               # "auto" | "review" | "ignore"
    occurrences: list[Occurrence] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    proposed_ghost: str | None = None         # set only when auto_alias mints one

    @property
    def resolved(self) -> bool:
        return self.entity_id is not None

    @property
    def evidence(self) -> str:
        return evidence_label(self.signals)

    def to_dict(self) -> dict:
        return {
            "surface": self.surface,
            "entity_id": self.entity_id,
            "kind": self.kind,
            "level": self.level,
            "score": round(self.score, 4),
            "action": self.action,
            "evidence": self.evidence,
            "signals": [s.to_dict() for s in self.signals],
            "aliases": sorted(self.aliases),
            "proposed_ghost": self.proposed_ghost,
            "occurrences": [o.to_dict() for o in self.occurrences],
        }


def combine_score(signals: list[Signal]) -> float:
    """Noisy-OR over independent signal weights. An exact (weight ≥ 1) hit → 1.0."""
    ws = [min(1.0, max(0.0, s.weight)) for s in signals if s.weight > 0]
    if not ws:
        return 0.0
    if any(w >= 1.0 for w in ws):
        return 1.0
    prod = 1.0
    for w in ws:
        prod *= 1.0 - w
    return round(1.0 - prod, 4)


def has_hard_evidence(signals: list[Signal]) -> bool:
    """True when a *structural* signal backs the candidate (not fuzzy/semantic alone)."""
    for s in signals:
        if s.weight <= 0:
            continue
        if s.name in _HARD_SIGNALS:
            return True
        if s.name == "graph" and s.weight >= _GRAPH_HARD_MIN:
            return True
    return False


def evidence_label(signals: list[Signal]) -> str:
    contributing = sorted((s for s in signals if s.weight > 0),
                          key=lambda s: s.weight, reverse=True)
    if not contributing:
        return "weak / no evidence"
    names: list[str] = []
    for s in contributing:
        if s.name not in names:
            names.append(s.name)
    if names == ["semantic"]:
        return "semantic only"
    if names == ["weak"]:
        return "weak / no evidence"
    return " + ".join(_LABEL.get(n, n) for n in names[:3])


def classify(*, score: float, level: str | None, resolved: bool,
             signals: list[Signal], settings) -> str:
    """auto / review / ignore, from the score + level + evidence strength.

    ``auto`` requires a hard structural signal *and* score ≥ ``auto_threshold``.
    ``restricted`` never auto-transforms (human approval gate). An unconfigured
    proposal only auto-transforms when ``settings.auto_alias`` is on.
    """
    if score >= settings.auto_threshold and has_hard_evidence(signals):
        if level == "restricted":
            return "review"
        if resolved or settings.auto_alias:
            return "auto"
        return "review"
    if score >= settings.review_threshold:
        return "review"
    return "ignore"
