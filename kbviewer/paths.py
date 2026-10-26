from pathlib import Path


class PathError(ValueError):
    pass


def safe_resolve(root: Path, rel: str) -> Path:
    """Resolve a KB-relative path, refusing anything that escapes root."""
    root = Path(root).resolve()
    rel = (rel or "").replace("\\", "/").lstrip("/")
    target = (root / rel).resolve()
    if target != root and root not in target.parents:
        raise PathError(f"path escapes KB root: {rel}")
    return target


def to_rel(root: Path, path: Path) -> str:
    return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
