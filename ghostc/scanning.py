"""Token-boundary leak scanning — shared by `ghostc verify` and the test suite.

`anchored_scan` is the one leak-scan primitive: non-overlapping, longest-needle-first,
bounded by ``[^A-Za-z0-9_]`` on both sides so short aliases like ``ip-a`` do not
substring-hit ``strip-ansi`` and nested spellings (``Northwind`` inside
``Northwind Airlines``) are counted once.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_SKIP_DIRS = (".git", "node_modules")


@dataclass(frozen=True)
class ScanHit:
    start: int
    end: int
    text: str          # the matched needle, verbatim from the corpus


def anchored_scan(corpus: str, needles: Iterable[str]) -> list[ScanHit]:
    """Every non-overlapping, token-boundary occurrence of any needle in *corpus*.

    At a shared position the longest needle wins (``re`` alternation is first-match,
    so needles are ordered longest-first).
    """
    uniq = sorted({n for n in needles if n}, key=len, reverse=True)
    if not uniq:
        return []
    rx = re.compile(
        r"(?<![A-Za-z0-9_])(" + "|".join(re.escape(n) for n in uniq) + r")(?![A-Za-z0-9_])"
    )
    return [ScanHit(m.start(1), m.end(1), m.group(1)) for m in rx.finditer(corpus)]


def iter_text_files(root: Path | str, skip_dirs: Iterable[str] = _DEFAULT_SKIP_DIRS
                    ) -> Iterator[tuple[str, str]]:
    """Yield ``(posix-relpath, text)`` for every UTF-8 file under *root*; skip binaries."""
    root = Path(root)
    skip = set(skip_dirs)
    for p in sorted(root.rglob("*")):
        if not p.is_file() or skip & set(p.relative_to(root).parts):
            continue
        try:
            yield p.relative_to(root).as_posix(), p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue


def _is_entry(obj: object) -> bool:
    return isinstance(obj, dict) and (
        {"real", "real_sha256"} <= obj.keys()
        or {"real", "ghost", "frozen"} <= obj.keys()
    )


def looks_like_mapping(text: str) -> bool:
    """True if *text* is a ghostc mapping store, one of its entries, or a slice of one.

    The mapping store holds real values in cleartext and must never be inside the ghost.
    """
    if "real_sha256" not in text and '"frozen"' not in text and "mapping_version" not in text:
        return False
    try:
        doc = json.loads(text)
    except (ValueError, TypeError):
        return "real_sha256" in text  # non-JSON file that mentions the field — flag it
    if isinstance(doc, dict):
        if "mapping_version" in doc or _is_entry(doc):
            return True
        entries = doc.get("entries")
        return isinstance(entries, list) and any(_is_entry(e) for e in entries)
    if isinstance(doc, list):
        return any(_is_entry(e) for e in doc)
    return False
