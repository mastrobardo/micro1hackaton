"""Reference graph + decaying taint propagation.

``adversary.js`` deliberately launders the vendor identity through aliases::

    const { MeridianClient: RestrictedFlightClient } = require('@meridianaero/flight-sdk');
    const client         = new RestrictedFlightClient({ ... });
    const flightProvider = client;
    const providers      = { primary: flightProvider };
    providers.primaryEndpoint = MAS_ENDPOINT;

Lexically, ``client`` / ``flightProvider`` / ``providers.primary`` carry no vendor
string at all. This module builds a directed value-flow graph over the JS/TS
trees — ``const a = b`` aliases, ``new C()``, ``require`` destructuring,
``obj.prop = x``, call arguments, ``module.exports``, ``x || 'literal'`` defaults,
``process.env.NAME`` — and propagates a score outward from the nodes that *do*
carry entity evidence, multiplied by ``decay`` per hop.

Node ids are bare identifier names (scope-insensitive — an accepted imprecision;
the taint decays and never auto-transforms on the graph signal alone unless it is
already ≥ 0.9). String / env / member nodes are namespaced.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

try:  # networkx is a core dep, but keep the import defensive for partial installs
    import networkx as nx
except ModuleNotFoundError:  # pragma: no cover
    nx = None

from tree_sitter_language_pack import get_parser

_JS_LANGS = {"javascript", "typescript", "tsx"}


def str_node(value: str) -> str:
    return f"str:{value}"


def env_node(name: str) -> str:
    return f"env:{name}"


def member_node(obj: str, prop: str) -> str:
    return f"member:{obj}.{prop}"


@dataclass
class TaintInfo:
    score: float
    hops: int
    via: str          # id of the nearest seed the taint came from

    def to_dict(self) -> dict:
        return {"score": round(self.score, 4), "hops": self.hops, "via": self.via}


@dataclass
class ReferenceGraph:
    edges: object = field(default=None)          # nx.DiGraph
    exported: set[str] = field(default_factory=set)
    string_values: dict[str, str] = field(default_factory=dict)  # str-node -> raw value
    env_names: set[str] = field(default_factory=set)

    def taint(self, seeds: dict[str, float], decay: float = 0.85,
              floor_hops: int = 3) -> dict[str, TaintInfo]:
        """BFS from *seeds* (id -> starting score) along edge direction."""
        if self.edges is None:
            return {}
        out: dict[str, TaintInfo] = {}
        q: deque[tuple[str, float, int, str]] = deque()
        for sid, score in seeds.items():
            if sid in self.edges:
                out[sid] = TaintInfo(score, 0, sid)
                q.append((sid, score, 0, sid))
        while q:
            node, score, hops, via = q.popleft()
            if hops >= floor_hops:
                continue
            nxt_score = round(score * decay, 4)
            if nxt_score < 0.05:
                continue
            for _, dst in self.edges.out_edges(node):
                prev = out.get(dst)
                if prev is None or nxt_score > prev.score:
                    out[dst] = TaintInfo(nxt_score, hops + 1, via)
                    q.append((dst, nxt_score, hops + 1, via))
        return out


def build_graph(files: dict[str, tuple[str, str]]) -> ReferenceGraph:
    """*files*: rel-path -> (source, tree-sitter lang). Non-JS entries are ignored."""
    if nx is None:  # pragma: no cover
        return ReferenceGraph()
    g = nx.DiGraph()
    rg = ReferenceGraph(edges=g)
    for _rel, (source, lang) in files.items():
        if lang not in _JS_LANGS:
            continue
        try:
            _walk_file(source, lang, g, rg)
        except Exception:  # pragma: no cover - a parse quirk must not kill discovery
            continue
    return rg


# --------------------------------------------------------------------------- #
# tree-sitter walk                                                            #
# --------------------------------------------------------------------------- #

def _text(node, data: bytes) -> str:
    return data[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _child(node, field: str):
    return node.child_by_field_name(field)


def _string_value(node, data: bytes) -> str | None:
    if node.type in ("string", "template_string"):
        raw = _text(node, data)
        return raw[1:-1] if len(raw) >= 2 else raw
    return None


def _add(g, src: str, dst: str, kind: str) -> None:
    if src and dst and src != dst:
        g.add_edge(src, dst, kind=kind)


_IDENT_TYPES = {"identifier", "shorthand_property_identifier",
                "shorthand_property_identifier_pattern"}


def _idents_in(node, data: bytes) -> list[str]:
    out: list[str] = []
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type in _IDENT_TYPES:
            txt = _text(n, data)
            if txt not in ("this", "super"):
                out.append(txt)
        else:
            stack.extend(n.children)
    return out


def _walk_file(source: str, lang: str, g, rg: ReferenceGraph) -> None:
    data = source.encode("utf-8")
    tree = get_parser(lang).parse(data)

    def visit(node) -> None:
        t = node.type
        if t == "variable_declarator":
            _handle_declarator(node, data, g, rg)
        elif t == "assignment_expression":
            _handle_assignment(node, data, g, rg)
        elif t == "call_expression":
            _handle_call(node, data, g)
        elif t == "member_expression":
            _handle_member(node, data, g, rg)
        for c in node.children:
            visit(c)

    visit(tree.root_node)
    _collect_exports(tree.root_node, data, rg)


def _handle_declarator(node, data, g, rg) -> None:
    name_node, value = _child(node, "name"), _child(node, "value")
    if value is None:
        return
    targets = _idents_in(name_node, data) if name_node else []
    # `const { A: B } = require('pkg')` — bound names sit under an object_pattern
    for tgt in targets:
        _flow_into(value, tgt, data, g, rg)


def _handle_assignment(node, data, g, rg) -> None:
    left, right = _child(node, "left"), _child(node, "right")
    if left is None or right is None:
        return
    if left.type == "member_expression":
        obj = _child(left, "object")
        prop = _child(left, "property")
        if obj is not None and prop is not None:
            mnode = member_node(_text(obj, data), _text(prop, data))
            _flow_into(right, mnode, data, g, rg)
            _add(g, mnode, _text(obj, data), "member-of")
    elif left.type == "identifier":
        _flow_into(right, _text(left, data), data, g, rg)


def _handle_call(node, data, g) -> None:
    fn = _child(node, "function")
    args = _child(node, "arguments")
    if fn is None or args is None or fn.type != "identifier":
        return
    fname = _text(fn, data)
    for arg in args.named_children:
        for ident in _idents_in(arg, data):
            _add(g, ident, fname, "arg")


def _handle_member(node, data, g, rg) -> None:
    obj = _child(node, "object")
    prop = _child(node, "property")
    if obj is None or prop is None:
        return
    if _text(obj, data) == "env" or _text(obj, data).endswith(".env"):
        rg.env_names.add(_text(prop, data))
    if node.type == "member_expression" and obj.type == "member_expression":
        inner_obj = _child(obj, "object")
        inner_prop = _child(obj, "property")
        if (inner_obj is not None and _text(inner_obj, data) == "process"
                and inner_prop is not None and _text(inner_prop, data) == "env"):
            name = _text(prop, data)
            rg.env_names.add(name)
            _add(g, env_node(name), env_node(name), "env")


def _flow_into(value, target: str, data, g, rg) -> None:
    """Add edges so *value*'s sources point at *target*."""
    vt = value.type
    if vt == "identifier":
        _add(g, _text(value, data), target, "alias")
        return
    sval = _string_value(value, data)
    if sval is not None:
        sn = str_node(sval)
        rg.string_values[sn] = sval
        _add(g, sn, target, "literal")
        return
    if vt == "new_expression":
        ctor = _child(value, "constructor")
        if ctor is not None and ctor.type == "identifier":
            _add(g, _text(ctor, data), target, "construct")
        return
    if vt == "call_expression":
        fn = _child(value, "function")
        args = _child(value, "arguments")
        if fn is not None and _text(fn, data) == "require" and args is not None:
            for a in args.named_children:
                s = _string_value(a, data)
                if s is not None:
                    sn = str_node(s)
                    rg.string_values[sn] = s
                    _add(g, sn, target, "require")
        elif fn is not None:
            for ident in _idents_in(value, data):
                _add(g, ident, target, "call-result")
        return
    if vt in ("binary_expression", "ternary_expression", "member_expression",
              "object", "array", "arguments"):
        for ident in _idents_in(value, data):
            _add(g, ident, target, "expr")
        for c in value.children:
            s = _string_value(c, data)
            if s is not None:
                sn = str_node(s)
                rg.string_values[sn] = s
                _add(g, sn, target, "literal")
        # object literal: values flow to the object name
        if vt == "object":
            for pair in value.named_children:
                if pair.type == "pair":
                    pv = _child(pair, "value")
                    if pv is not None:
                        for ident in _idents_in(pv, data):
                            _add(g, ident, target, "prop")


def _collect_exports(root, data, rg: ReferenceGraph) -> None:
    stack = [root]
    while stack:
        n = stack.pop()
        if n.type == "assignment_expression":
            left = _child(n, "left")
            right = _child(n, "right")
            if left is not None and right is not None and left.type == "member_expression":
                lo = _child(left, "object")
                lp = _child(left, "property")
                if (lo is not None and _text(lo, data) in ("module", "exports")
                        and lp is not None
                        and (_text(lo, data) == "exports" or _text(lp, data) == "exports")):
                    for ident in _idents_in(right, data):
                        rg.exported.add(ident)
        stack.extend(n.children)
