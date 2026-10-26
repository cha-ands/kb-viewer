from pathlib import Path

from .paths import to_rel

SKIP_DIRS = {"node_modules", "__pycache__"}
INDEX_NAMES = ("index.md", "readme.md")


def find_index(folder: Path):
    """Index page for a folder: index.md, README.md or <folder>.md inside it."""
    names = {p.name.lower(): p for p in folder.iterdir() if p.is_file()}
    for n in INDEX_NAMES + (folder.name.lower() + ".md",):
        if n in names:
            return names[n]
    return None


def build_tree(root: Path, exclude=()):
    root = Path(root).resolve()
    exclude = {Path(e).resolve() for e in exclude}

    def walk(folder: Path):
        children = []
        entries = sorted(folder.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        for p in entries:
            if p.name.startswith(".") or p.resolve() in exclude:
                continue
            if p.is_dir():
                if p.name in SKIP_DIRS:
                    continue
                node = walk(p)
                if node["children"] or node["index"]:
                    children.append(node)
            elif p.suffix.lower() == ".md":
                children.append({"type": "file", "name": p.stem, "path": to_rel(root, p)})
        idx = find_index(folder)
        return {
            "type": "dir",
            "name": folder.name,
            "path": "" if folder == root else to_rel(root, folder),
            "index": to_rel(root, idx) if idx else None,
            "children": children,
        }

    return walk(root)


def iter_pages(root: Path, exclude=()):
    """Yield every .md file path (relative) in the tree."""
    def rec(node):
        for c in node["children"]:
            if c["type"] == "file":
                yield c["path"]
            else:
                yield from rec(c)
    yield from rec(build_tree(root, exclude))
