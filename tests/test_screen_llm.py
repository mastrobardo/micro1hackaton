"""`client_agent.screen_llm` — the LLM adjudicator seam.

The model may accuse, never decide. These tests pin the parsing, the cost
accounting and the availability policy; the anchoring rule that keeps an
accusation honest is pinned in `test_screen.py`.
"""
from __future__ import annotations

import pytest

from bridge.llm import LLMReply
from ghostc.screen import ScreenError, screen_text
from client_agent.screen_llm import LLMAdjudicator, build_adjudicator, parse_claims

_CFG = {"mapping_version": 1,
        "entities": [{"id": "client_northwind", "kind": "client", "level": "restricted",
                      "strategy": "alias", "real": "Northwind Airlines",
                      "ghost": "Client A"}]}


class FakeLLM:
    """Records the prompt it was given and replies with canned text."""

    model = "fake-claude"

    def __init__(self, text: str) -> None:
        self.text = text
        self.system = ""
        self.user = ""

    def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> LLMReply:
        self.system, self.user = system, user
        return LLMReply(text=self.text, model=self.model, input_tokens=10,
                        output_tokens=5)


def test_parse_claims_tolerates_prose_around_the_json():
    claims = parse_claims('Sure — here you go:\n[{"surface": "Halcyon", '
                          '"kind": "client", "confidence": 0.8}]\nHope that helps.')
    assert claims == [{"surface": "Halcyon", "kind": "client", "confidence": 0.8}]


@pytest.mark.parametrize("reply", ["ACK", "", "{}", "[]", "[1, 2]", "[{}]", "not json ["])
def test_unreadable_reply_yields_no_accusations(reply):
    """A reply we cannot read must not crash the gate and must not invent findings —
    the deterministic layer is still there to do the gating."""
    assert parse_claims(reply) == []


def test_prompt_carries_both_halves_and_asks_only_about_the_ghost():
    llm = FakeLLM("[]")
    adj = LLMAdjudicator(llm)
    adj("GHOST: build it for Client A", "REAL: build it for Northwind Airlines")
    assert "Northwind Airlines" in llm.user and "Client A" in llm.user
    assert "GHOST TASK" in llm.user and "REAL TASK" in llm.user
    assert "verbatim" in llm.system.lower() or "VERBATIM" in llm.system


def test_adjudicator_tracks_its_own_cost():
    adj = LLMAdjudicator(FakeLLM("[]"))
    adj("ghost", "real")
    adj("ghost", "real")
    assert adj.info() == {"status": "ran", "model": "fake-claude", "calls": 2,
                          "tokens": 30}


def test_end_to_end_through_screen_text():
    llm = FakeLLM('[{"surface": "Halcyon Freight", "kind": "client", '
                  '"confidence": 0.9, "why": "unsubstituted client name"}]')
    res = screen_text("Add a Halcyon Freight tariff for Client A.",
                      real_text="Add a Halcyon Freight tariff for Northwind Airlines.",
                      cfg=_CFG, mapping_path=None, candidates_path=None,
                      adjudicator=LLMAdjudicator(llm))
    assert res.blocked and [c.surface for c in res.flagged] == ["Halcyon Freight"]
    assert res.flagged[0].evidence  # an "llm" signal, capped below auto_threshold


# -- availability policy ----------------------------------------------------- #

def test_off_mode_builds_no_adjudicator():
    adj, info = build_adjudicator("stub", mode="off")
    assert adj is None and info == {"status": "off"}


def test_best_effort_falls_back_to_deterministic_only_on_the_stub():
    """Offline CI and every `--backend stub` run must stay green: without a real
    client LLM the pass degrades to the deterministic layer and says so."""
    adj, info = build_adjudicator("stub", mode="best-effort")
    assert adj is None and info["status"] == "skipped"


def test_required_mode_refuses_the_stub():
    with pytest.raises(ScreenError, match="required"):
        build_adjudicator("stub", mode="required")


def test_unknown_mode_rejected():
    with pytest.raises(ScreenError):
        build_adjudicator("stub", mode="sometimes")


def test_real_backend_builds_an_adjudicator(monkeypatch):
    import client_agent.screen_llm as mod

    monkeypatch.setattr(mod, "get_llm", lambda backend, role: FakeLLM("[]"))
    adj, info = build_adjudicator("claude", mode="required")
    assert isinstance(adj, LLMAdjudicator) and info == {"status": "ran",
                                                        "model": "fake-claude"}
