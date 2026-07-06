import unittest
from pathlib import Path

from zimport.model import Notebook
from zimport.markup import Converter

FIXTURE = Path(__file__).parent / "fixtures" / "notebook"


def convert(parts, text, **kw):
    nb = Notebook.load(FIXTURE)
    return Converter(nb, **kw).convert_page(parts, text)


def body(parts, text, **kw):
    """Convert a page snippet, skipping the header, and return the markdown."""
    src = (
        "Content-Type: text/x-zim-wiki\n"
        "Wiki-Format: zim 0.6\n"
        "Creation-Date: 2024-01-01T00:00:00+00:00\n\n" + text
    )
    md, stats = convert(parts, src, **kw)
    return md, stats


class Headings(unittest.TestCase):
    def test_levels(self):
        md, _ = body(("X",), "====== H1 ======\n===== H2 =====\n== H5 ==")
        self.assertIn("# H1", md)
        self.assertIn("## H2", md)
        self.assertIn("##### H5", md)

    def test_h1_not_confused_with_hr(self):
        md, _ = body(("X",), "------\ntext")
        self.assertIn("---\n", md)


class Inline(unittest.TestCase):
    def test_formatting(self):
        md, _ = body(("X",), "//i// **b** __m__ ~~s~~ ''v''")
        self.assertIn("*i*", md)
        self.assertIn("**b**", md)
        self.assertIn("==m==", md)
        self.assertIn("~~s~~", md)
        self.assertIn("`v`", md)

    def test_italic_ignores_urls(self):
        md, _ = body(("X",), "see http://example.com/a//b for details")
        self.assertIn("http://example.com/a//b", md)

    def test_sub_super(self):
        md, _ = body(("X",), "H_{2}O 2^{10}")
        self.assertIn("H<sub>2</sub>O", md)
        self.assertIn("2<sup>10</sup>", md)

    def test_tags(self):
        md, stats = body(("X",), "a @todo item")
        self.assertIn("#todo", md)
        self.assertIn("todo", stats.tags)

    def test_email_not_a_tag(self):
        md, _ = body(("X",), "reach me at sam@example.com please")
        self.assertNotIn("#example", md)
        self.assertIn("sam@example.com", md)


class Lists(unittest.TestCase):
    def test_bullets_and_nesting(self):
        md, _ = body(("X",), "* a\n\t* b\n* c")
        self.assertIn("- a", md)
        self.assertIn("    - b", md)

    def test_checkboxes(self):
        md, _ = body(("X",), "[ ] a\n[*] b\n[x] c\n[>] d")
        self.assertIn("- [ ] a", md)
        self.assertIn("- [x] b", md)
        self.assertIn("- [-] c", md)
        self.assertIn("- [>] d", md)

    def test_numbered(self):
        md, _ = body(("X",), "1. one\n2. two")
        self.assertIn("1. one", md)
        self.assertIn("2. two", md)


class Code(unittest.TestCase):
    def test_verbatim_block(self):
        md, _ = body(("X",), "'''\n**not bold**\n'''")
        self.assertIn("```\n**not bold**\n```", md)

    def test_code_object_language(self):
        md, _ = body(("X",), '{{{code: lang="python"\nx = 1\n}}}')
        self.assertIn("```python", md)
        self.assertIn("x = 1", md)


class LineEndings(unittest.TestCase):
    def test_crlf_notebook(self):
        src = (
            "Content-Type: text/x-zim-wiki\r\n"
            "Wiki-Format: zim 0.6\r\n\r\n"
            "====== T ======\r\n* a\r\n\t* b\r\n"
        )
        md, _ = convert(("X",), src)
        self.assertIn("# T", md)
        self.assertIn("    - b", md)
        self.assertNotIn("\r", md)


class Links(unittest.TestCase):
    def test_external(self):
        md, _ = body(("Home",), "[[https://obsidian.md|Obsidian]]")
        self.assertIn("[Obsidian](https://obsidian.md)", md)

    def test_resolves_to_unique_leaf(self):
        md, _ = body(("Home",), "[[Projects:Foo:Bar]]")
        self.assertIn("[[Bar]]", md)

    def test_alias(self):
        md, _ = body(("Home",), "[[Projects:Foo|the Foo page]]")
        self.assertIn("[[Foo|the Foo page]]", md)

    def test_spaced_name(self):
        md, _ = body(("Home",), "[[Meeting Notes]]")
        self.assertIn("[[Meeting Notes]]", md)

    def test_subpage_plus(self):
        md, _ = body(("Projects",), "[[+Foo]]")
        self.assertIn("[[Foo]]", md)

    def test_unresolved_reported(self):
        md, stats = body(("Home",), "[[Nowhere:Missing]]")
        self.assertTrue(stats.unresolved)


class Images(unittest.TestCase):
    def test_embed_with_width(self):
        md, stats = body(("Projects", "Foo"), "{{./diagram.png?width=320}}")
        self.assertIn("![[Projects/Foo/diagram.png|320]]", md)
        self.assertIn("Projects/Foo/diagram.png", stats.attachments)

    def test_external_image(self):
        md, _ = body(("X",), "{{https://example.com/a.png|alt}}")
        self.assertIn("![alt](https://example.com/a.png)", md)


if __name__ == "__main__":
    unittest.main()
