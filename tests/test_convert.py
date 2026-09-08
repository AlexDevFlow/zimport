import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

FIXTURE = Path(__file__).parent / "fixtures" / "notebook"
ROOT = Path(__file__).parent.parent


class EndToEnd(unittest.TestCase):
    def run_convert(self, extra=()):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = Path(tmp.name) / "vault"
        r = subprocess.run(
            [sys.executable, "-m", "zimport", str(FIXTURE), str(out), *extra],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        return out, r

    def test_pages_and_attachment_written(self):
        out, _ = self.run_convert()
        self.assertTrue((out / "Home.md").exists())
        self.assertTrue((out / "Meeting Notes.md").exists())
        self.assertTrue((out / "Projects" / "Foo.md").exists())
        self.assertTrue((out / "Projects" / "Foo" / "Bar.md").exists())
        self.assertTrue((out / "Projects" / "Foo" / "diagram.png").exists())

    def test_attachment_bytes_preserved(self):
        out, _ = self.run_convert()
        src = (FIXTURE / "Projects" / "Foo" / "diagram.png").read_bytes()
        dst = (out / "Projects" / "Foo" / "diagram.png").read_bytes()
        self.assertEqual(src, dst)

    def test_no_warnings_on_clean_notebook(self):
        _, r = self.run_convert()
        self.assertNotIn("warning:", r.stderr)

    def test_refuses_nonempty_vault(self):
        out, _ = self.run_convert()
        r = subprocess.run(
            [sys.executable, "-m", "zimport", str(FIXTURE), str(out)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 2)

    def test_dry_run_writes_nothing(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = Path(tmp.name) / "vault"
        r = subprocess.run(
            [sys.executable, "-m", "zimport", str(FIXTURE), str(out), "--dry-run"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(out.exists())


    def test_refuses_a_vault_inside_the_notebook(self):
        r = subprocess.run(
            [sys.executable, "-m", "zimport", str(FIXTURE), str(FIXTURE / "out")],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 2)
        self.assertIn("inside each other", r.stderr)


class HiddenFiles(unittest.TestCase):
    def test_dot_directories_are_not_pages(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        nb = Path(tmp.name) / "notebook"
        (nb / ".zim").mkdir(parents=True)
        (nb / ".zim" / "index.txt").write_text("not a page\n", encoding="utf-8")
        (nb / "notebook.zim").write_text("[Notebook]\nname=t\n", encoding="utf-8")
        (nb / "Real.txt").write_text(
            "Content-Type: text/x-zim-wiki\n\n====== Real ======\n", encoding="utf-8"
        )
        out = Path(tmp.name) / "vault"
        r = subprocess.run(
            [sys.executable, "-m", "zimport", str(nb), str(out)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((out / "Real.md").exists())
        self.assertFalse((out / ".zim").exists())
        self.assertIn("1 page(s)", r.stdout)


if __name__ == "__main__":
    unittest.main()
