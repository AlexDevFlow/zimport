# zimport

[![tests](https://github.com/AlexDevFlow/zimport/actions/workflows/tests.yml/badge.svg)](https://github.com/AlexDevFlow/zimport/actions/workflows/tests.yml)

Convert a [Zim Desktop Wiki](https://zim-wiki.org) notebook into an
[Obsidian](https://obsidian.md) vault.

It reads the notebook's `.txt` files directly, so you don't need Zim installed
or any intermediate export step. Point it at your notebook folder and an empty
output folder, and you get a vault of Markdown files with the links, tags,
checkboxes and attachments carried across.

## Install

With pipx (keeps it in its own environment):

```
pipx install git+https://github.com/AlexDevFlow/zimport.git
```

Or with pip:

```
pip install git+https://github.com/AlexDevFlow/zimport.git
```

Or run it straight from a clone, no install needed (it only uses the standard
library, Python 3.9 or newer):

```
python3 -m zimport NOTEBOOK VAULT
```

## Use

```
zimport ~/Notebooks/personal ~/ObsidianVault
```

The first argument is the Zim notebook (the folder with `notebook.zim` in it).
The second is where the vault should go. It won't write into a folder that
already has files unless you pass `--overwrite`.

Options:

- `--frontmatter` adds a YAML block to each note with its creation date and any
  tags found on the page.
- `--keep-underscores` leaves underscores in names alone. By default a page
  saved as `My_Page.txt` becomes `My Page.md`, matching how Zim shows it.
- `--dry-run` reports what it would do without writing anything.
- `--overwrite` writes into a non-empty vault folder.
- `-q`, `--quiet` prints warnings only.

When it finishes it prints how many pages and attachments it handled, and warns
about links that didn't match a page or embedded files it couldn't find.

## What it converts

| Zim | Obsidian |
| --- | --- |
| `====== Head ======` down to `== Head ==` | `#` down to `#####` |
| `**bold**` `//italic//` `~~strike~~` | `**bold**` `*italic*` `~~strike~~` |
| `__mark__` | `==mark==` (highlight) |
| `''code''` and `'''` blocks | `` `code` `` and fenced blocks |
| `{{{code: lang="python" ...}}}` | fenced block with the language |
| `[ ] [*] [x] [>]` checkboxes | `- [ ] - [x] - [-] - [>]` tasks |
| `* item` bullets, `1.` and `a)` lists | `- item`, numbered list |
| `H_{2}O`, `x^{2}` | `H<sub>2</sub>O`, `x<sup>2</sup>` |
| `@tag` | `#tag` |
| `{{./image.png?width=300}}` | `![[image.png\|300]]` |
| `[[Page]]`, `[[a:b:c]]`, `[[+child]]`, `[[:top]]` | `[[Page]]` |
| `[[http://...\|text]]` | `[text](http://...)` |

Internal links are the fiddly part. Zim lets you write a link relative to the
current page and resolves it by walking up the tree, so the same text can mean
different pages depending on where it sits. zimport resolves each link the way
Zim would, then writes the shortest Obsidian link that still points at the right
note: just the page name where that's unique in the vault, or the full path
where it isn't.

Attachments live next to the page in Zim (in a folder named after it). Those get
copied into the vault at the matching place, and the embeds are rewritten to
point at them, including the ones written relative to a parent page
(`{{../shared.png}}`). Zim's own dot-folders, like the `.zim` index cache, are
left behind.

## What it doesn't do

- Zim's `@date` journal calendar isn't treated specially; those pages come
  across as ordinary notes.
- Obsidian's core checkbox rendering only knows "done" and "not done". The extra
  states (`[-]` cancelled, `[>]` forwarded) survive in the text and show up
  distinctly if you use a task plugin or a theme that styles them, but plain
  Obsidian treats them as done.
- A bare `@word` in running text becomes a `#tag`. If you have those and don't
  want them as tags, check the result.
- Zim indents with tabs, and Markdown reads four leading spaces as a code block.
  Indented lines under a list item keep their indent, since that's a list
  continuation; an indented paragraph on its own gets a shallower indent instead,
  so it still reads as a paragraph rather than turning into code.
- Lettered lists (`a)`, `b)`) become an ordinary numbered list; Markdown has no
  letter counter.

## Tests

```
python3 -m unittest discover -s tests
```

The tests run a sample notebook through the converter and check the markup, the
link resolution and the attachment copying. They only need the standard library.

## License

MIT.
