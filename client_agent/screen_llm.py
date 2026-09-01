"""The client-side LLM adjudicator for :mod:`ghostc.screen`.

The deterministic detector is **precision-oriented by construction**: it only
proposes an unconfigured entity from an *anchor* (a scoped package, an internal
host, a declared alias list, a decoded literal, reference-graph taint) and drops
any token that has none. That is exactly what keeps ``helmet`` and
``swagger-jsdoc`` out of the proposals — and exactly why it cannot see
``Northwind Airlines`` sitting in a sentence of a ticket with nothing structural
around it.

This module is the recall half. It shows Claude the **real** task and the
**ghost** task side by side and asks which spellings in the ghost half still
refer to something real. Three properties keep it honest:

* it lives in ``client_agent/``, never in ``ghostc/`` — the deterministic
  compiler keeps its stdlib-only dependency contract (``tests/test_boundary.py``);
* it may only **accuse**. Every surface it names is anchored back into the ghost
  text by :func:`ghostc.screen.screen_text` before it can score, and its signal
  is capped at ``W_LLM_CAP`` (0.6) — below ``auto_threshold``, so an accusation
  can send something to human review but can never decide anything on its own;
* it never rewrites. Redaction stays with the deterministic compiler.

**Boundary note.** This is a ``role="client"`` LLM: its prompt carries the real,
boundary-internal task text. That is the same crossing the PR-consistency gate in
``client_agent/graph.py`` already makes, and it is recorded in ``THREAT_MODEL.md``
— the client-role model sees inside the boundary, only the consultancy-role model
is external.
"""
from __future__ import annotations

import json
import re

from bridge.llm import get_llm
from ghostc.screen import ScreenError

MODES = ("best-effort", "required", "off")

_SYS = (
    "You are a privacy screener inside a company's trust boundary. A deterministic "
    "compiler has rewritten an internal task into a sanitized 'ghost' task that is "
    "about to be sent to an external contractor. The compiler only knows the entities "
    "in its config, so anything it never heard of passed through untouched.\n"
    "You are given the REAL task and the GHOST task. Name every spelling that is still "
    "present in the GHOST task and that identifies something real: a client, vendor, "
    "person, internal service, hostname, account or credential.\n"
    "Rules: only report strings that appear VERBATIM in the GHOST task. Do NOT report "
    "the ghost aliases the compiler produced (names like 'client-a', 'vendor-e', "
    "'service-b', 'Person A'). Do NOT report ordinary technical vocabulary, open-source "
    "package names, or generic English words.\n"
    'Reply with ONLY a compact JSON array: [{"surface": "<verbatim string>", '
    '"kind": "client|vendor|person|internal_service|domain|infra_identifier|secret", '
    '"confidence": 0.0-1.0, "why": "<short reason>"}]. Empty array if the ghost task '
    "is clean."
)


class LLMAdjudicator:
    """Callable matching :data:`ghostc.screen.Adjudicator`. Tracks its own cost."""

    def __init__(self, llm, *, max_chars: int = 6000, max_tokens: int = 1024) -> None:
        self._llm = llm
        self.model = getattr(llm, "model", "unknown")
        self.max_chars = max_chars
        self.max_tokens = max_tokens
        self.calls = 0
        self.tokens = 0
        self.error: str | None = None

    def __call__(self, ghost_text: str, real_text: str | None = None) -> list[dict]:
        user = (f"REAL TASK (internal, for comparison only):\n{(real_text or '')[:self.max_chars]}"
                f"\n\n---\n\nGHOST TASK (about to leave the boundary):\n"
                f"{ghost_text[:self.max_chars]}\n\n"
                "Which spellings in the GHOST TASK still identify something real?")
        reply = self._llm.complete(system=_SYS, user=user, max_tokens=self.max_tokens)
        self.calls += 1
        self.tokens += reply.total_tokens
        return parse_claims(reply.text)

    def info(self) -> dict:
        return {"status": "error" if self.error else "ran", "model": self.model,
                "calls": self.calls, "tokens": self.tokens}


def parse_claims(text: str) -> list[dict]:
    """Pull the JSON array out of a model reply. Never raises — a reply we cannot
    read yields no accusations, and the deterministic layer still gates."""
    m = re.search(r"\[.*\]", text or "", re.DOTALL)
    if not m:
        return []
    try:
        doc = json.loads(m.group(0))
    except ValueError:
        return []
    if not isinstance(doc, list):
        return []
    return [c for c in doc if isinstance(c, dict) and c.get("surface")]


def build_adjudicator(backend: str = "auto", *, mode: str = "best-effort"):
    """``(adjudicator | None, info)`` for the requested *mode*.

    * ``off`` — no LLM layer.
    * ``best-effort`` (default) — use Claude when a client key + SDK are present;
      fall back to the deterministic layer alone otherwise, recording
      ``status: "skipped"``. Without this, offline CI and every ``--backend stub``
      run would fail closed on an LLM that was never going to be there.
    * ``required`` — a real model or nothing: raises if only the stub resolves.
      This is the production setting.
    """
    if mode not in MODES:
        raise ScreenError(f"screen-llm mode must be one of {MODES}, got {mode!r}")
    if mode == "off":
        return None, {"status": "off"}

    llm = get_llm(backend, role="client")
    if getattr(llm, "model", "") == "stub":
        if mode == "required":
            raise ScreenError(
                "screen-llm=required but no client LLM is available "
                "(set CLIENT_ANTHROPIC_API_KEY / ANTHROPIC_API_KEY, or install the "
                "[agents] extra); refusing to screen with the stub")
        return None, {"status": "skipped", "detail": "no client LLM available"}
    return LLMAdjudicator(llm), {"status": "ran", "model": llm.model}
