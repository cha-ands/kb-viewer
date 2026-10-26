# KB Viewer

Local browser viewer for a markdown knowledge base with nested concept folders, plus a notes panel that records page review notes in a single `NOTES.md`.

No dependencies beyond Python 3.10+. Frontend libraries (marked, highlight.js, mermaid, js-yaml, DOMPurify) are vendored in `static/vendor/`, so it works offline.

## Run

```
python kbview.py <path-to-kb> [--port 4321] [--notes path/to/NOTES.md] [--no-browser]
```

Opens `http://127.0.0.1:4321`.

## Features

- Folder tree to any depth. A folder's page is `index.md`, `README.md` or `<folder>.md`; clicking the folder opens it.
- Markdown rendering: GFM tables and task lists, frontmatter shown as a metadata box, syntax highlighting, mermaid diagrams.
- Relative `.md` links and `[[wikilinks]]` (`[[name]]`, `[[name|label]]`, `[[path/to/page#heading]]`) open inside the viewer. Links that don't resolve are shown in red.
- Search (`/` to focus, Enter opens the top hit, Esc clears).
- Notes panel: add (Ctrl+Enter), tick off, edit, delete. Badges in the tree show open notes per page. Collapsed folders show the total for everything inside.
- Light/dark theme and resizable panes.

## NOTES.md

Saved to `<kb>/NOTES.md` by default (hidden from the tree):

```
# KB Review Notes

## concepts/auth/oauth/index.md
- [ ] 2026-10-26 14:02 — Missing refresh token rotation
- [x] 2026-10-25 09:10 — Fix broken link to sessions
```

You can edit the file by hand. The app reads it again before every change, and keeps any lines it doesn't recognise.

## Tests

```
python -m unittest discover -s tests -t .
```
