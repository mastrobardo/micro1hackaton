"""Reverse patch compiler — ghost PR diff -> real PR diff.

Translates ghost aliases back to real spellings via the mapping store + the
``privacy.yaml`` match rules, using the same segment / casing engine as ``compile``
(:mod:`ghostc.aliasing`). Two passes per diff line: exact ``ghost`` literal ->
``real`` literal (token-boundary anchored, longest first), then segment splicing
for the remaining casings (``vendorA`` -> ``skyRoute``, ``VENDOR_A_URL`` ->
``SKYROUTE_URL``, ``vendorAClient.js`` -> ``skyRouteClient.js``).

Fail closed — :class:`Rejection` (CLI exit 1, ``patch.rejected`` audit, nothing
written) on:

* an unmapped ghost-alias-shaped token (the agent invented an alias),
* a real value already present in the ghost diff (the ghost should never hold one),
* a mapping-version mismatch,
* a duplicate ghost alias in the store (ambiguous resolution).

Reversal is lossy for entities whose real name is a multi-word display string
(``Northwind Airlines``, ``SkyRoute Data Ltd``): code tokens reverse cleanly, prose
casings land approximately. Those entities are flagged ``lossy`` and the pipeline's
human review gate (PR-consistency agent) is downstream of this step by design.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ghostc.aliasing import analyze, splice_span
from ghostc.audit import AuditLog, hash_real, new_operation_id
from ghostc.config import load_config
from ghostc.scanning import anchored_scan

_SCAN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*")
_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*$")


class Rejection(Exception):
    """Raised on any fail-closed condition. The reverse compiler writes nothing."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail

    def __str__(self) -> str:
        return f"{self.reason}: {self.detail}" if self.detail else self.reason


@dataclass
class ReverseEntity:
    entity_id: str
    level: str
    ghost: str                    # canonical kebab ghost alias
    real: str                     # canonical real (display) spelling
    ghost_segments: list[str]
    real_segments: list[str]
    ghost_prefix: str             # "vendor", "service", ...

    @property
    def lossy(self) -> bool:
        # multi-word display names (`Northwind Airlines`) can't recover word count /
        # prose casing on the way back; single tokens and dotted values round-trip.
        return " " in self.real


@dataclass
class PatchResult:
    real_diff: str
    entities_resolved: list[str] = field(default_factory=list)
    lossy_entities: list[str] = field(default_factory=list)
    files: int = 0
    hunks: int = 0
    applied: bool = False
    branch: str | None = None

    def summary(self) -> str:
        lines = [
            f"translated: {self.files} file(s), {self.hunks} hunk(s)",
            f"entities resolved: {', '.join(self.entities_resolved) or '(none)'}",
        ]
        if self.lossy_entities:
            lines.append(f"LOSSY (multi-word real name — verify prose): "
                         f"{', '.join(self.lossy_entities)}")
        if self.applied:
            lines.append(f"applied to branch: {self.branch}")
        return "\n".join(lines)


def _seg(token: str) -> list[str]:
    segs, _ = analyze(token)
    return [s.text for s in segs]


def _reverse_entities(mapping: dict, cfg: dict) -> list[ReverseEntity]:
    # per entity, the identifier match spelling that segments into the *most* pieces —
    # it reverses with the best fidelity (`skyRoute` -> [sky, route] beats `skyroute`).
    match_ident: dict[str, str] = {}
    for e in cfg.get("entities", []):
        cands = [m["value"] for m in e.get("match", []) if m.get("kind") == "identifier"]
        if cands:
            match_ident[e["id"]] = max(cands, key=lambda v: (len(_seg(v)), len(v)))

    out: list[ReverseEntity] = []
    seen: set[str] = set()
    for entry in mapping.get("entries", []):
        ghost = entry.get("ghost") or ""
        if not ghost:                        # remove-strategy: nothing to reverse
            continue
        if ghost in seen:
            raise Rejection("ambiguous mapping", f"duplicate ghost alias {ghost!r}")
        seen.add(ghost)

        eid, real = entry["entity_id"], entry["real"]
        if eid in match_ident:
            real_segs = _seg(match_ident[eid])
        elif _TOKEN_RE.match(real):
            real_segs = _seg(real)
        else:
            real_segs = [w.lower() for w in re.split(r"[^A-Za-z0-9]+", real) if w]

        ghost_segs = _seg(ghost.split(".")[0])   # host-a.example -> ["host", "a"]
        out.append(ReverseEntity(eid, entry.get("level", "internal"), ghost, real,
                                 ghost_segs, real_segs, ghost_segs[0]))
    return out


