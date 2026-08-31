"""`ghostc.review.app` — argument parsing + jsonl helper. The Streamlit UI itself
needs a runtime; the logic it calls is covered by test_review_model / _store."""
from __future__ import annotations

import importlib.util
import json

import pytest

from ghostc.review import app


def test_defaults_and_overrides():
    a = app._args([])
    assert a.decisions == "review/decisions.jsonl"
    assert a.candidates == "workspace/private/candidates.jsonl"
    a = app._args(["--decisions", "x.jsonl", "--eval-csv", "e.csv"])
    assert a.decisions == "x.jsonl" and a.eval_csv == "e.csv"


def test_jsonl_reads_and_tolerates_missing(tmp_path):
    assert app._jsonl(str(tmp_path / "nope.jsonl")) == []
    p = tmp_path / "m.jsonl"
    p.write_text('{"a": 1}\n\n{"a": 2}\n', encoding="utf-8")
    assert app._jsonl(str(p)) == [{"a": 1}, {"a": 2}]


@pytest.mark.skipif(importlib.util.find_spec("streamlit") is not None,
                    reason="streamlit installed — main() would launch it")
def test_main_without_streamlit_is_a_helpful_error():
    with pytest.raises(SystemExit, match=r"\[review\] extra"):
        app.main()
