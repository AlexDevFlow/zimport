"""Turning a single Zim page into Obsidian-flavoured Markdown.

The conversion is line based. Most of Zim's block markup (headings, lists,
checkboxes, code fences) is decided by the start of a line, so we walk the page
top to bottom holding a little state for code blocks. Inline markup (bold,
links, images, ...) is handled separately, protecting links and verbatim spans
before the formatting rules run so we don't reformat inside them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .model import Notebook, decode_name

# Zim checkbox states -> Markdown task markers. Obsidian core only cares whether
# the box is empty, but the extra markers ([-], [>], [<]) survive round trips
# and render distinctly under the common task themes/plugins.
_BOX = {" ": " ", "*": "x", "x": "-", "X": "-", ">": ">", "<": "<"}

_HEADING = re.compile(r"^(={2,7})(.*?)=*\s*$")
_HR = re.compile(r"^-{5,}\s*$")
_BULLET = re.compile(r"^([*•])\s+(.*)$")
_CHECKBOX = re.compile(r"^\[([ *xX><])\]\s+(.*)$")
_NUMBERED = re.compile(r"^(\d+|[a-zA-Z])[.)]\s+(.*)$")
_CODE_OBJ = re.compile(r"^\s*\{\{\{(?:code:)?(.*)$")
_LANG = re.compile(r'lang="([^"]+)"')

_PROTECT = re.compile(r"\{\{.*?\}\}|\[\[.*?\]\]|''.*?''")
_TAG = re.compile(r"(?<![\w/#])@([A-Za-z][\w\-]*)")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://")


@dataclass
class PageStats:
    tags: set[str] = field(default_factory=set)
    creation_date: str | None = None
    links: int = 0
    unresolved: list[str] = field(default_factory=list)
    attachments: set[str] = field(default_factory=set)  # posix paths in vault


class Converter:
    def __init__(self, notebook: Notebook, frontmatter: bool = False):
        self.nb = notebook
        self.frontmatter = frontmatter

    def convert_page(self, parts: tuple[str, ...], text: str) -> tuple[str, PageStats]:
        stats = PageStats()
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        body, stats.creation_date = _strip_header(text)
        out: list[str] = []
        in_code = False
        code_obj = False
        in_list = False
        for raw in body.split("\n"):
            if code_obj:
                if raw.strip() == "}}}":
                    out.append("```")
                    code_obj = False
                else:
                    out.append(raw)
                continue
            if in_code:
                if raw.strip() == "'''":
                    out.append("```")
                    in_code = False
                else:
                    out.append(raw)
                continue
            if raw.strip() == "'''":
                out.append("```")
                in_code = True
                continue
            m = _CODE_OBJ.match(raw)
            if m:
                lang = _LANG.search(m.group(1))
                out.append("```" + (lang.group(1) if lang else ""))
                code_obj = True
                continue
            line, in_list = self._line(parts, raw, stats, in_list)
            out.append(line)

        md = "\n".join(out)
        if self.frontmatter and (stats.creation_date or stats.tags):
            md = _frontmatter(stats) + md
        return md, stats

    # -- block level -------------------------------------------------------

    def _line(
        self, parts: tuple[str, ...], line: str, stats: PageStats, in_list: bool
    ) -> tuple[str, bool]:
        """Convert one body line. Returns the line and whether a list is open.

        ``in_list`` matters for indentation: four spaces continue a list item,
        but in front of an ordinary paragraph they would make Obsidian render
        it as a code block.
        """
        indent = 0
        while indent < len(line) and line[indent] == "\t":
            indent += 1
        stripped = line[indent:]
        pad = "    " * indent

        if not stripped.strip():
            return "", in_list

        h = _HEADING.match(stripped)
        if h:
            level = max(1, min(6, 7 - len(h.group(1))))
            title = self._inline(parts, h.group(2).strip(), stats)
            return pad + "#" * level + " " + title, False
        if _HR.match(stripped):
            return pad + "---", False

        c = _CHECKBOX.match(stripped)
        if c:
            box = _BOX.get(c.group(1), " ")
            return f"{pad}- [{box}] " + self._inline(parts, c.group(2), stats), True
        b = _BULLET.match(stripped)
        if b:
            return f"{pad}- " + self._inline(parts, b.group(2), stats), True
        n = _NUMBERED.match(stripped)
        if n:
            num = n.group(1) if n.group(1).isdigit() else "1"
            return f"{pad}{num}. " + self._inline(parts, n.group(2), stats), True

        if indent and not in_list:
            pad = _soft_indent(indent)
        return pad + self._inline(parts, stripped, stats), in_list

    # -- inline ------------------------------------------------------------

    def _inline(self, parts: tuple[str, ...], text: str, stats: PageStats) -> str:
        held: list[str] = []

        def protect(m: re.Match) -> str:
            s = m.group(0)
            if s.startswith("{{"):
                repl = self._image(parts, s[2:-2], stats)
            elif s.startswith("[["):
                repl = self._link(parts, s[2:-2], stats)
            else:  # ''verbatim''
                repl = "`" + s[2:-2] + "`"
            held.append(repl)
            return f"\x00{len(held) - 1}\x00"

        text = _PROTECT.sub(protect, text)

        text = re.sub(r"\^\{(.+?)\}", r"<sup>\1</sup>", text)
        text = re.sub(r"_\{(.+?)\}", r"<sub>\1</sub>", text)
        text = re.sub(r"(?<!:)//(.+?)//", r"*\1*", text)
        text = re.sub(r"__(.+?)__", r"==\1==", text)

        def tag(m: re.Match) -> str:
            stats.tags.add(m.group(1))
            return "#" + m.group(1)

        text = _TAG.sub(tag, text)

        text = re.sub(r"\x00(\d+)\x00", lambda m: held[int(m.group(1))], text)
        return text

    def _link(self, parts: tuple[str, ...], inner: str, stats: PageStats) -> str:
        stats.links += 1
        href, _, disp = inner.partition("|")
        href = href.strip()
        disp = disp.strip() or None

        if _SCHEME.match(href) or href.startswith(("mailto:", "tel:")):
            return f"[{disp or href}]({href})"
        if href.startswith(("./", "../", "/", "~", "file:")):
            return f"[{disp or href}]({href})"

        target, _, anchor = href.partition("#")
        if not target:  # link within the same page
            label = f"|{disp}" if disp else ""
            return f"[[#{anchor}{label}]]"

        resolved, exists = self.nb.resolve(parts, target)
        if not exists:
            # No page behind it. Write the full path so the dead link stays
            # where Zim would have put the page, instead of shortening to a
            # bare name that Obsidian would attach to some unrelated note.
            stats.unresolved.append(href)
            link = "/".join(self.nb.vault_parts(resolved))
        else:
            link = self.nb.wikilink_target(resolved)
        if anchor:
            link += "#" + anchor
        leaf = decode_name(resolved[-1], self.nb.keep_underscores)
        if disp and disp != leaf:
            return f"[[{link}|{disp}]]"
        return f"[[{link}]]"

    def _image(self, parts: tuple[str, ...], inner: str, stats: PageStats) -> str:
        src, _, alt = inner.partition("|")
        alt = alt.strip()
        path, _, query = src.strip().partition("?")
        width = ""
        wm = re.search(r"width=(\d+)", query)
        if wm:
            width = "|" + wm.group(1)

        if _SCHEME.match(path) or path.startswith(("file:", "/")):
            return f"![{alt}]({path})"

        # Attachments live in the folder named after the page, so "./x.png" is
        # that folder and each "../" steps one page up.
        fname = path
        up = 0
        while True:
            if fname.startswith("../"):
                fname = fname[3:]
                up += 1
            elif fname.startswith("./"):
                fname = fname[2:]
            else:
                break
        base = list(self.nb.vault_parts(parts))
        while up and base:
            base.pop()
            up -= 1
        embed = "/".join(base + [fname])
        stats.attachments.add(embed)
        return f"![[{embed}{width}]]"


def _soft_indent(level: int) -> str:
    """Indent for a paragraph outside a list: visible, but under the four
    spaces that would turn it into a code block."""
    return " " * min(3, 2 * level)


def _strip_header(text: str) -> tuple[str, str | None]:
    lines = text.split("\n")
    created = None
    i = 0
    if lines and re.match(r"^Content-Type:\s", lines[0]):
        while i < len(lines) and lines[i].strip():
            m = re.match(r"^Creation-Date:\s*(.+)$", lines[i])
            if m:
                created = m.group(1).strip()
            i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
    return "\n".join(lines[i:]), created


def _frontmatter(stats: PageStats) -> str:
    rows = ["---"]
    if stats.creation_date:
        rows.append(f"created: {_yaml_scalar(stats.creation_date)}")
    if stats.tags:
        rows.append("tags:")
        for t in sorted(stats.tags):
            rows.append(f"  - {t}")
    rows.append("---")
    rows.append("")
    rows.append("")
    return "\n".join(rows)


def _yaml_scalar(value: str) -> str:
    """Quote a frontmatter value if it would otherwise confuse a YAML parser."""
    if not value:
        return '""'
    if value[0] in "-?:,[]{}#&*!|>'\"%@`" or ": " in value or " #" in value:
        return "'" + value.replace("'", "''") + "'"
    return value
