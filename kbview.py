"""KB Viewer — browse a markdown knowledge base and keep review notes.

Usage: python kbview.py <kb_path> [--port 4321] [--notes NOTES.md] [--no-browser]
"""
import argparse
import sys
import webbrowser
from pathlib import Path

from kbviewer.server import App, make_server


def main():
    ap = argparse.ArgumentParser(description="Markdown knowledge base viewer")
    ap.add_argument("kb", help="path to the knowledge base folder")
    ap.add_argument("--port", type=int, default=4321)
    ap.add_argument("--notes", help="notes file (default: <kb>/NOTES.md)")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    root = Path(args.kb).expanduser()
    if not root.is_dir():
        sys.exit(f"not a folder: {root}")
    app = App(root, args.notes)
    srv = make_server(app, port=args.port)
    url = f"http://127.0.0.1:{args.port}"
    print(f"KB:    {app.root}\nNotes: {app.notes_file}\nOpen:  {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
