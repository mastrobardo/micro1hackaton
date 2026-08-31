"""``ghostc-review`` — the human review board (Streamlit).

    ghostc-review [-- --candidates PATH --decisions PATH ...]
    # or, equivalently:
    streamlit run ghostc/review/app.py -- --candidates PATH --decisions PATH

Two tabs:

* **Review** — the `candidates.jsonl` queue. Per proposal: accept (→ entity id +
  level + approver), ignore, or escalate to `restricted`. Every action appends to
  `decisions.jsonl`; the implied `privacy.yaml` delta is shown live.
* **Process data** — read-only dashboard over `metrics/agent-runs.jsonl`,
  `eval-report.csv`, audit-event counts, and the scorer-vs-human agreement stat.
  "The process generates the data that improves the process."

The pipeline consumes `decisions.jsonl`, never this app:
``ghostc compile --decisions decisions.jsonl`` reproduces the reviewed ghost.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULTS = {
    "candidates": "workspace/private/candidates.jsonl",
    "decisions": "review/decisions.jsonl",
    "config": "privacy.yaml",
    "metrics": "metrics/agent-runs.jsonl",
    "eval_csv": "workspace/eval-report.csv",
    "audit": "workspace/private/audit.jsonl",
}


def _args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="ghostc-review")
    for k, v in DEFAULTS.items():
        ap.add_argument(f"--{k.replace('_', '-')}", default=v)
    return ap.parse_args(argv)


def _jsonl(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


# --------------------------------------------------------------------- the app
def _run_app(argv: list[str]) -> None:
    import streamlit as st
    import yaml

    from ghostc.audit import AuditLog
    from ghostc.review.model import (config_delta, delta_yaml, load_candidates,
                                     review_rows)
    from ghostc.review.store import DecisionStore

    a = _args(argv)
    st.set_page_config(page_title="ghostc review board", layout="wide")
    st.title("ghostc — human review board")
    st.caption(f"candidates `{a.candidates}` · decisions `{a.decisions}` · "
               f"config `{a.config}`")

    store = DecisionStore(a.decisions)
    cands = load_candidates(a.candidates)
    try:
        cfg = yaml.safe_load(Path(a.config).read_text(encoding="utf-8")) or {}
    except OSError:
        cfg = {"entities": []}

    tab_review, tab_data = st.tabs(["Review", "Process data"])

    # ---- Review ------------------------------------------------------------
    with tab_review:
        rows = review_rows(cands, store)
        if not rows:
            st.info(f"No open proposals in `{a.candidates}`. "
                    "Run `ghostc discover` first.")
        st.dataframe(
            [{k: r[k] for k in ("surface", "kind", "level", "score", "evidence",
                                "occurrences", "proposed_action", "decision",
                                "approved_by")} for r in rows],
            use_container_width=True, hide_index=True)

        st.subheader("Decide")
        labels = {f"{r['surface']}  ·  {r['proposed_action']}  ·  score {r['score']}": r
                  for r in rows}
        if labels:
            pick = st.selectbox("proposal", list(labels))
            r = labels[pick]
            cand = next(c for c in cands
                        if (c.get("entity_id") or c["surface"]) in (r["key"], r["surface"])
                        and c["surface"] == r["surface"])
            c1, c2, c3 = st.columns(3)
            action = c1.radio("action", ("accept", "ignore", "escalate"),
                              help="accept → compiled as its own alias · ignore → left "
                                   "as-is · escalate → marked restricted (needs approver)")
            level = c2.selectbox("level", ("confidential", "internal", "restricted"),
                                 index=("confidential", "internal", "restricted")
                                 .index(r["level"] if r["level"] in
                                        ("confidential", "internal", "restricted")
                                        else "confidential"))
            entity_id = c2.text_input("entity id (accept/escalate)",
                                      value=r["key"].replace("sha256:", "rev_")[:24])
            approver = c3.text_input("approved_by", value=r["approved_by"] or "")
            ghost = c3.text_input("ghost alias (optional)")
            note = st.text_input("note", value=r["note"])
            if st.button("record decision", type="primary"):
                audit = AuditLog(a.audit)
                store.record(
                    surface=cand["surface"], reviewer_action=action,
                    key=r["key"],
                    entity_id=entity_id if action in ("accept", "escalate") else None,
                    proposed_action=cand.get("action", "review"),
                    proposed_level=cand.get("level"),
                    level=level, ghost=ghost or None,
                    approved_by=approver or None, note=note,
                    occurrences=len(cand.get("occurrences", [])), audit=audit)
                st.success(f"recorded: {action} — {cand['surface']}")
                st.rerun()

        st.subheader("Implied `privacy.yaml` change (what `compile --decisions` applies)")
        st.code(delta_yaml(config_delta(store, cfg, cands)), language="yaml")

    # ---- Process data (the dashboard) -----------------------------------
    with tab_data:
        sm = store.summarize()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("decisions", sm["n_decisions"])
        c2.metric("scorer-vs-human agreement",
                  f"{sm['agreement_rate']:.0%}" if sm["agreement_rate"] is not None else "—")
        c3.metric("escalations", sm["escalations"])
        c4.metric("overrides", sm["overrides"])
        if sm["by_proposed_action"]:
            st.write("agreement by the scorer's proposed action")
            st.dataframe(
                [{"proposed_action": k, "n": v["n"], "agree": v["agree"],
                  "rate": f"{v['agree'] / v['n']:.0%}" if v["n"] else "—"}
                 for k, v in sorted(sm["by_proposed_action"].items())],
                use_container_width=True, hide_index=True)

        st.subheader("Agent runs · `metrics/agent-runs.jsonl`")
        mrows = _jsonl(a.metrics)
        st.dataframe(mrows, use_container_width=True, hide_index=True) if mrows else \
            st.info("no agent-run metrics yet")

        st.subheader("Eval report · `eval-report.csv`")
        ep = Path(a.eval_csv)
        if ep.exists():
            import csv
            with ep.open(newline="", encoding="utf-8") as fh:
                st.dataframe(list(csv.DictReader(fh)), use_container_width=True,
                             hide_index=True)
        else:
            st.info("run `ghostc eval` to generate it")

        st.subheader("Audit events · counts")
        ev: dict[str, int] = {}
        for e in _jsonl(a.audit):
            ev[e.get("event", "?")] = ev.get(e.get("event", "?"), 0) + 1
        st.dataframe([{"event": k, "count": v} for k, v in sorted(ev.items())],
                     use_container_width=True, hide_index=True) if ev else \
            st.info("no audit log yet")


# ----------------------------------------------------------- console entry
def main() -> None:
    """`ghostc-review` — (re)launch this file under `streamlit run`."""
    try:
        from streamlit.web import cli as stcli
    except ModuleNotFoundError:
        raise SystemExit("the review board needs the [review] extra:\n"
                         "  pip install -e '.[review]'")
    sys.argv = ["streamlit", "run", __file__, "--", *sys.argv[1:]]
    raise SystemExit(stcli.main())


if __name__ == "__main__":
    _run_app(sys.argv[1:])
