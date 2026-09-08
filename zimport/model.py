"""Discovering the pages in a Zim notebook and resolving links between them.

A Zim notebook is a directory tree of ``.txt`` files. A page called ``Foo`` is
stored as ``Foo.txt``; its child pages live in a sibling directory ``Foo/``. So
``Projects/Foo/Bar.txt`` is the page ``Projects:Foo:Bar`` in Zim's own notation.
Spaces in a page name are written as underscores on disk.

This module walks that tree, and knows how to turn a Zim link (which can be
absolute, relative, or a bare name that Zim resolves by walking up the tree)
into a path we can point an Obsidian wikilink at.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


ZIM_HEADER = "Content-Type: text/x-zim-wiki"


def is_page_file(path: Path) -> bool:
    """Whether Zim would treat this .txt file as a page.

    Zim wants its own header on the first line, and it stores a page name by
    writing spaces as underscores, so a name that still has a space in it
    never came from Zim. Everything else in the tree is just a file sitting
    next to a page -- a text attachment, most often -- and gets copied across
    rather than converted.
    """
    if " " in path.name:
        return False
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
            return fh.readline(60).strip() == ZIM_HEADER
    except OSError:
        return False


def decode_name(part: str, keep_underscores: bool = False) -> str:
    """On-disk name segment to display name. Zim writes spaces as underscores."""
    if keep_underscores:
        return part
    return part.replace("_", " ")


@dataclass
class Page:
    parts: tuple[str, ...]        # raw on-disk namespace, e.g. ("Projects", "Foo")
    source: Path                  # the .txt file

    @property
    def name(self) -> str:
        return self.parts[-1]


@dataclass
class Notebook:
    root: Path
    keep_underscores: bool = False
    pages: dict[tuple[str, ...], Page] = field(default_factory=dict)
    _leaf_counts: dict[str, int] = field(default_factory=dict)
    _norm_index: dict[tuple[str, ...], tuple[str, ...]] = field(default_factory=dict)

    @classmethod
    def load(cls, root: Path, keep_underscores: bool = False) -> "Notebook":
        nb = cls(root=root, keep_underscores=keep_underscores)
        for txt in sorted(root.rglob("*.txt")):
            rel = txt.relative_to(root)
            # Zim keeps its index and per-notebook state in dot-directories;
            # those aren't pages.
            if any(p.startswith(".") for p in rel.parts):
                continue
            parts = rel.with_suffix("").parts
            if not parts or not is_page_file(txt):
                continue
            nb.pages[parts] = Page(parts=parts, source=txt)
        for parts in nb.pages:
            leaf = decode_name(parts[-1], keep_underscores).lower()
            nb._leaf_counts[leaf] = nb._leaf_counts.get(leaf, 0) + 1
            nb._norm_index[_normalize(parts)] = parts
        return nb

    def has_notebook_config(self) -> bool:
        return (self.root / "notebook.zim").exists()

    # -- output paths ------------------------------------------------------

    def vault_parts(self, parts: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(decode_name(p, self.keep_underscores) for p in parts)

    def vault_relpath(self, parts: tuple[str, ...]) -> Path:
        vp = self.vault_parts(parts)
        return Path(*vp).with_suffix(".md")

    def leaf_is_unique(self, parts: tuple[str, ...]) -> bool:
        leaf = decode_name(parts[-1], self.keep_underscores).lower()
        return self._leaf_counts.get(leaf, 0) <= 1

    # -- link resolution ---------------------------------------------------

    def resolve(
        self, current: tuple[str, ...], href: str
    ) -> tuple[tuple[str, ...], bool]:
        """Resolve a Zim page href against the page ``current`` is on.

        Returns the target namespace parts and whether a page actually exists
        there. ``current`` is the linking page's own parts (its leaf included).
        """
        href = href.strip()
        if href.startswith(":"):
            # absolute from notebook root
            return self._lookup(tuple(_split(href[1:])), tuple(_split(href[1:])))
        if href.startswith("+"):
            # child of the current page
            comps = tuple(_split(href[1:]))
            fallback = tuple(current) + comps
            return self._lookup(fallback, fallback)

        comps = tuple(_split(href))
        if not comps:
            return current, True
        return self._resolve_floating(tuple(current), comps)

    def _resolve_floating(
        self, current: tuple[str, ...], comps: tuple[str, ...]
    ) -> tuple[tuple[str, ...], bool]:
        """Resolve a link written as a plain name, the way Zim does.

        Zim matches the link's *first* name against the pages it knows, then
        hangs the rest of the link off whatever that matched. A candidate has
        to sit at or above the linking page's own depth -- a plain name never
        reaches down into a child, which is what ``[[+child]]`` is for -- and
        it has to share an ancestor with the linking page. Of those, the
        deepest wins, so a sibling beats a page of the same name at the root.
        """
        anchor = _normalize((comps[0],))[0]
        here = _normalize(current)
        maxdepth = len(current) - 1

        best: list[tuple[str, ...]] = []
        best_depth = -1
        for parts in self.pages:
            if _normalize((parts[-1],))[0] != anchor:
                continue
            depth = len(parts) - 1
            if depth > maxdepth or depth < best_depth:
                continue
            if depth > 0 and here[: depth] != _normalize(parts[:-1]):
                continue  # not on the linking page's own branch
            if depth > best_depth:
                best, best_depth = [parts], depth
            else:
                best.append(parts)

        if best:
            # Zim prefers a candidate whose name matches letter for letter.
            exact = [p for p in best if p[-1] == comps[0]]
            pick = (exact or sorted(best, reverse=True))[0]
            return self._lookup(pick + comps[1:], pick + comps[1:])

        # Nothing matched, so Zim puts the page next to the linking one.
        return current[:-1] + comps, False

    def _find(self, parts: tuple[str, ...]) -> tuple[str, ...] | None:
        """Look parts up ignoring underscore/space and case; return real parts."""
        if parts in self.pages:
            return parts
        return self._norm_index.get(_normalize(parts))

    def _lookup(
        self, ideal: tuple[str, ...], fallback: tuple[str, ...]
    ) -> tuple[tuple[str, ...], bool]:
        hit = self._find(ideal)
        if hit is not None:
            return hit, True
        return fallback, False

    def wikilink_target(self, parts: tuple[str, ...]) -> str:
        """Shortest Obsidian link target: bare leaf if unique, else full path."""
        if self.leaf_is_unique(parts):
            return decode_name(parts[-1], self.keep_underscores)
        vp = self.vault_parts(parts)
        return "/".join(vp)


def _split(path: str) -> list[str]:
    return [p for p in path.split(":") if p]


def _normalize(parts: tuple[str, ...]) -> tuple[str, ...]:
    """Fold underscore/space and case so link text matches on-disk names."""
    return tuple(p.replace("_", " ").strip().lower() for p in parts)
