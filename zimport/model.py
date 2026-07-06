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
            parts = rel.with_suffix("").parts
            if not parts:
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

        # Zim resolves a plain link by walking up: try it under the current
        # page, then each ancestor namespace, then the root.
        base = tuple(current)
        while True:
            hit = self._find(base + comps)
            if hit is not None:
                return hit, True
            if not base:
                break
            base = base[:-1]
        # nothing matched: Zim would create it next to the current page
        return tuple(current[:-1]) + comps, False

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
