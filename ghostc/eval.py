"""ghostc eval — measure the privacy win: keyword redaction vs `compile`.

MVP metric (no external agent). Build both comparators from the real repo, then
count residual real-entity occurrences in each tree two ways:

* **residual (casing-aware)** — run the compiler's own matchers over the tree
  without writing (`compile_repo(tree, dry_run=True)` in detector mode). This is
  the honest measure: "does a configured entity still appear, in *any* spelling
  derived from its real name?". `compile` should leave 0; the baseline leaves
  every casing variant a keyword replace can't see.
* **strict token scan** — `anchored_scan` over the configured spellings only, the
  same check `verify` and `tests/expected/groundtruth.json` use. Reported for
  continuity; on a fixture where every configured spelling is an exact keyword it
  cannot tell the two approaches apart — which is itself the point.

Downstream metrics (task pass rate, human approvals, wall-clock, token cost) need
the external-agent harness and are emitted as ``n/a`` here.

Outputs ``<report>.md`` + ``<report>.csv``; audit events under component ``eval``.
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ghostc.audit import AuditLog, new_operation_id
from ghostc.config import load_config
from ghostc.scanning import anchored_scan, iter_text_files

_GROUNDTRUTH = Path(__file__).resolve().parents[1] / "tests" / "expected" / "groundtruth.json"


@dataclass
class Approach:
    label: str
    tree: Path
    residual_total: int = 0
    residual_by_entity: dict[str, int] = field(default_factory=dict)
    strict_total: int = 0
    strict_by_entity: dict[str, int] = field(default_factory=dict)


@dataclass
class Case:
    """One evaluation case: a configured sensitive entity, scored identically on both trees.

    The entity is the case unit because it is what the two approaches actually disagree
    about — a keyword `sed` neutralises the spellings it was handed and leaks the rest,
    so the per-entity residual is where the win is or isn't.
    """
    entity_id: str
    kind: str
    level: str
    ghost: str
    real_occurrences: int
    baseline_residual: int
    compile_residual: int

    @property
    def exercised(self) -> bool:
        """False for a configured entity the fixture never actually uses — such a case
        cannot distinguish the approaches, so it is reported but not scored."""
        return self.real_occurrences > 0

    @property
    def passed(self) -> bool:
        return self.exercised and self.compile_residual == 0

    @property
    def result(self) -> str:
        if not self.exercised:
            return "n/a — not present in fixture"
        return "pass" if self.compile_residual == 0 else "FAIL"

    @property
    def hard(self) -> bool:
        """Most spellings to get right — the challenging case."""
        return self.baseline_residual > 0 and self.real_occurrences >= 20


@dataclass
class EvalResult:
    real: Path
    approaches: list[Approach]
    report_md: Path
    report_csv: Path
    groundtruth_total: int
    real_residual_total: int
    real_strict_total: int
    cases: list[Case] = field(default_factory=list)
    cases_csv: Path | None = None

    def by_label(self, label: str) -> Approach:
        return next(a for a in self.approaches if a.label == label)

    def summary(self) -> str:
        base = self.by_label("baseline")
        comp = self.by_label("compile")
        lines = [
            f"eval: {self.real}  (groundtruth {self.groundtruth_total} occurrences, "
            f"detector sees {self.real_residual_total} in the real repo)",
            "",
            f"{'metric':<44}{'baseline':>12}{'compile':>12}",
            f"{'-' * 68}",
            f"{'residual entity occurrences (casing-aware)':<44}"
            f"{base.residual_total:>12}{comp.residual_total:>12}",
            f"{'strict token leaks (verify / groundtruth method)':<44}"
            f"{base.strict_total:>12}{comp.strict_total:>12}",
            "",
        ]
        if base.residual_by_entity:
            lines.append("baseline residual by entity:")
            for eid, n in sorted(base.residual_by_entity.items()):
                lines.append(f"  {eid:<28} x{n}")
            lines.append("")
        if self.cases:
            scored = [c for c in self.cases if c.exercised]
            n_pass = sum(1 for c in scored if c.passed)
            n_base = sum(1 for c in scored if c.baseline_residual == 0)
            hard = next((c.entity_id for c in self.cases if c.hard), None)
            lines.append(f"cases: {len(scored)} scored  "
                         f"clean under compile {n_pass}/{len(scored)}  "
                         f"clean under baseline {n_base}/{len(scored)}"
                         + (f"  (hard: {hard})" if hard else ""))
            lines.append("")
        lines.append(f"report: {self.report_md}  +  {self.report_csv}")
        if self.cases_csv is not None:
            lines.append(f"cases:  {self.cases_csv}")
        verdict = "PASS" if comp.residual_total == 0 and base.residual_total > comp.residual_total \
            else "CHECK"
        lines.append(f"{verdict}: compile residual={comp.residual_total}, "
                     f"baseline residual={base.residual_total}")
        return "\n".join(lines)


def _spellings(entity: dict) -> list[str]:
    out = [entity["real"]]
    for m in entity.get("match", []):
        if m.get("kind") in ("literal", "identifier"):
            out.append(m["value"])
    return [s for s in dict.fromkeys(out) if s]


def _residual_scan(tree: Path, config_path: str) -> tuple[int, dict[str, int]]:
    """Casing-aware: the compiler's matchers over *tree*, writing nothing."""
    from ghostc.compile import compile_repo

    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        res = compile_repo(str(tree), config_path=str(config_path),
                           out=str(t / "ghost"), spec_path=str(t / "s.md"),
                           mapping_path=str(t / "m.json"), audit_path=str(t / "a.jsonl"),
                           detect=False, dry_run=True)
    by = {eid: len(r.occurrences) for eid, r in res.entities.items()}
    return res.hits, by


