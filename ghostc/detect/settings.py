"""Detection thresholds + tunables, read from the optional ``detection:`` block
of ``privacy.yaml`` (schema: ``schemas/privacy-config.schema.json``).

Every field has a default, so a config with no ``detection:`` block behaves
exactly as before this layer existed.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


@dataclass(frozen=True)
class DetectionSettings:
    auto_threshold: float = 0.90        # score ≥ this + a hard signal  → auto-transform
    review_threshold: float = 0.45      # score in [review, auto)       → human review queue
    auto_alias: bool = False            # mint aliases for unconfigured auto candidates
    decode_pass: bool = True            # fold string concat / [].join / base64 and re-scan
    fuzzy_min_len: int = 6              # rapidfuzz only compares tokens at least this long
    fuzzy_min_ratio: float = 88.0       # ... and only keeps matches at least this similar
    graph_decay: float = 0.85          # taint multiplier per reference-graph hop
    graph_floor_hops: int = 3          # stop propagating past this many hops
    weights: dict[str, float] = field(default_factory=dict)  # per-signal weight overrides

    def weight(self, name: str, default: float) -> float:
        try:
            return _clamp01(self.weights[name])
        except (KeyError, TypeError, ValueError):
            return default


DEFAULTS = DetectionSettings()


def detection_settings(cfg: dict | None) -> DetectionSettings:
    block = (cfg or {}).get("detection") or {}
    weights = block.get("signal_weights") or {}
    return replace(
        DEFAULTS,
        auto_threshold=_clamp01(block.get("auto_threshold", DEFAULTS.auto_threshold)),
        review_threshold=_clamp01(block.get("review_threshold", DEFAULTS.review_threshold)),
        auto_alias=bool(block.get("auto_alias", DEFAULTS.auto_alias)),
        decode_pass=bool(block.get("decode_pass", DEFAULTS.decode_pass)),
        fuzzy_min_len=int(block.get("fuzzy_min_len", DEFAULTS.fuzzy_min_len)),
        fuzzy_min_ratio=float(block.get("fuzzy_min_ratio", DEFAULTS.fuzzy_min_ratio)),
        graph_decay=_clamp01(block.get("graph_decay", DEFAULTS.graph_decay)),
        graph_floor_hops=int(block.get("graph_floor_hops", DEFAULTS.graph_floor_hops)),
        weights={str(k): float(v) for k, v in weights.items()},
    )
