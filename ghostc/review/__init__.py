"""Human review board — the reviewer's decisions on `discover` candidates and
`restricted` clearances, as an append-only log the compiler consumes.

`store.py`  — `DecisionStore` over `decisions.jsonl` (durable, boundary-internal).
`model.py`  — streamlit-free glue: load candidates, apply a decision, config delta.
`app.py`    — the `ghostc-review` Streamlit UI (optional `[review]` extra).

The pipeline consumes the **file**, never the UI: `ghostc compile --decisions
<path>` reproduces the reviewed ghost with no Streamlit in the loop.
"""
