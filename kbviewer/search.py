import re
from pathlib import Path

from .tree import iter_pages

FM_TITLE_RE = re.compile(r"^title:\s*['\"]?(.+?)['\"]?\s*$", re.M)
H1_RE = re.compile(r"^#\s+(.+)$", re.M)


def page_title(text: str, fallback: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            m = FM_TITLE_RE.search(text[3:end])
            if m:
                return m.group(1)
    m = H1_RE.search(text)
    return m.group(1).strip() if m else fallback


class SearchIndex:
    """Plain substring search with an mtime-keyed text cache."""

    def __init__(self, root: Path, exclude=()):
        self.root = Path(root).resolve()
        self.exclude = exclude
        self._cache = {}  # rel -> (mtime, text, title)

    def _docs(self):
        seen = set()
        for rel in iter_pages(self.root, self.exclude):
            seen.add(rel)
            p = self.root / rel
            mtime = p.stat().st_mtime
            hit = self._cache.get(rel)
            if not hit or hit[0] != mtime:
                text = p.read_text(encoding="utf-8", errors="replace")
                hit = (mtime, text, page_title(text, p.stem))
                self._cache[rel] = hit
            yield rel, hit[1], hit[2]
        for gone in set(self._cache) - seen:
            del self._cache[gone]

    def search(self, q: str, limit=50):
        terms = [t for t in q.lower().split() if t]
        if not terms:
            return []
        results = []
        for rel, text, title in self._docs():
            low, tlow, plow = text.lower(), title.lower(), rel.lower()
            if not all(t in low or t in plow for t in terms):
                continue
            score = sum(10 * (t in tlow) + 5 * (t in plow) + min(low.count(t), 5) for t in terms)
            results.append({"path": rel, "title": title, "snippet": _snippet(text, terms[0]), "score": score})
        results.sort(key=lambda r: -r["score"])
        return results[:limit]


def _snippet(text, term, width=80):
    i = text.lower().find(term)
    if i == -1:
        return text[:width * 2].replace("\n", " ").strip()
    start = max(0, i - width)
    s = text[start:i + len(term) + width].replace("\n", " ").strip()
    return ("…" if start else "") + s + "…"
