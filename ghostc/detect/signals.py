"""Evidence extractors — each returns a :class:`~ghostc.detect.candidate.Signal`
(or ``None``) with an independent weight that the noisy-OR later combines.

Default weights live here as ``W_*`` constants and can be overridden per signal
name through ``detection.signal_weights`` in ``privacy.yaml``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from ghostc.detect.candidate import Signal
from ghostc.detect.semantic import similarity
from ghostc.detect.tokenize import contains_run, segments, words

W_EXACT = 1.0
W_STEM = 0.85
W_STEM_PREFIX = 0.6          # stem is the prefix of a single longer segment
W_IMPORT_REF = 0.9
W_SYMBOL = 0.8
W_ALIAS_ENUM = 0.8
W_ACRONYM_ALONE = 0.22
W_ACRONYM_CORROBORATED = 0.7
W_FUZZY_MIN = 0.45
W_FUZZY_MAX = 0.7
W_SEMANTIC_CAP = 0.45
W_GRAPH_CAP = 0.85
W_WEAK = 0.02

_STOPWORDS = {
    "client", "clients", "provider", "providers", "service", "services", "vendor",
    "vendors", "config", "endpoint", "api", "url", "key", "secret", "data", "systems",
    "system", "core", "app", "platform", "gateway", "internal", "flight", "search",
    "request", "response", "default", "primary", "main", "base", "http", "https",
}

_ALIAS_ENUM_RE = re.compile(
    r"(?:also\s+known\s+as|known\s+(?:internally\s+)?as|aka|aliases?)\s*:?\s*(.+?)"
    r"(?:\n\s*\n|\Z)", re.IGNORECASE | re.DOTALL)
_ALIAS_ITEM_RE = re.compile(r"[-*•]\s*([A-Za-z0-9][A-Za-z0-9 ._/-]{1,40})")


@dataclass
class EntityProfile:
    entity_id: str | None
    kind: str | None
    level: str | None
    names: list[str] = field(default_factory=list)     # full spellings
    stems: list[list[str]] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)   # short forms
    note: str = ""

    @property
    def is_proposal(self) -> bool:
        return self.entity_id is None

    def semantic_texts(self) -> list[str]:
        return [t for t in (*self.names, *self.aliases, self.note) if t]


def profile_from_config(entity: dict) -> EntityProfile:
    real = entity.get("real", "")
    names = [real]
    aliases: list[str] = []
    stems = [segments(real)] if segments(real) else []
    for m in entity.get("match", []):
        val = m.get("value", "")
        if not val:
            continue
        if m["kind"] == "literal":
            (names if " " in val else aliases).append(val)
        elif m["kind"] == "identifier":
            aliases.append(val)
        if segments(val):
            stems.append(segments(val))
    # de-dupe stems
    seen: set[tuple] = set()
    uniq_stems = []
    for s in stems:
        if tuple(s) not in seen:
            seen.add(tuple(s))
            uniq_stems.append(s)
    return EntityProfile(
        entity_id=entity["id"], kind=entity.get("kind"), level=entity.get("level"),
        names=[n for n in dict.fromkeys(names) if n], stems=uniq_stems,
        aliases=[a for a in dict.fromkeys(aliases) if a], note=entity.get("note", ""),
    )


# --------------------------------------------------------------------------- #
# per-surface signals                                                         #
# --------------------------------------------------------------------------- #

def exact_signal(surface: str, prof: EntityProfile) -> Signal | None:
    if surface in prof.names or surface in prof.aliases:
        return Signal("exact", W_EXACT, surface)
    return None


def stem_signal(segs: list[str], prof: EntityProfile) -> Signal | None:
    best: Signal | None = None
    for stem in prof.stems:
        if not stem:
            continue
        if contains_run(segs, stem) is not None:
            return Signal("stem", W_STEM, "-".join(stem))
        if len(stem) == 1 and len(stem[0]) >= 5:
            for seg in segs:
                if seg != stem[0] and seg.startswith(stem[0]):
                    best = Signal("stem", W_STEM_PREFIX, f"{stem[0]}~{seg}")
    return best


def import_ref_signal(surface: str, node_kind: str) -> Signal | None:
    if surface.startswith("@") and "/" in surface:
        return Signal("import_ref", W_IMPORT_REF, "scoped package")
    if node_kind in ("import", "env"):
        return Signal("import_ref", W_IMPORT_REF, node_kind)
    return None


def symbol_signal(node_kind: str, has_stem: bool, graph_score: float) -> Signal | None:
    if node_kind in ("identifier", "definition") and (has_stem or graph_score >= 0.5):
        w = W_SYMBOL if has_stem else min(W_SYMBOL, 0.55 + graph_score / 4)
        return Signal("symbol_context", w, node_kind)
    return None


def fuzzy_signal(surface: str, prof: EntityProfile, *, min_len: int,
                 min_ratio: float) -> Signal | None:
    cand = surface.lower()
    if len(cand) < min_len:
        return None
    segs = segments(surface)
    if segs and all(s in _STOPWORDS or s.isdigit() for s in segs):
        return None                       # "Systems", "provider" — never a fuzzy hit
    targets = [t.lower() for t in (*prof.names, *prof.aliases) if len(t) >= min_len]
    best = 0.0
    for t in targets:
        scores = [fuzz.ratio(cand, t), fuzz.token_set_ratio(cand, t)]
        if len(cand) >= 0.6 * len(t):     # only compare substrings of comparable length
            scores.append(fuzz.partial_ratio(cand, t))
        best = max(best, *scores)
    if best < min_ratio:
        return None
    span = max(1.0, 100.0 - min_ratio)
    frac = (best - min_ratio) / span
    weight = W_FUZZY_MIN + frac * (W_FUZZY_MAX - W_FUZZY_MIN)
    return Signal("fuzzy", round(weight, 4), f"~{int(best)}%")


def acronym_signal(surface: str, prof: EntityProfile, *, corroborated: bool
                   ) -> Signal | None:
    if not (2 <= len(surface) <= 5 and surface.isupper() and surface.isalpha()):
        return None
    initials = "".join(w[0] for w in words(" ".join(prof.names)) if w)
    hit = surface.lower() in {a.lower() for a in prof.aliases} \
        or (len(initials) >= 3 and surface.lower() == initials.lower())
    if not hit:
        return None
    w = W_ACRONYM_CORROBORATED if corroborated else W_ACRONYM_ALONE
    return Signal("acronym", w, "corroborated" if corroborated else "unconfirmed")


def semantic_signal(context: str, prof: EntityProfile) -> Signal | None:
    raw = similarity(context, prof.semantic_texts())
    weight = min(W_SEMANTIC_CAP, round(raw * 0.5, 4))
    if weight < 0.15:
        return None
    return Signal("semantic", weight, f"cos~{raw:.2f}")


def graph_signal(score: float, hops: int, via: str) -> Signal | None:
    if score < 0.2:
        return None
    return Signal("graph", min(W_GRAPH_CAP, round(score, 4)), f"{hops} hop(s) from {via}")


def weak_signal() -> Signal:
    return Signal("weak", W_WEAK, "bare token")


def is_stopword(surface: str) -> bool:
    segs = segments(surface)
    return bool(segs) and all(s in _STOPWORDS or s.isdigit() for s in segs)


# --------------------------------------------------------------------------- #
# comment-level: "also known as: …" alias enumeration                         #
# --------------------------------------------------------------------------- #

def alias_enumerations(comment_text: str) -> list[list[str]]:
    """Lists of short forms declared in a comment (``known internally as: …``)."""
    out: list[list[str]] = []
    for m in _ALIAS_ENUM_RE.finditer(comment_text):
        block = m.group(1)
        items = [i.strip(" .-\t") for i in _ALIAS_ITEM_RE.findall(block)]
        items = [i for i in items if i and not i.lower().startswith(("this ", "for "))]
        if len(items) >= 2:
            out.append(items)
    return out