def _strict_scan(tree: Path, entities: list[dict]) -> tuple[int, dict[str, int]]:
    owner: dict[str, str] = {}
    for e in entities:
        for s in _spellings(e):
            owner.setdefault(s, e["id"])
    counts: dict[str, int] = {}
    total = 0
    for _rel, text in iter_text_files(tree):
        for hit in anchored_scan(text, owner):
            eid = owner[hit.text]
            counts[eid] = counts.get(eid, 0) + 1
            total += 1
    return total, counts


def _groundtruth_total() -> int:
    if not _GROUNDTRUTH.exists():
        return 0
    doc = json.loads(_GROUNDTRUTH.read_text(encoding="utf-8"))
    return sum(doc.get("occurrences", {}).values())


def run_eval(real: str, config_path: str = "privacy.yaml",
             baseline_out: str = "workspace/baseline-ghost",
             compile_out: str = "workspace/ghost",
             report: str = "workspace/eval-report",
             audit_path: str = "workspace/private/audit.jsonl") -> EvalResult:
    real_p = Path(real)
    if not real_p.is_dir():
        raise SystemExit(f"real repo not found: {real}")

    cfg = load_config(config_path)
    seeds = [e for e in cfg.get("entities", []) if e.get("source", "seed") == "seed"]

    op = new_operation_id()
    audit = AuditLog(audit_path, op)
    audit.emit("run.start", "eval", details={"real": str(real_p), "config": config_path})

    from ghostc.baseline import baseline_repo
    from ghostc.compile import compile_repo

    baseline_p = Path(baseline_out)
    compile_p = Path(compile_out)
    baseline_repo(str(real_p), config_path=str(config_path), out=str(baseline_p),
                  spec_path=str(baseline_p.parent / "baseline-spec.md"),
                  audit_path=audit_path)
    compile_repo(str(real_p), config_path=str(config_path), out=str(compile_p),
                 spec_path=str(compile_p.parent / "ghost-spec.md"),
                 mapping_path=str(compile_p.parent / "private" / "mapping.json"),
                 audit_path=audit_path, detect=False)

    real_residual_total, real_residual_by_entity = _residual_scan(real_p, config_path)
    real_strict_total, _ = _strict_scan(real_p, seeds)
    groundtruth_total = _groundtruth_total()

    approaches: list[Approach] = []
    for label, tree in (("baseline", baseline_p), ("compile", compile_p)):
        r_total, r_by = _residual_scan(tree, config_path)
        s_total, s_by = _strict_scan(tree, seeds)
        approaches.append(Approach(label, tree, r_total, r_by, s_total, s_by))
        audit.emit("eval.metric", "eval", subject={"approach": label},
                   details={"residual_occurrences": r_total,
                            "strict_token_leaks": s_total,
                            "residual_by_entity": dict(sorted(r_by.items()))})

    report_md = Path(f"{report}.md")
    report_csv = Path(f"{report}.csv")
    cases = _build_cases(seeds, real_residual_by_entity,
                         approaches[0].residual_by_entity, approaches[1].residual_by_entity)
    result = EvalResult(real_p, approaches, report_md, report_csv,
                        groundtruth_total, real_residual_total, real_strict_total,
                        cases=cases, cases_csv=Path(f"{report}-cases.csv"))
    _write_reports(result)

    for c in cases:
        audit.emit("eval.case", "eval", subject={"entity": c.entity_id},
                   decision="pass" if c.passed else "fail",
                   details={"real_occurrences": c.real_occurrences,
                            "baseline_residual": c.baseline_residual,
                            "compile_residual": c.compile_residual,
                            "hard": c.hard})

    base = result.by_label("baseline")
    comp = result.by_label("compile")
    audit.emit("eval.summary", "eval",
               decision="pass" if comp.residual_total == 0
               and base.residual_total > comp.residual_total else "check",
               details={"baseline_residual": base.residual_total,
                        "compile_residual": comp.residual_total,
                        "baseline_strict": base.strict_total,
                        "compile_strict": comp.strict_total})
    return result


