"""The detection pass: repo → ranked :class:`~ghostc.detect.candidate.Candidate` list.

Configured entities are matched directly (exact / stem / fuzzy / acronym / phrase).

**Unconfigured entities are only proposed from an anchor** — evidence that is hard
to explain as ordinary code:

* a declared alias list (``known internally as: …``),
* a scoped package (``@meridianaero/flight-sdk``),
* an internal host (``gw.prod.contoso.internal``),
* a de-obfuscated literal that still carries a distinctive stem,
* reference-graph taint that traces back to one of the above.

Weaker mentions (an env var, a camelCase symbol, a comment) only ever *attach* to
an existing anchor by stem match. A token with no anchor is dropped — that is
what keeps ``helmet`` / ``moment`` / ``swagger-jsdoc`` out of the proposals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ghostc.config import load_config
from ghostc.detect.candidate import Candidate, Occurrence, Signal, classify, combine_score
from ghostc.detect.decode import decoded_literals
from ghostc.detect.graph import build_graph, str_node
from ghostc.detect.semantic import using_embeddings
from ghostc.detect.settings import DetectionSettings, detection_settings
from ghostc.detect import signals as sig
from ghostc.detect.shapes import shape_hits
from ghostc.detect.tokenize import contains_run, segments, tokens, words
from ghostc.parsers import scoped
from ghostc.parsers import treesitter as ts
from ghostc.scanning import anchored_scan, iter_text_files

_DEFAULT_LEVEL_BY_KIND = {
    "vendor": "internal", "client": "restricted", "internal_service": "confidential",
    "infra_identifier": "confidential", "domain": "confidential", "secret": "restricted",
    "person": "restricted",
}
_CODE_KINDS = {"identifier", "definition", "import", "env"}

# generic segments that never, on their own, identify an entity
_GENERIC = sig._STOPWORDS | {
    "config", "server", "request", "response", "handler", "module", "export",
    "common", "create", "update", "delete", "default", "option", "options",
    "params", "result", "status", "error", "message", "number", "object",
    "schema", "model", "route", "router", "controller", "middleware", "validate",
    "validation", "logger", "logging", "token", "value", "index", "helper",
    "wrapper", "factory", "adapter", "manager", "context", "primary", "secondary",
    "package", "inventory", "flight", "search", "schedule", "schedules", "email",
    "account", "region", "header", "prod", "production", "development", "staging",
    "availability", "reset", "password", "verify", "refresh", "access", "bearer",
    "strategy", "callback", "connection", "collection", "document", "transport",
    "format", "console", "process", "global", "window", "return", "await", "async",
    "class", "const", "function", "example", "sample", "test", "spec", "mock",
}


def _distinctive(seg: str) -> bool:
    return len(seg) >= 5 and not seg.isdigit() and seg not in _GENERIC


def _stem_hits_anchor(segs: list[str], anchor_stems: dict[str, bool]) -> bool:
    """True if any occurrence segment matches an anchor stem.

    Long stems match by prefix (``meridian`` ↔ ``meridianaero``); short stems
    (acronyms like ``mas``) must match exactly.
    """
    for s in segs:
        for stem, prefix_ok in anchor_stems.items():
            if s == stem:
                return True
            if prefix_ok and len(s) >= 5 and len(stem) >= 5 \
                    and (s.startswith(stem) or stem.startswith(s)):
                return True
    return False


@dataclass
class _Occ:
    file: str
    line: int
    surface: str
    node_kind: str
    context: str
    signals: list[Signal] = field(default_factory=list)
    entity_id: str | None = None
    anchor: str | None = None       # proposal group this occurrence belongs to


@dataclass
class _Anchor:
    key: str
    stems: dict[str, bool] = field(default_factory=dict)   # stem -> prefix-match ok
    kind_hint: str = "vendor"
    seed: Signal | None = None
    display: str = ""

    def add_stem(self, s: str, prefix_ok: bool = True) -> None:
        if s and (self.stems.get(s) is None or prefix_ok):
            self.stems[s] = prefix_ok or self.stems.get(s, False)


@dataclass
class ScanResult:
    candidates: list[Candidate]
    settings: DetectionSettings
    files_scanned: int
    used_embeddings: bool

    def by_action(self, action: str) -> list[Candidate]:
        return [c for c in self.candidates if c.action == action]

    def table(self, limit: int | None = None) -> str:
        rows = self.candidates if limit is None else self.candidates[:limit]
        if not rows:
            return "(no candidates)"
        w = min(max((len(c.surface) for c in rows), default=8), 38)
        out = []
        for c in rows:
            tag = c.entity_id or "(new)"
            out.append(f"{c.surface[:w]:<{w}}  →  {c.score:4.2f}  "
                       f"{c.evidence:<32} [{c.action}] {tag}")
        return "\n".join(out)

    def metrics(self, groundtruth: dict | None) -> dict:
        found = {c.entity_id for c in self.candidates
                 if c.entity_id and c.action != "ignore"}
        proposed = [c for c in self.candidates
                    if not c.entity_id and c.action != "ignore"]
        m = {
            "candidates": len(self.candidates),
            "auto": len(self.by_action("auto")),
            "review": len(self.by_action("review")),
            "ignore": len(self.by_action("ignore")),
            "configured_found": sorted(found),
            "proposed": sorted(c.surface for c in proposed),
        }
        if groundtruth:
            expect = set(groundtruth.get("occurrences", {})) - set(
                groundtruth.get("absent_by_design", []))
            m["recall_configured"] = round(len(found & expect) / len(expect), 3) \
                if expect else None
            m["missed_configured"] = sorted(expect - found)
        return m


# --------------------------------------------------------------------------- #

def scan_repo(repo: str, config_path: str = "privacy.yaml",
              settings: DetectionSettings | None = None,
              cfg: dict | None = None) -> ScanResult:
    repo_p = Path(repo)
    if not repo_p.is_dir():
        raise SystemExit(f"repo not found: {repo}")
    cfg = cfg or load_config(config_path)
    settings = settings or detection_settings(cfg)
    exclusions = cfg.get("exclusions", [])

    profiles = [sig.profile_from_config(e) for e in cfg.get("entities", [])]
    prof_by_id = {p.entity_id: p for p in profiles}
    phrase_owner: dict[str, str] = {}
    for p in profiles:
        for spelling in (*p.names, *p.aliases):
            phrase_owner.setdefault(spelling, p.entity_id)

    files: dict[str, tuple[str, str]] = {}
    n_files = 0
    for rel, text in iter_text_files(repo_p, skip_dirs=(".git", "node_modules")):
        if _excluded(rel, exclusions):
            continue
        n_files += 1
        files[rel] = (text, ts.language_for(rel) or
                      ("scoped" if scoped.handles(rel) else ""))

    # 1. raw occurrences, configured-entity resolution + shape signals
    occs: list[_Occ] = []
    for rel, (text, lang) in files.items():
        occs.extend(_collect_file(rel, text, lang, profiles, phrase_owner, settings))

    # 2. anchors for unconfigured entities
    anchors = _build_anchors(files, occs, profiles)

    # 3. reference-graph taint
    rg = build_graph(files)
    seeds = _graph_seeds(occs, rg)
    taint = rg.taint(seeds, decay=settings.graph_decay,
                     floor_hops=settings.graph_floor_hops)
    _apply_taint(occs, taint, anchors)

    # 4. de-obfuscated literals
    if settings.decode_pass:
        occs.extend(_decode_occs(files, profiles, anchors))

    # 5. attach every unconfigured occurrence to an anchor (or drop it)
    _attach_to_anchors(occs, anchors)

    cands = _aggregate(occs, prof_by_id, anchors, settings)
    cands.sort(key=lambda c: (-c.score, c.entity_id or "~", c.surface))
    return ScanResult(cands, settings, n_files, using_embeddings())


# --------------------------------------------------------------------------- #
# 1. collection                                                               #
# --------------------------------------------------------------------------- #

def _collect_file(rel, text, lang, profiles, phrase_owner, settings) -> list[_Occ]:
    out: list[_Occ] = []
    lines = text.splitlines()

    for hit in anchored_scan(text, phrase_owner):
        line = text.count("\n", 0, hit.start) + 1
        out.append(_Occ(rel, line, hit.text, _kind_at(text, hit.start, rel),
                        _line_ctx(lines, line),
                        [Signal("exact", sig.W_EXACT, hit.text)],
                        entity_id=phrase_owner[hit.text]))

    corroborated = _acronym_corroboration(text, profiles)
    for tok in tokens(text):
        surface, segs = tok.text, list(tok.segments)
        if len(surface) < 2:
            continue
        line = text.count("\n", 0, tok.start) + 1
        node_kind = _kind_at(text, tok.start, rel)
        ctx = _line_ctx(lines, line)
        eid, sigs = _score_against_profiles(surface, segs, node_kind, ctx,
                                            profiles, settings, corroborated)
        shp = _shape_signal_for(surface, text, tok.start)
        if shp is not None:
            sigs = [*sigs, shp]
        if not sigs and eid is None:
            # keep bare tokens with a distinctive segment as *potential* anchor
            # members; unanchored ones are dropped later in _attach_to_anchors,
            # so prose words never survive without a strong anchor.
            if any(_distinctive(s) for s in segs):
                out.append(_Occ(rel, line, surface, node_kind, ctx, []))
            continue
        out.append(_Occ(rel, line, surface, node_kind, ctx, sigs, entity_id=eid))
    return out


def _score_against_profiles(surface, segs, node_kind, ctx, profiles, settings,
                            corroborated) -> tuple[str | None, list[Signal]]:
    best_id, best_signals, best_score = None, [], 0.0
    for p in profiles:
        sigs = [s for s in (
            sig.exact_signal(surface, p),
            sig.stem_signal(segs, p),
            sig.fuzzy_signal(surface, p, min_len=settings.fuzzy_min_len,
                             min_ratio=settings.fuzzy_min_ratio),
            sig.acronym_signal(surface, p, corroborated=p.entity_id in corroborated),
        ) if s is not None]
        if not sigs:
            continue
        imp = sig.import_ref_signal(surface, node_kind)
        if imp is not None:
            sigs.append(imp)
        s = combine_score(sigs)
        if s > best_score:
            best_score, best_id, best_signals = s, p.entity_id, sigs
    return best_id, best_signals


# --------------------------------------------------------------------------- #
# 2. anchors                                                                  #
# --------------------------------------------------------------------------- #

def _build_anchors(files, occs, profiles) -> dict[str, _Anchor]:
    anchors: dict[str, _Anchor] = {}

    def anchor_for(key: str, kind: str, seed: Signal, display: str = "") -> _Anchor:
        a = anchors.get(key)
        if a is None:
            a = _Anchor(key, kind_hint=kind, seed=seed, display=display or key)
            a.add_stem(key)
            anchors[key] = a
        return a

    for rel, (text, lang) in files.items():
        # 2a. declared alias lists
        for group in sig.alias_enumerations(text):
            items_words = [w for item in group for w in words(item)]
            distinct = [w for w in items_words if _distinctive(w)]
            if not distinct:
                continue
            key = min(distinct, key=len)
            a = anchor_for(key, "vendor",
                           Signal("alias_enum", sig.W_ALIAS_ENUM, "declared alias"),
                           display=max(group, key=len))
            for w in items_words:
                a.add_stem(w, prefix_ok=len(w) >= 5)

        # 2b. scoped npm packages + 2c. internal hosts
        for h in shape_hits(text):
            if h.kind == "scoped_npm_package":
                scope = h.text.split("/", 1)[0].lstrip("@")
                segs = [s for s in segments(scope) if _distinctive(s)]
                if segs:
                    key = min(segs, key=len)
                    a = anchor_for(key, "vendor",
                                   Signal("import_ref", sig.W_IMPORT_REF,
                                          "scoped package"),
                                   display=h.text)
                    for s in segments(scope):
                        a.add_stem(s)
            elif h.kind == "internal_host":
                labels = [s for s in h.text.replace("://", ".").split(".")
                          if _distinctive(s)]
                if labels:
                    key = min(labels, key=len)
                    anchor_for(key, "infra_identifier",
                               Signal("shape", h.weight, "internal host"),
                               display=h.text)
            elif h.kind == "tenant_id":
                for s in segments(h.text):
                    if _distinctive(s) and s in anchors:
                        anchors[s].add_stem(s)
    return anchors


# --------------------------------------------------------------------------- #
# 3. graph taint                                                              #
# --------------------------------------------------------------------------- #

def _graph_seeds(occs, rg) -> dict[str, float]:
    seeds: dict[str, float] = {}
    if rg.edges is None:
        return seeds
    for o in occs:
        s = combine_score(o.signals)
        if s < 0.5:
            continue
        for node in (o.surface, str_node(o.surface)):
            if node in rg.edges:
                seeds[node] = max(seeds.get(node, 0.0), s)
    return seeds


def _apply_taint(occs, taint, anchors) -> None:
    if not taint:
        return
    by_surface: dict[str, list[_Occ]] = {}
    for o in occs:
        by_surface.setdefault(o.surface, []).append(o)

    for node, info in taint.items():
        if info.hops == 0:
            continue
        name = node.split(":", 1)[1] if node.startswith(("str:", "env:", "member:")) \
            else node
        anc = _anchor_key_for(name, anchors) or _anchor_key_for(_short(info.via), anchors)
        s = Signal("graph", min(sig.W_GRAPH_CAP, info.score),
                   f"{info.hops} hop(s) from {_short(info.via)}")
        targets = by_surface.get(name)
        if targets:
            for o in targets:
                if o.entity_id is None:
                    o.signals.append(s)
                    if anc:
                        o.anchor = anc
        elif node.startswith("str:") or node.startswith("env:"):
            continue
        elif not node.startswith("member:"):
            occs.append(_Occ("(graph)", 0, name, "identifier", "", [s], anchor=anc))


def _anchor_key_for(name: str, anchors) -> str | None:
    segs = segments(name)
    for key, a in anchors.items():
        if _stem_hits_anchor(segs, a.stems):
            return key
    return None


# --------------------------------------------------------------------------- #
# 4. decode                                                                   #
# --------------------------------------------------------------------------- #

def _decode_occs(files, profiles, anchors) -> list[_Occ]:
    out: list[_Occ] = []
    stems = [(p, s) for p in profiles for s in p.stems]
    for rel, (text, lang) in files.items():
        if lang not in ("javascript", "typescript", "tsx"):
            continue
        for d in decoded_literals(text):
            dsegs = segments(d.text) or words(d.text)
            matched = next((p.entity_id for p, st in stems
                            if contains_run(dsegs, st) is not None), None)
            anc = None if matched else _anchor_key_for(d.text, anchors)
            if matched is None and anc is None:
                if not any(_distinctive(s) for s in dsegs):
                    continue
            out.append(_Occ(rel, d.line, d.text, "string", d.text,
                            [Signal("decoded", 0.5, d.method)],
                            entity_id=matched, anchor=anc))
    return out


# --------------------------------------------------------------------------- #
# 5. attach unconfigured occurrences to anchors                               #
# --------------------------------------------------------------------------- #

def _attach_to_anchors(occs, anchors) -> None:
    for o in occs:
        if o.entity_id is not None:
            continue
        key = o.anchor or _anchor_key_for(o.surface, anchors)
        if key is None:
            continue
        o.anchor = key
        if not any(s.name in ("stem", "alias_enum", "decoded") for s in o.signals):
            stem = _matched_stem(segments(o.surface), anchors[key].stems)
            if stem:
                o.signals.append(Signal("stem", sig.W_STEM * 0.8, stem))


def _matched_stem(segs, anchor_stems) -> str | None:
    for s in segs:
        for stem, prefix_ok in anchor_stems.items():
            if s == stem:
                return stem
            if prefix_ok and len(s) >= 5 and len(stem) >= 5 \
                    and (s.startswith(stem) or stem.startswith(s)):
                return stem
    return None


# --------------------------------------------------------------------------- #
# 6. aggregation                                                              #
# --------------------------------------------------------------------------- #

def _aggregate(occs, prof_by_id, anchors, settings) -> list[Candidate]:
    groups: dict[str, list[_Occ]] = {}
    for o in occs:
        if o.entity_id is not None:
            groups.setdefault(f"id:{o.entity_id}", []).append(o)
        elif o.anchor is not None:
            groups.setdefault(f"anc:{o.anchor}", []).append(o)

    out: list[Candidate] = []
    for key, members in groups.items():
        by_name: dict[str, Signal] = {}
        for o in members:
            for s in o.signals:
                if s.name not in by_name or s.weight > by_name[s.name].weight:
                    by_name[s.name] = s

        if key.startswith("id:"):
            eid = key[3:]
            p = prof_by_id.get(eid)
            kind, level, resolved = (p.kind, p.level, True) if p else (None, None, True)
            merged = list(by_name.values())
        else:
            eid, resolved = None, False
            anc = anchors[key[4:]]
            merged = list(by_name.values())
            if anc.seed is not None and anc.seed.name not in by_name:
                merged.append(anc.seed)
            if not _keep_proposal(members, {s.name: s for s in merged}):
                continue
            # the anchor's own signal (alias list / scoped pkg / internal host) is the
            # kind hint — more reliable than scanning surrounding text for keywords
            kind = anc.kind_hint
            level = _DEFAULT_LEVEL_BY_KIND.get(kind, "confidential")
            merged.append(sig.weak_signal())

        score = combine_score(merged)
        action = classify(score=score, level=level, resolved=resolved,
                          signals=merged, settings=settings)
        real_occs = [o for o in members if o.file != "(graph)"]
        surfaces = list(dict.fromkeys(o.surface for o in real_occs)) or \
            list(dict.fromkeys(o.surface for o in members))
        if key.startswith("id:") and prof_by_id.get(key[3:]) and prof_by_id[key[3:]].names:
            rep = prof_by_id[key[3:]].names[0]
        else:
            rep = _representative(members, anchors.get(key[4:]))
        out.append(Candidate(
            surface=rep, entity_id=eid, kind=kind, level=level, score=score,
            signals=sorted(merged, key=lambda s: -s.weight), action=action,
            occurrences=[Occurrence(o.file, o.line, o.surface, o.node_kind)
                         for o in real_occs],
            aliases=[s for s in surfaces if s != rep],
        ))
    return out


def _keep_proposal(members, by_name) -> bool:
    n = len(members)
    files = {o.file for o in members if o.file != "(graph)"}
    code = any(o.node_kind in _CODE_KINDS for o in members)
    if "alias_enum" in by_name:
        return True
    imp = by_name.get("import_ref")
    if imp is not None and imp.detail == "scoped package":
        return True
    g = by_name.get("graph")
    if g is not None and g.weight >= 0.55:
        return True
    if "shape" in by_name and (n >= 2 or len(files) >= 2):
        return True
    if "decoded" in by_name and n >= 1 and code:
        return True
    return False


def _representative(members, anchor: _Anchor | None) -> str:
    named = [o.surface for o in members
             if o.node_kind in ("comment", "string") and " " in o.surface
             and len(o.surface) <= 48]
    if named:
        return max(named, key=len)
    if anchor and anchor.display and anchor.display != anchor.key:
        return anchor.display
    surfaces = [o.surface for o in members if o.file != "(graph)"] or \
        [o.surface for o in members]
    return max(surfaces, key=len) if surfaces else (anchor.key if anchor else "?")


# --------------------------------------------------------------------------- #
# helpers                                                                     #
# --------------------------------------------------------------------------- #

def _short(via: str) -> str:
    return via.replace("str:", "").replace("env:", "").replace("member:", "")


def _kind_at(text: str, pos: int, rel: str) -> str:
    name = rel.rsplit("/", 1)[-1]
    if name.startswith(".env") or name.endswith(".env"):
        return "env"
    line_start = text.rfind("\n", 0, pos) + 1
    prefix = text[line_start:pos]
    stripped = prefix.lstrip()
    if "//" in prefix or stripped.startswith(("*", "/*", "#")):
        return "comment"
    if "import " in prefix or "require(" in prefix or prefix.rstrip().endswith("from"):
        return "import"
    if prefix.rstrip().endswith(("const", "let", "var", "function", "class")):
        return "definition"
    if '"' in prefix or "'" in prefix or "`" in prefix:
        return "string"
    return "identifier"


def _line_ctx(lines, line) -> str:
    i = max(0, line - 1)
    return lines[i].strip() if i < len(lines) else ""


def _acronym_corroboration(text, profiles) -> set[str]:
    present = set()
    for tok in tokens(text):
        present.update(tok.segments)
    out = set()
    for p in profiles:
        for st in p.stems:
            if st and all(s in present for s in st):
                out.add(p.entity_id)
    return out


def _shape_signal_for(surface, text, pos) -> Signal | None:
    window = text[max(0, pos - 2):pos + len(surface) + 2]
    for h in shape_hits(window):
        if surface in h.text or h.text in surface:
            return Signal("shape", h.weight, h.kind)
    return None


def _excluded(rel, patterns) -> bool:
    import fnmatch

    parts = rel.split("/")
    for pat in patterns:
        if fnmatch.fnmatch(rel, pat):
            return True
        core = pat.strip("*/")
        if "/" not in core and (core in parts or fnmatch.fnmatch(parts[-1], core)):
            return True
    return False
