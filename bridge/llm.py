"""LLM backend for the agent workflow — real Claude, or a deterministic stub.

Claude is reached through the official ``anthropic`` SDK (not a LangChain wrapper);
LangGraph only orchestrates. When ``langsmith`` is importable and a LangSmith key
is present, the client is wrapped so every call is traced.

``backend`` resolution:

* ``"stub"``               — always the deterministic :class:`StubLLM`
* ``"claude"``             — real Claude; raises if the SDK / key are missing
* ``"auto"`` (default)     — Claude when an Anthropic key is set and the SDK
                             imports, else the stub

Set ``GHOSTC_AGENT_BACKEND`` / ``GHOSTC_AGENT_MODEL`` to override in the env.

**Per-agent credentials.** Every entry point takes ``role`` — ``"client"`` (the
company-side orchestrator: planning + the consistency gate) or ``"consultancy"``
(the external coding agent). A secret is read from the role-prefixed name first,
then the bare name::

    CLIENT_ANTHROPIC_API_KEY      -> ANTHROPIC_API_KEY
    CONSULTANCY_ANTHROPIC_API_KEY -> ANTHROPIC_API_KEY
    CLIENT_LANGSMITH_API_KEY      -> LANGSMITH_API_KEY
    CONSULTANCY_LANGSMITH_API_KEY -> LANGSMITH_API_KEY
    {ROLE}_LANGSMITH_PROJECT      -> LANGSMITH_PROJECT   -> ghostc-<role>
    {ROLE}_LANGSMITH_ENDPOINT     -> LANGSMITH_ENDPOINT  (e.g. EU tenant)

So one key still works everywhere; split them for separate billing / trace orgs /
blast-radius. Phase E's ``docker compose`` gives each service only its own subset.
``ClaudeLLM.complete`` / ``StubLLM.complete`` carry ``@traceable`` spans.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from bridge.trace import traceable

DEFAULT_MODEL = os.environ.get("GHOSTC_AGENT_MODEL", "claude-opus-5")
ROLES = ("client", "consultancy")


def _check_role(role: str) -> str:
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}, got {role!r}")
    return role


def resolve_secret(name: str, role: str) -> str | None:
    """Role-prefixed env var (``CLIENT_FOO`` / ``CONSULTANCY_FOO``) then bare ``FOO``."""
    _check_role(role)
    return os.environ.get(f"{role.upper()}_{name}") or os.environ.get(name) or None


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

    @traceable(run_type="llm", name="stub.complete")
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

    def __init__(self, model: str = DEFAULT_MODEL, *,
                 api_key: str | None = None, langsmith_api_key: str | None = None) -> None:
        import anthropic  # noqa: F401  (import error surfaces to the caller)

        self.model = model
        client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        try:
            if langsmith_api_key or os.environ.get("LANGSMITH_API_KEY"):
                from langsmith.wrappers import wrap_anthropic

                client = wrap_anthropic(client)
        except Exception:  # tracing is best-effort, never fatal
            pass
        self._client = client

    @traceable(run_type="llm", name="claude.complete")
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


def _claude_available(role: str = "client") -> bool:
    if not resolve_secret("ANTHROPIC_API_KEY", role):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def get_llm(backend: str = "auto", model: str | None = None, *, role: str = "client"):
    """Return an object with ``.complete(system=, user=, max_tokens=) -> LLMReply``.

    *role* selects which Anthropic / LangSmith key to use (see the module docstring).
    """
    _check_role(role)
    backend = os.environ.get("GHOSTC_AGENT_BACKEND", backend)
    if backend == "stub":
        return StubLLM()

    def _claude() -> ClaudeLLM:
        return ClaudeLLM(
            model or DEFAULT_MODEL,
            api_key=resolve_secret("ANTHROPIC_API_KEY", role),
            langsmith_api_key=resolve_secret("LANGSMITH_API_KEY", role),
        )

    if backend == "claude":
        return _claude()
    return _claude() if _claude_available(role) else StubLLM()


def configure_langsmith(role: str = "client") -> bool:
    """Enable LangSmith tracing for *role* if a key is present. Returns whether it's on.

    Project name resolves ``{ROLE}_LANGSMITH_PROJECT`` -> ``LANGSMITH_PROJECT`` ->
    ``ghostc-<role>``. Sets ``LANGSMITH_API_KEY`` / ``LANGSMITH_PROJECT`` in the env
    for the wrapped client to pick up — so within one process the most recent
    ``configure_langsmith`` call wins (fine across the Phase-E process split).
    """
    _check_role(role)
    key = resolve_secret("LANGSMITH_API_KEY", role)
    if not key:
        return False
    project = (os.environ.get(f"{role.upper()}_LANGSMITH_PROJECT")
               or os.environ.get("LANGSMITH_PROJECT")
               or f"ghostc-{role}")
    os.environ["LANGSMITH_API_KEY"] = key
    os.environ["LANGSMITH_PROJECT"] = project
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    endpoint = resolve_secret("LANGSMITH_ENDPOINT", role)  # e.g. EU: https://eu.api.smith.langchain.com
    if endpoint:
        os.environ["LANGSMITH_ENDPOINT"] = endpoint
    return True
