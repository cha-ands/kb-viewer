import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from kbviewer.notes import NotesStore, parse, serialize
from kbviewer.paths import PathError, safe_resolve
from kbviewer.search import SearchIndex
from kbviewer.tree import build_tree

FIXTURE = Path(__file__).parent / "fixtures" / "kb"


class PathsTest(unittest.TestCase):
    def test_inside(self):
        self.assertEqual(safe_resolve(FIXTURE, "concepts/auth/index.md"),
                         (FIXTURE / "concepts/auth/index.md").resolve())

    def test_escape_rejected(self):
        for bad in ["../x", "concepts/../../x", "..\\..\\x"]:
            with self.assertRaises(PathError):
                safe_resolve(FIXTURE, bad)


class TreeTest(unittest.TestCase):
    def test_nested_depth(self):
        t = build_tree(FIXTURE)
        concepts = next(c for c in t["children"] if c["name"] == "concepts")
        auth = next(c for c in concepts["children"] if c["name"] == "auth")
        oauth = next(c for c in auth["children"] if c["name"] == "oauth")
        flows = next(c for c in oauth["children"] if c["name"] == "flows")
        self.assertEqual(auth["index"], "concepts/auth/index.md")
        self.assertEqual({c["name"] for c in flows["children"]}, {"authorization-code", "refresh-token"})

    def test_folder_named_index(self):
        t = build_tree(FIXTURE)
        storage = next(c for c in t["children"][0]["children"] if c["name"] == "storage")
        self.assertEqual(storage["index"], "concepts/storage/storage.md")

    def test_assets_only_folder_hidden(self):
        t = build_tree(FIXTURE)
        self.assertNotIn("assets", [c["name"] for c in t["children"]])


class NotesTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.store = NotesStore(self.dir / "NOTES.md")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_add_toggle_delete(self):
        now = datetime(2026, 10, 26, 14, 2)
        n = self.store.add("a/b.md", "Fix intro\nsecond line", now)
        self.store.add("c.md", "Other")
        text = (self.dir / "NOTES.md").read_text(encoding="utf-8")
        self.assertIn("## a/b.md\n- [ ] 2026-10-26 14:02 — Fix intro\n  second line", text)
        self.store.set_done("a/b.md", n["id"], True)
        self.assertTrue(self.store.list("a/b.md")[0]["done"])
        self.assertEqual(self.store.counts(), {"c.md": 1})
        self.store.delete("a/b.md", n["id"])
        self.assertEqual(self.store.list("a/b.md"), [])
        self.assertNotIn("## a/b.md", (self.dir / "NOTES.md").read_text(encoding="utf-8"))

    def test_roundtrip_preserves_manual_lines(self):
        src = ("# KB Review Notes\n\nSome intro text.\n\n## x.md\n"
               "- [ ] 2026-01-01 10:00 — one\n  more\n- [x] no stamp\nfree text line\n")
        pre, sections = parse(src)
        self.assertEqual(pre, ["Some intro text."])
        self.assertEqual(sections["x.md"][0].text, "one\nmore")
        self.assertEqual(sections["x.md"][1].stamp, "")
        self.assertEqual(serialize(pre, sections), src)

    def test_edit_text(self):
        n = self.store.add("a.md", "old")
        e = self.store.edit("a.md", n["id"], "new")
        self.assertEqual(self.store.list("a.md")[0]["text"], "new")
        self.assertNotEqual(e["id"], n["id"])

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            self.store.add("a.md", "   ")


class SearchTest(unittest.TestCase):
    def test_finds_nested(self):
        r = SearchIndex(FIXTURE).search("rotation")
        self.assertEqual(r[0]["path"], "concepts/auth/oauth/flows/refresh-token.md")
        self.assertEqual(r[0]["title"], "Refresh Token")

    def test_frontmatter_title(self):
        r = SearchIndex(FIXTURE).search("authorization framework")
        self.assertEqual(r[0]["title"], "OAuth 2.0")


if __name__ == "__main__":
    unittest.main()
