"""Candidate scoring / detection layer for ``ghostc discover`` and the
threshold-driven compiler.

Turns a repo into a ranked list of :class:`~ghostc.detect.candidate.Candidate`
objects: a surface span, the evidence :class:`~ghostc.detect.candidate.Signal`
list behind it, a combined confidence ``score`` in ``[0, 1]``, and a threshold-
derived ``action`` (``auto`` / ``review`` / ``ignore``).

Public surface:

* :func:`ghostc.detect.scan.scan_repo` — the whole pass over a repo.
* :class:`ghostc.detect.candidate.Candidate` / ``Signal`` — the result shape.
* :func:`ghostc.detect.settings.detection_settings` — thresholds + weights.
"""
from __future__ import annotations

from ghostc.detect.candidate import Candidate, Signal, combine_score
from ghostc.detect.settings import DetectionSettings, detection_settings

__all__ = [
    "Candidate",
    "Signal",
    "combine_score",
    "DetectionSettings",
    "detection_settings",
]
