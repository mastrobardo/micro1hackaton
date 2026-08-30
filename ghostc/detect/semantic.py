"""Semantic similarity signal — optional embeddings, stdlib fallback.

If ``sentence-transformers`` is installed (the ``[semantic]`` extra) real
sentence embeddings are used; otherwise a character-trigram cosine over the
entity's name / note / alias gives a weak lexical-semantic proxy. Either way the
caller caps the contribution low and never lets it auto-transform — this is the
"semantic only → 0.43" tier.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache

_WORD = re.compile(r"[A-Za-z0-9]+")
_model_state: dict[str, object] = {}


def _load_model():
    if "tried" in _model_state:
        return _model_state.get("model")
    _model_state["tried"] = True
    try:  # pragma: no cover - exercised only when the extra is installed
        from sentence_transformers import SentenceTransformer

        _model_state["model"] = SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:  # noqa: BLE001 - any failure → fall back
        _model_state["model"] = None
    return _model_state.get("model")


@lru_cache(maxsize=4096)
def _trigrams(text: str) -> frozenset:
    norm = "".join(_WORD.findall(text.lower()))
    if len(norm) < 3:
        return frozenset({norm} if norm else set())
    return frozenset(norm[i:i + 3] for i in range(len(norm) - 2))


def _trigram_cosine(a: str, b: str) -> float:
    ta, tb = _trigrams(a), _trigrams(b)
    if not ta or not tb:
        return 0.0
    ca, cb = Counter(_trigrams(a)), Counter(_trigrams(b))
    common = set(ca) & set(cb)
    if not common:
        return 0.0
    dot = sum(ca[t] * cb[t] for t in common)
    na = math.sqrt(sum(v * v for v in ca.values()))
    nb = math.sqrt(sum(v * v for v in cb.values()))
    return dot / (na * nb) if na and nb else 0.0


def similarity(context: str, entity_texts: list[str]) -> float:
    """Max similarity of *context* to any of *entity_texts*, in [0, 1]."""
    texts = [t for t in entity_texts if t and t.strip()]
    if not context.strip() or not texts:
        return 0.0
    model = _load_model()
    if model is not None:  # pragma: no cover - needs the optional extra
        import numpy as np

        embs = model.encode([context, *texts], normalize_embeddings=True)
        return float(max(np.dot(embs[0], embs[i]) for i in range(1, len(embs))))
    return max(_trigram_cosine(context, t) for t in texts)


def using_embeddings() -> bool:
    return _load_model() is not None
