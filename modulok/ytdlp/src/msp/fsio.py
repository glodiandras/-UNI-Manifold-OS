"""Small filesystem helpers with typed errors and atomic writes.

Every file the pipeline generates is written atomically (temp file in the same
directory + ``os.replace``), so an interrupted run can never leave a truncated
source.md or metadata.json behind.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import FilesystemError


def write_text_atomic(path: str | Path, text: str, *, encoding: str = "utf-8") -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp"
        )
        handle = os.fdopen(fd, "w", encoding=encoding, newline="\n")
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        handle = None
        os.replace(tmp_name, target)
    except OSError as exc:
        if handle is not None:
            handle.close()
        raise FilesystemError(f"Cannot write {target}: {exc}") from exc
    return target


def write_json_atomic(path: str | Path, data: Any, *, indent: int = 2) -> Path:
    try:
        text = json.dumps(data, ensure_ascii=False, indent=indent, sort_keys=False) + "\n"
    except (TypeError, ValueError) as exc:
        raise FilesystemError(f"Cannot serialise JSON for {path}: {exc}") from exc
    return write_text_atomic(path, text)


def read_json(path: str | Path) -> Any:
    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FilesystemError(f"File not found: {target}") from exc
    except OSError as exc:
        raise FilesystemError(f"Cannot read {target}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise FilesystemError(f"Invalid JSON in {target}: {exc}") from exc


def read_text(path: str | Path) -> str:
    target = Path(path)
    try:
        return target.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FilesystemError(f"File not found: {target}") from exc
    except OSError as exc:
        raise FilesystemError(f"Cannot read {target}: {exc}") from exc


def human_size(num_bytes: float | int | None) -> str:
    """Bytes -> short human readable size, used in CLI output only."""
    if not num_bytes:
        return "?"
    size = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TiB"


def dir_is_empty(path: str | Path) -> bool:
    target = Path(path)
    return target.is_dir() and not any(target.iterdir())