def _build_cases(seeds: list[dict], real_by: dict[str, int],
                 base_by: dict[str, int], comp_by: dict[str, int]) -> list[Case]:
    """One case per configured entity, ordered most-exposed first."""
    cases = [
        Case(entity_id=e["id"],
             kind=e.get("kind", "—"),
             level=e.get("level", "—"),
             ghost=e.get("ghost") or "<removed>",
             real_occurrences=real_by.get(e["id"], 0),
             baseline_residual=base_by.get(e["id"], 0),
             compile_residual=comp_by.get(e["id"], 0))
        for e in seeds
    ]
    return sorted(cases, key=lambda c: (-c.real_occurrences, c.entity_id))


def _pct(base: int, comp: int) -> str:
    if base <= 0:
        return "—"
    return f"-{base - comp} ({round(100 * (base - comp) / base)}%)"


def _write_reports(res: EvalResult) -> None:
    base = res.by_label("baseline")
    comp = res.by_label("compile")

    rows = [
        ("Residual entity occurrences (casing-aware) — target 0",
         str(base.residual_total), str(comp.residual_total),
         _pct(base.residual_total, comp.residual_total)),
        ("Strict token leaks (verify / groundtruth method) — target 0",
         str(base.strict_total), str(comp.strict_total),
         _pct(base.strict_total, comp.strict_total)),
        ("Reversible (ghost PR -> real PR)", "no", "yes (mapping store)", "—"),
        ("Task pass rate", "n/a — needs external-agent harness", "n/a", "—"),
        ("Human approvals per task", "n/a", "n/a", "—"),
        ("Wall-clock per task", "n/a", "n/a", "—"),
        ("Token cost per task", "n/a", "n/a", "—"),
    ]

    md = [
        "# Eval report — baseline keyword redaction vs `ghostc compile`",
        "",
        f"Real repo: `{res.real}` · groundtruth: **{res.groundtruth_total}** configured-spelling "
        f"occurrences (strict scan of the real repo: {res.real_strict_total}) · casing-aware "
        f"detector sees **{res.real_residual_total}** in the real repo.",
        "",
        "MVP metric — no external coding agent. The primary row is the **residual entity "
        "occurrences (casing-aware)** count: how many real-entity occurrences survive into what "
        "would be handed to an external agent, in any spelling derived from the real name. "
        "`compile` should leave 0; the keyword baseline leaks every spelling it was not "
        "literally configured with (`SKYROUTE_API_KEY`, `bookingCore`, `BOOKING_CORE_URL`, …).",
        "",
        "The **strict token leaks** row is the exact-spelling scan `verify` and "
        "`groundtruth.json` use. On this fixture every configured spelling is an exact keyword, "
        "so a keyword `sed` neutralises all of them and this row reads 0 for both approaches — "
        "it cannot see the difference. That blind spot is the reason the casing-aware detector "
        "exists and is the primary metric.",
        "",
        "| Metric | Baseline (`sed` redaction) | Solution (`compile`) | Improvement |",
        "|---|---|---|---|",
    ]
    md += [f"| {m} | {b} | {c} | {d} |" for m, b, c, d in rows]
    if res.cases:
        scored = [c for c in res.cases if c.exercised]
        n_pass = sum(1 for c in scored if c.passed)
        n_base = sum(1 for c in scored if c.baseline_residual == 0)
        skipped = len(res.cases) - len(scored)
        md += [
            "",
            "## Per-case results",
            "",
            f"**{n_pass}/{len(scored)}** cases clean under `compile`; "
            f"**{n_base}/{len(scored)}** under the baseline."
            + (f" ({skipped} configured entity/entities are absent from the fixture and "
               f"cannot separate the approaches — listed, not scored.)" if skipped else ""),
            "",
            "The case unit is the **sensitive entity**: it is what the two approaches "
            "actually disagree about. Both are given the same fixture and scored by the same "
            "casing-aware scan, so every row is a like-for-like comparison. "
            "*Occurrences* is what the detector sees in the **real** repo — the exposure each "
            "approach has to neutralise. A case passes when `compile` leaves **0** residual.",
            "",
            "| # | Case (entity) | kind | level | ghost alias | occurrences (real) "
            "| baseline residual | `compile` residual | result |",
            "|---:|---|---|---|---|---:|---:|---:|---|",
        ]
        for i, c in enumerate(res.cases, 1):
            label = f"`{c.entity_id}`" + (" **(hard)**" if c.hard else "")
            md.append(
                f"| {i} | {label} | {c.kind} | {c.level} | `{c.ghost}` "
                f"| {c.real_occurrences} | {c.baseline_residual} | {c.compile_residual} "
                f"| {c.result} |"
            )
        hard = [c for c in res.cases if c.hard]
        if hard:
            h = hard[0]
            md += [
                "",
                f"**Challenging case — `{h.entity_id}`.** {h.real_occurrences} occurrences "
                f"spread across code, config, env-var names, hostnames and prose, in spellings "
                f"the config never lists literally. The baseline neutralises the spellings it "
                f"was handed and still leaves **{h.baseline_residual}**; the casing engine "
                f"normalises to one canonical entity and re-cases per occurrence, leaving "
                f"**{h.compile_residual}**. This case is why the casing engine exists — see "
                "the Improvement Changelog, Iteration 2.",
            ]

    md += ["", "## Baseline residual leaks by entity", ""]
    if base.residual_by_entity:
        md += ["| entity | residual occurrences |", "|---|---|"]
        md += [f"| `{eid}` | {n} |" for eid, n in sorted(base.residual_by_entity.items())]
    else:
        md.append("_none_")
    md += ["", "## `compile` residual leaks by entity", ""]
    if comp.residual_by_entity:
        md += ["| entity | residual occurrences |", "|---|---|"]
        md += [f"| `{eid}` | {n} |" for eid, n in sorted(comp.residual_by_entity.items())]
    else:
        md.append("_none — clean_")
    md.append("")

    res.report_md.parent.mkdir(parents=True, exist_ok=True)
    res.report_md.write_text("\n".join(md), encoding="utf-8")

    csv_lines = ["metric,baseline,compile,improvement"]
    csv_lines += [
        ",".join(_csv(x) for x in (m, b, c, d)) for m, b, c, d in rows
    ]
    res.report_csv.write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    if res.cases_csv is not None:
        case_lines = ["case,entity,kind,level,ghost_alias,real_occurrences,"
                      "baseline_residual,compile_residual,hard,result"]
        case_lines += [
            ",".join(_csv(x) for x in (
                str(i), c.entity_id, c.kind, c.level, c.ghost,
                str(c.real_occurrences), str(c.baseline_residual), str(c.compile_residual),
                "yes" if c.hard else "no",
                c.result if c.exercised else "n/a"))
            for i, c in enumerate(res.cases, 1)
        ]
        res.cases_csv.write_text("\n".join(case_lines) + "\n", encoding="utf-8")


def _csv(value: str) -> str:
    if any(ch in value for ch in (',', '"', "\n")):
        return '"' + value.replace('"', '""') + '"'
    return value
