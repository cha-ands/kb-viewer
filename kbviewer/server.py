import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .notes import NotesStore
from .paths import PathError, safe_resolve
from .search import SearchIndex, page_title
from .tree import build_tree

STATIC = Path(__file__).resolve().parent.parent / "static"


class App:
    def __init__(self, root: Path, notes_file: Path = None):
        self.root = Path(root).resolve()
        self.notes_file = Path(notes_file).resolve() if notes_file else self.root / "NOTES.md"
        self.exclude = (self.notes_file,)
        self.notes = NotesStore(self.notes_file)
        self.index = SearchIndex(self.root, self.exclude)


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        # --- helpers ---
        def _json(self, data, status=200):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _error(self, status, msg):
            self._json({"error": msg}, status)

        def _file(self, path: Path):
            if not path.is_file():
                return self._error(404, "not found")
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def _dispatch(self, method):
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path.startswith("/api/"):
                    return self._api(method, url.path[5:], q)
                if method != "GET":
                    return self._error(405, "method not allowed")
                if url.path.startswith("/kb/"):
                    return self._file(safe_resolve(app.root, unquote(url.path[4:])))
                rel = unquote(url.path).lstrip("/") or "index.html"
                return self._file(safe_resolve(STATIC, rel))
            except PathError as e:
                self._error(403, str(e))
            except KeyError as e:
                self._error(404, f"not found: {e}")
            except ValueError as e:
                self._error(400, str(e))

        # --- api ---
        def _api(self, method, route, q):
            if route == "tree" and method == "GET":
                return self._json({
                    "root": app.root.name,
                    "notesFile": app.notes_file.name,
                    "tree": build_tree(app.root, app.exclude),
                    "counts": app.notes.counts(),
                })
            if route == "page" and method == "GET":
                p = safe_resolve(app.root, q.get("path", ""))
                if p.suffix.lower() != ".md" or not p.is_file():
                    return self._error(404, "page not found")
                text = p.read_text(encoding="utf-8", errors="replace")
                return self._json({"path": q["path"], "title": page_title(text, p.stem), "text": text})
            if route == "search" and method == "GET":
                return self._json(app.index.search(q.get("q", "")))
            if route == "notes":
                if method == "GET":
                    return self._json(app.notes.list(q.get("path", "")))
                b = self._body()
                path = b.get("path") or ""
                safe_resolve(app.root, path)
                if method == "POST":
                    return self._json(app.notes.add(path, b.get("text", "")), 201)
                if method == "PATCH":
                    if "text" in b:
                        return self._json(app.notes.edit(path, b["id"], b["text"]))
                    return self._json(app.notes.set_done(path, b["id"], b.get("done", True)))
                if method == "DELETE":
                    app.notes.delete(path, b["id"])
                    return self._json({"ok": True})
            self._error(404, "unknown route")

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_PATCH(self):
            self._dispatch("PATCH")

        def do_DELETE(self):
            self._dispatch("DELETE")

    return Handler


def make_server(app: App, host="127.0.0.1", port=4321):
    return ThreadingHTTPServer((host, port), make_handler(app))
