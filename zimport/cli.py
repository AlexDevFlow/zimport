"""Command-line entry point: convert a Zim notebook into an Obsidian vault."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .model import Notebook, decode_name
from .markup import Converter


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="zimport",
        description="Convert a Zim Desktop Wiki notebook into an Obsidian vault.",
    )
    p.add_argument("notebook", type=Path, help="the Zim notebook directory")
    p.add_argument("vault", type=Path, help="output directory for the Obsidian vault")
    p.add_argument(
        "--frontmatter",
        action="store_true",
        help="add YAML frontmatter with the page's creation date and tags",
    )
    p.add_argument(
        "--keep-underscores",
        action="store_true",
        help="keep underscores in names instead of turning them back into spaces",
    )
    p.add_argument(
        "--overwrite",
        action="store_true",
        help="write into the vault directory even if it already has files",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be written without touching the disk",
    )
    p.add_argument("-q", "--quiet", action="store_true", help="only print warnings")
    return p


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    nb_root: Path = args.notebook
    vault: Path = args.vault

    if not nb_root.is_dir():
        print(f"zimport: {nb_root} is not a directory", file=sys.stderr)
        return 2
    if _nested(nb_root, vault):
        print(
            "zimport: the notebook and the vault must not sit inside each other",
            file=sys.stderr,
        )
        return 2
    if vault.exists() and any(vault.iterdir()) and not args.overwrite and not args.dry_run:
        print(
            f"zimport: {vault} is not empty (use --overwrite to write into it)",
            file=sys.stderr,
        )
        return 2

    nb = Notebook.load(nb_root, keep_underscores=args.keep_underscores)
    if not nb.has_notebook_config() and not args.quiet:
        print(
            f"zimport: no notebook.zim in {nb_root}; treating it as a page tree anyway",
            file=sys.stderr,
        )
    if not nb.pages:
        print(f"zimport: no .txt pages found under {nb_root}", file=sys.stderr)
        return 1

    conv = Converter(nb, frontmatter=args.frontmatter)
    pages_written = 0
    unresolved: list[tuple[str, str]] = []
    referenced: set[str] = set()

    for parts, page in nb.pages.items():
        text = page.source.read_text(encoding="utf-8-sig", errors="replace")
        md, stats = conv.convert_page(parts, text)
        dest = vault / nb.vault_relpath(parts)
        referenced |= stats.attachments
        for href in stats.unresolved:
            unresolved.append((":".join(parts), href))
        if not args.dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(md, encoding="utf-8")
        pages_written += 1

    found = attachment_files(nb)
    attachments = copy_attachments(found, vault, dry_run=args.dry_run)

    if not args.quiet:
        where = "would convert" if args.dry_run else "converted"
        print(f"{where} {pages_written} page(s), copied {attachments} attachment(s)")
    missing = referenced - set(found)
    if missing and not args.quiet:
        print(f"warning: {len(missing)} embedded file(s) not found in the notebook", file=sys.stderr)
        for m in sorted(missing)[:10]:
            print(f"  missing: {m}", file=sys.stderr)
    if unresolved and not args.quiet:
        print(f"warning: {len(unresolved)} link(s) had no matching page", file=sys.stderr)
        for src, href in unresolved[:10]:
            print(f"  {src} -> {href}", file=sys.stderr)
    return 0


def attachment_files(nb: Notebook) -> dict[str, Path]:
    """Every non-page file in the notebook, keyed by its path in the vault.

    The key is what an embed in a converted page points at, so the caller can
    both copy the files and tell which embeds have nothing behind them.
    """
    out: dict[str, Path] = {}
    for f in sorted(nb.root.rglob("*")):
        if f.is_dir() or f.suffix == ".txt" or f.name == "notebook.zim":
            continue
        rel = f.relative_to(nb.root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        dirs = [decode_name(p, nb.keep_underscores) for p in rel.parts[:-1]]
        out["/".join(dirs + [rel.name])] = f
    return out


def copy_attachments(found: dict[str, Path], vault: Path, dry_run: bool) -> int:
    """Copy the notebook's non-page files into their place in the vault."""
    for vault_path, src in found.items():
        if dry_run:
            continue
        dest = vault.joinpath(*vault_path.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    return len(found)


def _nested(a: Path, b: Path) -> bool:
    """True if either directory sits inside the other (or they're the same)."""
    ra, rb = a.resolve(), b.resolve()
    return ra == rb or ra in rb.parents or rb in ra.parents


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
