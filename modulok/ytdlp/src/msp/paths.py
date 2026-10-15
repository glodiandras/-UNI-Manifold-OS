"""Project-root discovery and path resolution.

Nothing in the pipeline hardcodes an absolute path (spec section 14). Every
relative path in config.yaml is resolved against the *project root*, which is
found in this order:

1. ``$MSP_PROJECT_ROOT`` (the ``scripts/*.py`` wrappers set it from their own
   location, so running them from anywhere works)
2. the nearest ancestor - of an explicit start path, of the working directory,
   then of this source file - that contains ``config/config.yaml``
3. the same search for ``pyproject.toml``
4. the current working directory (last resort)
"""

from __future__ import annotations

import os
from pathlib import Path

PRIMARY_MARKER = "config/config.yaml"
SECONDARY_MARKER = "pyproject.toml"
MARKERS = (PRIMARY_MARKER, SECONDARY_MARKER)


def _walk_up(start: Path, marker: str) -> Path | None:
    current = Path(start).expanduser().resolve()
    for candidate in (current, *current.parents):
        if (candidate / marker).exists():
            return candidate
    return None


def find_project_root(start: str | Path | None = None) -> Path:
    """Locate the project root directory.

    ``config/config.yaml`` outranks ``pyproject.toml`` as a marker: an unrelated
    Python project in a parent directory (or in the current working directory)
    must never be mistaken for this pipeline's root.
    """
    env_root = os.environ.get("MSP_PROJECT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    origins = [Path(start)] if start is not None else []
    origins += [Path.cwd(), Path(__file__).parent]
    for marker in MARKERS:
        for origin in origins:
            found = _walk_up(origin, marker)
            if found:
                return found
    return Path.cwd().resolve()


def resolve_path(value: str | Path, root: Path) -> Path:
    """Resolve a config path value: ``~`` expanded, relatives anchored at *root*."""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return Path(os.path.normpath(path))


def ensure_directory(path: Path) -> Path:
    """``mkdir -p`` with a typed error."""
    from .errors import FilesystemError

    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise FilesystemError(f"Cannot create directory {path}: {exc}") from exc
    return path
