import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from kbviewer.server import App, make_server

FIXTURE = Path(__file__).parent / "fixtures" / "kb"


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.srv = make_server(App(FIXTURE, cls.tmp / "NOTES.md"), port=0)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        shutil.rmtree(cls.tmp)

    def req(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.base + path, data=data, method=method,
                                   headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.read()

    def get_json(self, path):
        s, b = self.req("GET", path)
        self.assertEqual(s, 200, b)
        return json.loads(b)

    def test_tree(self):
        d = self.get_json("/api/tree")
        self.assertEqual(d["tree"]["index"], "index.md")

    def test_page(self):
        d = self.get_json("/api/page?path=concepts/auth/oauth/flows/refresh-token.md")
        self.assertIn("Rotation", d["text"])

    def test_page_escape(self):
        s, _ = self.req("GET", "/api/page?path=../../test_core.py")
        self.assertEqual(s, 403)

    def test_kb_asset_and_static(self):
        s, b = self.req("GET", "/kb/assets/dot.svg")
        self.assertEqual(s, 200)
        self.assertIn(b"<svg", b)
        s, b = self.req("GET", "/")
        self.assertEqual(s, 200)
        self.assertIn(b"<html", b)

    def test_search(self):
        d = self.get_json("/api/search?q=pkce")
        self.assertEqual(d[0]["path"], "concepts/auth/oauth/flows/authorization-code.md")

    def test_notes_crud(self):
        p = "concepts/auth/sessions.md"
        s, b = self.req("POST", "/api/notes", {"path": p, "text": "Add CSRF section"})
        self.assertEqual(s, 201)
        nid = json.loads(b)["id"]
        self.assertEqual(self.get_json("/api/tree")["counts"], {p: 1})
        s, _ = self.req("PATCH", "/api/notes", {"path": p, "id": nid, "done": True})
        self.assertEqual(s, 200)
        self.assertTrue(self.get_json(f"/api/notes?path={p}")[0]["done"])
        s, _ = self.req("DELETE", "/api/notes", {"path": p, "id": nid})
        self.assertEqual(s, 200)
        self.assertEqual(self.get_json(f"/api/notes?path={p}"), [])
        s, _ = self.req("DELETE", "/api/notes", {"path": p, "id": "nope"})
        self.assertEqual(s, 404)


if __name__ == "__main__":
    unittest.main()
