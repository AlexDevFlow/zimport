#!/usr/bin/env python3
"""Check zimport's link resolution against Zim's own.

Zim decides where a link points using its page index, and the rules are
fiddly enough that reading the documentation is not the same as matching the
behaviour. This script asks both implementations the same question -- for
every page in a notebook, resolve every other page name in each of the link
forms Zim understands -- and reports any answer they disagree on.

It needs Zim's Python package importable. Zim ships one, so the usual way to
run this is with the interpreter from a Zim install:

    path/to/zim/python3 tools/compare_with_zim.py NOTEBOOK

It is not part of the test suite, because it needs Zim on the machine.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import zim.newfs
    from zim.notebook import build_notebook, Path as ZimPath
    from zim.notebook.page import HRef
except ImportError:
    sys.exit(
        "could not import zim -- run this with the Python interpreter from a "
        "Zim installation, or with Zim's package on PYTHONPATH"
    )

from zimport.model import Notebook


def link_forms(pagename: str) -> list[str]:
    leaf = pagename.split(":")[-1]
    return [leaf, pagename, ":" + pagename, "+" + leaf]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        return int(bool(print(__doc__.strip())))
    notebook_dir = Path(argv[1]).resolve()  # Zim insists on an absolute path

    zim_nb, _ = build_notebook(zim.newfs.LocalFolder(str(notebook_dir)))
    zim_nb.index.check_and_update()
    ours = Notebook.load(notebook_dir)

    names = sorted(":".join(p).replace("_", " ") for p in ours.pages)
    missing = {p.name for p in zim_nb.pages.walk()} ^ set(names)
    if missing:
        print("the two disagree on which files are pages:")
        for name in sorted(missing):
            print("   ", name)

    agree, disagree = 0, []
    for source in names:
        hrefs = [h for name in names for h in link_forms(name)]
        hrefs += ["Ghost", "Ghost:Deeper", ":Ghost", "+Ghost"]
        for href in hrefs:
            theirs = zim_nb.pages.resolve_link(
                ZimPath(source), HRef.new_from_wiki_link(href)
            ).name
            parts, _ = ours.resolve(tuple(source.replace(" ", "_").split(":")), href)
            mine = ":".join(parts).replace("_", " ")
            if theirs == mine:
                agree += 1
            else:
                disagree.append((source, href, theirs, mine))

    print(f"{agree + len(disagree)} link resolutions compared")
    print(f"agree:    {agree}")
    print(f"disagree: {len(disagree)}")
    for source, href, theirs, mine in disagree:
        print(f"   from {source}  [[{href}]]  zim={theirs}  zimport={mine}")
    return 1 if disagree or missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
