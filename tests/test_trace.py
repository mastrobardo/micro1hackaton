"""bridge.trace.traceable — works decorated bare, as a factory, and passes through."""
from __future__ import annotations

from bridge.trace import traceable


def test_bare_decorator_preserves_behaviour():
    @traceable
    def add(a, b):
        return a + b

    assert add(2, 3) == 5


def test_factory_decorator_preserves_behaviour():
    @traceable(run_type="chain", name="node:demo")
    def mul(a, b):
        return a * b

    assert mul(4, 5) == 20


def test_wraps_a_prebuilt_function():
    def sub(a, b):
        return a - b

    wrapped = traceable(run_type="chain", name="node:sub")(sub)
    assert wrapped(10, 4) == 6