def _translate(text: str, rents: list[ReverseEntity]) -> tuple[str, set[str]]:
    used: set[str] = set()

    # 1. exact ghost literal -> real literal, token-boundary anchored, longest first
    for r in sorted(rents, key=lambda r: -len(r.ghost)):
        rx = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(r.ghost) + r"(?![A-Za-z0-9_])")
        if rx.search(text):
            text = rx.sub(lambda _m, _r=r.real: _r, text)
            used.add(r.entity_id)

    # 1b. the space-separated display renderings of a multi-segment alias
    #     (`Vendor A`, `VENDOR A` — how `compile` writes a display literal like
    #     "SkyRoute Data Ltd"). Segment splice below can't see across a space, so a
    #     comment or prose line the consultancy wrote using the ghost display name
    #     would otherwise carry a ghost alias into the real PR.
    for r in sorted(rents, key=lambda r: -len(r.ghost_segments)):
        if len(r.ghost_segments) < 2:
            continue
        for variant in (" ".join(s.capitalize() for s in r.ghost_segments),
                        " ".join(s.upper() for s in r.ghost_segments)):
            rx = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(variant) + r"(?![A-Za-z0-9_])")
            if rx.search(text):
                text = rx.sub(lambda _m, _r=r.real: _r, text)
                used.add(r.entity_id)

    # 2. segment splice for the remaining alias casings (vendorA, VENDOR_A_URL, ...)
    hits: list[tuple[int, int, str, str]] = []
    for r in rents:
        for m in _SCAN_RE.finditer(text):
            sp = splice_span(m.group(0), r.ghost_segments, r.real_segments)
            if sp is None:
                continue
            cs, ce, repl = sp
            if repl != m.group(0)[cs:ce]:
                hits.append((m.start() + cs, m.start() + ce, repl, r.entity_id))

    hits.sort(key=lambda h: (-(h[1] - h[0]), h[0]))
    taken: list[tuple[int, int]] = []
    picked: list[tuple[int, int, str, str]] = []
    for h in hits:
        if any(not (h[1] <= t0 or h[0] >= t1) for t0, t1 in taken):
            continue
        taken.append((h[0], h[1]))
        picked.append(h)
    for s, e, repl, eid in sorted(picked, key=lambda h: h[0], reverse=True):
        text = text[:s] + repl + text[e:]
        used.add(eid)
    return text, used


_HEADER_PREFIXES = ("--- ", "+++ ", "diff --git ", "rename from ", "rename to ",
                    "copy from ", "copy to ")


def _reverse_diff(diff_text: str, rents: list[ReverseEntity]) -> tuple[str, set[str], int, int]:
    out: list[str] = []
    used: set[str] = set()
    files = hunks = 0
    for raw in diff_text.splitlines():
        if raw.startswith("diff --git "):
            files += 1
        if raw.startswith("@@"):
            hunks += 1
        if raw.startswith(_HEADER_PREFIXES):
            t, u = _translate(raw, rents)
        elif raw[:1] in ("+", "-", " ") and not raw.startswith(("+++", "---")):
            t_body, u = _translate(raw[1:], rents)
            t = raw[0] + t_body
        else:
            t, u = raw, set()
        out.append(t)
        used |= u
    tail = "\n" if diff_text.endswith("\n") else ""
    return "\n".join(out) + tail, used, files, hunks


