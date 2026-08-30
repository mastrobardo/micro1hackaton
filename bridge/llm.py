"""LLM backend for the agent workflow — real Claude, or a deterministic stub.

Claude is reached through the official ``anthropic`` SDK (not a LangChain wrapper);
LangGraph only orchestrates. When ``langsmith`` is importable and
``LANGSMITH_API_KEY`` is set, the client is wrapped so every call is traced.

``backend`` resolution:

* ``"stub"``               — always the deterministic :class:`StubLLM`
* ``"claude"``             — real Claude; raises if the SDK / key are missing
* ``"auto"`` (default)     — Claude when ``ANTHROPIC_API_KEY`` is set and the SDK
                             imports, else the stub

Set ``GHOSTC_AGENT_BACKEND`` / ``GHOSTC_AGENT_MODEL`` to override in the env.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_MODEL = os.environ.get("GHOSTC_AGENT_MODEL", "claude-opus-5")


@dataclass
class LLMReply:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class StubLLM:
    """Deterministic, offline. Returns a canned verdict/plan keyed by intent."""

    model = "stub"

    def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> LLMReply:
        low = user.lower()
        if "consistent with the task" in low or "consistency" in low:
            text = '{"verdict": "consistent", "flags": []}'
        elif "rephrase" in low or "reword" in low:
            # echo the payload unchanged — the deterministic substitution already ran
            marker = "TASK:\n"
            text = user.split(marker, 1)[1].strip() if marker in user else user.strip()
        else:
            text = "ACK"
        return LLMReply(text=text, model=self.model,
                        input_tokens=len(user) // 4, output_tokens=len(text) // 4)


class ClaudeLLM:
    """Thin wrapper over ``anthropic``. Adaptive thinking, non-streaming, high effort."""

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        import anthropic  # noqa: F401  (import error surfaces to the caller)

        self.model = model
        client = anthropic.Anthropic()
        try:
            if os.environ.get("LANGSMITH_API_KEY"):
                from langsmith.wrappers import wrap_anthropic

                client = wrap_anthropic(client)
        except Exception:  # tracing is best-effort, never fatal
            pass
        self._client = client

    def complete(self, *, system: str, user: str, max_tokens: int = 4096) -> LLMReply:
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        u = getattr(msg, "usage", None)
        return LLMReply(text=text, model=self.model,
                        input_tokens=getattr(u, "input_tokens", 0) or 0,
                        output_tokens=getattr(u, "output_tokens", 0) or 0)


def _claude_available() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def get_llm(backend: str = "auto", model: str | None = None):
    """Return an object with ``.complete(system=, user=, max_tokens=) -> LLMReply``."""
    backend = os.environ.get("GHOSTC_AGENT_BACKEND", backend)
    if backend == "stub":
        return StubLLM()
    if backend == "claude":
        return ClaudeLLM(model or DEFAULT_MODEL)
    return ClaudeLLM(model or DEFAULT_MODEL) if _claude_available() else StubLLM()


def configure_langsmith(project: str = "ghostc-agents") -> bool:
    """Enable LangSmith tracing if a key is present. Returns whether it's on."""
    if not os.environ.get("LANGSMITH_API_KEY"):
        return False
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_PROJECT", project)
    return True
