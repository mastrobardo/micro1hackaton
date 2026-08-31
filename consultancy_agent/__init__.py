"""Consultancy-side agent — runs OUTSIDE the company trust boundary.

MUST NOT import ``ghostc`` or ``client_agent``. It sees only a ghost repo
checkout + ``TASK.md`` and opens a ghost PR. Enforced by tests/test_boundary.py.
"""