def _check_ghost_diff(diff_text: str, rents: list[ReverseEntity], mapping: dict,
                      cfg: dict, expect_version: int | None) -> None:
    if expect_version is not None and mapping.get("mapping_version") != expect_version:
        raise Rejection("mapping-version mismatch",
                        f"diff expects {expect_version}, store is "
                        f"{mapping.get('mapping_version')}")

    added = "\n".join(l[1:] for l in diff_text.splitlines()
                      if l[:1] in ("+", " ") and not l.startswith("+++"))

    needles: dict[str, str] = {}
    for e in mapping.get("entries", []):
        if e.get("real"):
            needles.setdefault(e["real"], e["entity_id"])
    for e in cfg.get("entities", []):
        needles.setdefault(e["real"], e["id"])
        for m in e.get("match", []):
            if m.get("kind") in ("literal", "identifier"):
                needles.setdefault(m["value"], e["id"])
    leaks = anchored_scan(added, needles)
    if leaks:
        # name the owning entities, never the cleartext values (audit contract)
        raise Rejection("unexpected real entity in the ghost diff",
                        ", ".join(sorted({needles[h.text] for h in leaks})))

    prefixes = sorted({r.ghost_prefix for r in rents})
    if prefixes:
        known = {r.ghost for r in rents} | {r.ghost.split(".")[0] for r in rents}
        # separator form (`service-a`, `SERVICE_A`): prefix in any case.
        # no-separator form (`serviceA`, `ServiceA`): mixed case only + an upper/digit
        # tail, so an all-caps plural like `SERVICES` and a lowercase `services` are
        # both left alone.
        sep_pfx = "|".join(re.escape(v) for p in prefixes
                           for v in (p, p.capitalize(), p.upper()))
        cap_pfx = "|".join(re.escape(v) for p in prefixes for v in (p, p.capitalize()))
        alias_rx = re.compile(
            rf"(?<![A-Za-z0-9_])(?:(?P<p1>{sep_pfx})[-_](?P<s>[A-Za-z0-9])"
            rf"|(?P<p2>{cap_pfx})(?P<c>[A-Z0-9]))(?![A-Za-z0-9])")
        unmapped: set[str] = set()
        for line in added.splitlines():
            for m in alias_rx.finditer(line):
                prefix = (m.group("p1") or m.group("p2")).lower()
                letter = (m.group("s") or m.group("c")).lower()
                if f"{prefix}-{letter}" not in known:
                    unmapped.add(m.group(0))
        if unmapped:
            raise Rejection("unmapped ghost-alias-shaped token",
                            ", ".join(sorted(unmapped)) + " — not in the mapping store")


# --------------------------------------------------------------------------- #
#  reverse_apply — handoff/base-anchored reverse compile (used by open-real-pr) #
# --------------------------------------------------------------------------- #
#
# `reverse_patch` above rebuilds the real diff by token-translating *every* line
# of the ghost diff, context lines included. Forward `compile` is not a perfect
# token-level involution (`SKYROUTE_API_KEY` -> `VENDOR_A_API_KEY` -> reverse
# `SKY_ROUTE_API_KEY`), so translated context can drift from the real file and
# `git apply` then rejects the hunk.
#
# `reverse_apply` sidesteps that: forward `compile` is *line-preserving* (it only
# rewrites tokens inside a line, never adds/removes lines), so ghost-repo line N
# at the handoff commit corresponds 1:1 to real-repo line N at the PR base. It
# replays the consultancy's hunks onto the *real base file* — context and removed
# lines are taken verbatim from the real pre-image by position, only added lines
# are token-translated — and returns concrete file contents that always apply.


@dataclass
class _Hunk:
    old_start: int
    old_count: int
    lines: list[tuple[str, str]] = field(default_factory=list)   # (tag, content), tag in " -+"


@dataclass
class _FileDiff:
    old_path: str
    new_path: str
    is_new: bool = False
    is_delete: bool = False
    hunks: list[_Hunk] = field(default_factory=list)


@dataclass
class ReverseApplyResult:
    files: dict[str, str | None]          # real rel path -> new content, or None = delete
    entities_resolved: list[str] = field(default_factory=list)
    lossy_entities: list[str] = field(default_factory=list)
    n_files: int = 0
    n_hunks: int = 0
    fallbacks: list[str] = field(default_factory=list)   # files that missed the line-map anchor


