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

    attachments = copy_attachments(nb, vault, dry_run=args.dry_run)

    if not args.quiet:
        where = "would convert" if args.dry_run else "converted"
        print(f"{where} {pages_written} page(s), copied {attachments} attachment(s)")
    missing = referenced - _existing_attachment_set(nb)
    if missing and not args.quiet:
        print(f"warning: {len(missing)} embedded file(s) not found in the notebook", file=sys.stderr)
        for m in sorted(missing)[:10]:
            print(f"  missing: {m}", file=sys.stderr)
    if unresolved and not args.quiet:
        print(f"warning: {len(unresolved)} link(s) had no matching page", file=sys.stderr)
        for src, href in unresolved[:10]:
            print(f"  {src} -> {href}", file=sys.stderr)
    return 0


def copy_attachments(nb: Notebook, vault: Path, dry_run: bool) -> int:
    """Copy every non-page file into the vault, decoding directory names."""
    count = 0
    for f in sorted(nb.root.rglob("*")):
        if f.is_dir() or f.suffix == ".txt" or f.name == "notebook.zim":
            continue
        if any(part.startswith(".") for part in f.relative_to(nb.root).parts):
            continue
        rel = f.relative_to(nb.root)
        vault_parts = [decode_name(p, nb.keep_underscores) for p in rel.parts[:-1]]
        dest = vault.joinpath(*vault_parts, rel.name)
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
        count += 1
    return count


def _existing_attachment_set(nb: Notebook) -> set[str]:
    out: set[str] = set()
    for f in nb.root.rglob("*"):
        if f.is_dir() or f.suffix == ".txt" or f.name == "notebook.zim":
            continue
        rel = f.relative_to(nb.root)
        if any(p.startswith(".") for p in rel.parts):
            continue
        dirs = [decode_name(p, nb.keep_underscores) for p in rel.parts[:-1]]
        out.add("/".join(dirs + [rel.name]))
    return out


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
