"""Read/write review notes kept in a single NOTES.md.

Format:
    # KB Review Notes

    ## concepts/auth/oauth.md
    - [ ] 2026-10-26 14:02 — Missing refresh flow
      continuation line
    - [x] 2026-10-25 09:10 — Fixed link

The file is re-read on every operation so manual edits are never clobbered.
Unrecognised lines inside a section are preserved verbatim.
"""
import hashlib
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

HEADER = "# KB Review Notes"
SEP = " — "
ITEM_RE = re.compile(r"^- \[([ xX])\] ?(.*)$")
STAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2})" + SEP + r"(.*)$", re.S)

_lock = threading.Lock()


@dataclass
class Note:
    done: bool
    stamp: str
    text: str

    @property
    def id(self):
        return hashlib.sha1(f"{self.stamp}|{self.text}".encode()).hexdigest()[:10]

    def to_dict(self):
        return {"id": self.id, "done": self.done, "stamp": self.stamp, "text": self.text}

    def to_lines(self):
        first, *rest = self.text.split("\n")
        head = f"{self.stamp}{SEP}{first}" if self.stamp else first
        return [f"- [{'x' if self.done else ' '}] {head}"] + [f"  {l}" for l in rest]


def parse(text: str):
    """Return (preamble_lines, sections) where sections is {path: [Note | str]}."""
    preamble, sections, current = [], {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            current = sections.setdefault(line[3:].strip(), [])
            continue
        if current is None:
            if line.strip() != HEADER:
                preamble.append(line)
            continue
        m = ITEM_RE.match(line)
        if m:
            body = m.group(2)
            sm = STAMP_RE.match(body)
            stamp, body = (sm.group(1), sm.group(2)) if sm else ("", body)
            current.append(Note(m.group(1) != " ", stamp, body))
        elif line.startswith("  ") and current and isinstance(current[-1], Note):
            current[-1].text += "\n" + line[2:]
        elif line.strip():
            current.append(line)
    while preamble and not preamble[-1].strip():
        preamble.pop()
    while preamble and not preamble[0].strip():
        preamble.pop(0)
    return preamble, sections


def serialize(preamble, sections) -> str:
    out = [HEADER, ""]
    if preamble:
        out += preamble + [""]
    for path, entries in sections.items():
        if not entries:
            continue
        out.append(f"## {path}")
        for e in entries:
            out += e.to_lines() if isinstance(e, Note) else [e]
        out.append("")
    return "\n".join(out)


class NotesStore:
    def __init__(self, file: Path):
        self.file = Path(file)

    def _load(self):
        if not self.file.exists():
            return [], {}
        return parse(self.file.read_text(encoding="utf-8"))

    def _save(self, preamble, sections):
        self.file.write_text(serialize(preamble, sections), encoding="utf-8")

    def list(self, path):
        _, sections = self._load()
        return [n.to_dict() for n in sections.get(path, []) if isinstance(n, Note)]

    def counts(self):
        """Open note count per page."""
        _, sections = self._load()
        res = {}
        for path, entries in sections.items():
            n = sum(1 for e in entries if isinstance(e, Note) and not e.done)
            if n:
                res[path] = n
        return res

    def add(self, path, text, now=None):
        text = text.strip().replace("\r\n", "\n")
        if not text:
            raise ValueError("empty note")
        stamp = (now or datetime.now()).strftime("%Y-%m-%d %H:%M")
        with _lock:
            pre, sections = self._load()
            note = Note(False, stamp, text)
            sections.setdefault(path, []).append(note)
            self._save(pre, sections)
        return note.to_dict()

    def _find(self, sections, path, note_id):
        for e in sections.get(path, []):
            if isinstance(e, Note) and e.id == note_id:
                return e
        raise KeyError(note_id)

    def set_done(self, path, note_id, done):
        with _lock:
            pre, sections = self._load()
            note = self._find(sections, path, note_id)
            note.done = bool(done)
            self._save(pre, sections)
        return note.to_dict()

    def edit(self, path, note_id, text):
        text = text.strip().replace("\r\n", "\n")
        if not text:
            raise ValueError("empty note")
        with _lock:
            pre, sections = self._load()
            note = self._find(sections, path, note_id)
            note.text = text
            self._save(pre, sections)
        return note.to_dict()

    def delete(self, path, note_id):
        with _lock:
            pre, sections = self._load()
            note = self._find(sections, path, note_id)
            sections[path].remove(note)
            self._save(pre, sections)