_DIFF_HDR = re.compile(r"^diff --git a/(.+?) b/(.+)$")
_HUNK_HDR = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _parse_unified(diff_text: str) -> list[_FileDiff]:
    files: list[_FileDiff] = []
    cur: _FileDiff | None = None
    hunk: _Hunk | None = None
    for raw in diff_text.splitlines():
        m = _DIFF_HDR.match(raw)
        if m:
            cur = _FileDiff(m.group(1), m.group(2))
            files.append(cur)
            hunk = None
            continue
        if cur is None:
            continue
        if raw.startswith("new file mode"):
            cur.is_new = True
        elif raw.startswith("deleted file mode"):
            cur.is_delete = True
        elif (hm := _HUNK_HDR.match(raw)):
            hunk = _Hunk(int(hm.group(1)), int(hm.group(2) or 1))
            cur.hunks.append(hunk)
        elif raw.startswith("\\"):                       # "\ No newline at end of file"
            continue
        elif hunk is not None and raw[:1] in (" ", "+", "-"):
            hunk.lines.append((raw[0], raw[1:]))
        elif hunk is not None and raw == "":             # a bare blank = context blank line
            hunk.lines.append((" ", ""))
    return files


def _splice_index(h: _Hunk) -> int:
    # `@@ -3,2 ...` replaces lines 3-4  -> index 2 ; `@@ -5,0 ...` inserts after line 5 -> index 5
    return h.old_start - 1 if h.old_count > 0 else h.old_start


def _apply_hunks(base_lines: list[str], hunks: list[_Hunk], *,
                 render_add) -> list[str]:
    """Replay *hunks* onto *base_lines*. Context / removed lines are consumed from
    the base by position; added lines come from ``render_add(content)``."""
    lines = list(base_lines)
    for h in sorted(hunks, key=lambda h: h.old_start, reverse=True):
        i = _splice_index(h)
        seg: list[str] = []
        k = 0
        for tag, content in h.lines:
            if tag == " ":
                seg.append(lines[i + k] if i + k < len(lines) else content)
                k += 1
            elif tag == "-":
                k += 1
            else:                                        # "+"
                seg.append(render_add(content))
        lines[i:i + h.old_count] = seg
    return lines


def _body_lines(text: str) -> tuple[list[str], str]:
    """Split keeping the trailing-newline flag; the final "" from a trailing \\n is dropped."""
    trailing = "\n" if text.endswith("\n") else ""
    parts = text.split("\n")
    if trailing:
        parts = parts[:-1]
    return parts, trailing


def reverse_apply(ghost_diff: str, mapping_path: str, *, config_path: str = "privacy.yaml",
                  ghost_at=None, real_at=None, mapping_version: int | None = None,
                  audit_path: str = "workspace/private/audit.jsonl") -> ReverseApplyResult:
    """Reverse-compile a ghost *impl* diff into concrete real-repo file contents.

    ``ghost_at(rel) -> str | None``  ghost file content at the handoff commit.
    ``real_at(rel)  -> str | None``  real file content at the PR base.

    Fail-closed (:class:`Rejection`, ``patch.rejected`` audit) on the same
    conditions as :func:`reverse_patch` — unmapped alias-shaped token, a real
    value already in the ghost diff, mapping-version mismatch, duplicate ghost
    alias.
    """
    mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
    cfg = load_config(config_path)
    audit = AuditLog(audit_path, new_operation_id())
    try:
        rents = _reverse_entities(mapping, cfg)
        _check_ghost_diff(ghost_diff, rents, mapping, cfg, mapping_version)
    except Rejection as rej:
        audit.emit("patch.rejected", "reverse-compiler", decision="block",
                   details={"reason": rej.reason, "detail": rej.detail})
        raise

    used: set[str] = set()

    def tr(s: str) -> str:
        t, u = _translate(s, rents)
        used.update(u)
        return t

    out: dict[str, str | None] = {}
    fallbacks: list[str] = []
    fds = _parse_unified(ghost_diff)
    n_hunks = sum(len(fd.hunks) for fd in fds)

    for fd in fds:
        real_old, real_new = tr(fd.old_path), tr(fd.new_path)

        if fd.is_delete:
            out[real_old] = None
            continue

        if fd.is_new or (ghost_at and ghost_at(fd.old_path) is None):
            added = [c for h in fd.hunks for (tag, c) in h.lines if tag == "+"]
            out[real_new] = "\n".join(tr(l) for l in added) + "\n"
            continue

        gb = ghost_at(fd.old_path) if ghost_at else None
        rb = real_at(real_old) if real_at else None
        if gb is None or rb is None:
            # no anchor available — translate the reconstructed ghost-impl wholesale
            gi = _apply_hunks((gb or "").split("\n"), fd.hunks, render_add=lambda c: c)
            out[real_new] = "\n".join(tr(l) for l in gi)
            fallbacks.append(real_new)
            continue

        gbl, _ = _body_lines(gb)
        rbl, trailing = _body_lines(rb)
        if len(gbl) != len(rbl):
            gi = _apply_hunks(gbl, fd.hunks, render_add=lambda c: c)
            out[real_new] = "\n".join(tr(l) for l in gi) + trailing
            fallbacks.append(real_new)
            continue

        merged = _apply_hunks(rbl, fd.hunks, render_add=tr)
        out[real_new] = "\n".join(merged) + trailing
        if real_old != real_new:
            out.setdefault(real_old, None)               # sensitive path component renamed

    by_id = {r.entity_id: r for r in rents}
    lossy = sorted(eid for eid in used if by_id[eid].lossy)
    audit.emit("patch.parsed", "reverse-compiler",
               details={"files": len(fds), "hunks": n_hunks,
                        "entities_resolved": sorted(used), "fallbacks": fallbacks})
    for eid in sorted(used):
        r = by_id[eid]
        audit.emit("patch.entity_resolved", "reverse-compiler", level=r.level,
                   subject={"entity_id": eid, "real_sha256": hash_real(r.real)},
                   details={"lossy": r.lossy})
    return ReverseApplyResult(out, sorted(used), lossy, len(fds), n_hunks, fallbacks)


def _git_apply(real: Path, branch: str, diff: str) -> None:
    if not (real / ".git").is_dir():
        raise Rejection("apply target is not a git repo", str(real))
    b = subprocess.run(["git", "-C", str(real), "checkout", "-b", branch],
                       capture_output=True, text=True)
    if b.returncode != 0:
        raise Rejection("could not create branch", b.stderr.strip())
    p = subprocess.run(
        ["git", "-C", str(real), "apply", "--3way", "--whitespace=nowarn", "-"],
        input=diff, capture_output=True, text=True)
    if p.returncode != 0:
        raise Rejection("git apply failed", (p.stderr or p.stdout).strip())


def reverse_patch(ghost_diff: str, mapping_path: str, *, config_path: str = "privacy.yaml",
                  real_repo: str | None = None, mapping_version: int | None = None,
                  do_apply: bool = False, branch: str = "ghostc/reverse-patch",
                  audit_path: str = "workspace/private/audit.jsonl") -> PatchResult:
    diff_text = Path(ghost_diff).read_text(encoding="utf-8")
    mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
    cfg = load_config(config_path)

    audit = AuditLog(audit_path, new_operation_id())
    try:
        rents = _reverse_entities(mapping, cfg)
        _check_ghost_diff(diff_text, rents, mapping, cfg, mapping_version)
        real_diff, used, files, hunks = _reverse_diff(diff_text, rents)
    except Rejection as rej:
        audit.emit("patch.rejected", "reverse-compiler", decision="block",
                   details={"reason": rej.reason, "detail": rej.detail})
        raise

    audit.emit("patch.parsed", "reverse-compiler",
               details={"files": files, "hunks": hunks,
                        "entities_resolved": sorted(used)})
    by_id = {r.entity_id: r for r in rents}
    lossy = sorted(eid for eid in used if by_id[eid].lossy)
    for eid in sorted(used):
        r = by_id[eid]
        audit.emit("patch.entity_resolved", "reverse-compiler", level=r.level,
                   subject={"entity_id": eid, "real_sha256": hash_real(r.real)},
                   details={"lossy": r.lossy})

    result = PatchResult(real_diff, sorted(used), lossy, files, hunks)

    if do_apply:
        if not real_repo:
            raise Rejection("apply requires --real", "no real repo given")
        _git_apply(Path(real_repo), branch, real_diff)
        result.applied = True
        result.branch = branch
        audit.emit("patch.applied", "reverse-compiler", subject={"branch": branch},
                   details={"entities": sorted(used)})
    return result
