"""YAML input/output for the pipeline.

PyYAML is a declared dependency and is used whenever it can be imported. The
module additionally ships a deliberately small fallback reader so that a bare
``python3 scripts/validate.py`` keeps working in an interpreter where PyYAML
was never installed - the staging tree is meant to stay readable years from
now, without a working virtualenv.

The fallback understands exactly the subset this pipeline emits (nested
mappings, block/flow sequences of scalars, quoted and plain scalars, comments).
Anything else - anchors, aliases, tags, block scalars, multi-document streams -
raises :class:`~msp.errors.YamlSubsetError` telling the user to install PyYAML,
instead of silently guessing at a meaning.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .errors import ConfigError, YamlSubsetError

try:  # pragma: no cover - trivial import guard
    import yaml as _pyyaml
except ImportError:  # pragma: no cover
    _pyyaml = None

HAVE_PYYAML = _pyyaml is not None

FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)(?:\r?\n)---[ \t]*(?:\r?\n(.*))?\Z", re.DOTALL)

_INT_RE = re.compile(r"\A[-+]?\d+\Z")
_FLOAT_RE = re.compile(r"\A[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?\Z")
_TRUE = {"true", "yes", "on"}
_FALSE = {"false", "no", "off"}
_NULL = {"", "null", "~"}

_INSTALL_HINT = "Install PyYAML for full YAML support:  pip install PyYAML"


def backend_name() -> str:
    """Which reader is active - useful in diagnostics and log headers."""
    return "PyYAML" if HAVE_PYYAML else "builtin-subset"


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def load(text: str, *, origin: str = "<string>") -> Any:
    """Parse a YAML document into Python data."""
    if HAVE_PYYAML:
        try:
            return _pyyaml.safe_load(text)
        except _pyyaml.YAMLError as exc:  # pragma: no cover - message passthrough
            raise ConfigError(f"Invalid YAML in {origin}: {exc}") from exc
    return _load_subset(text, origin=origin)


def load_file(path: str | Path) -> Any:
    """Parse a YAML file. Missing files raise :class:`ConfigError`."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"YAML file not found: {p}") from exc
    except OSError as exc:
        raise ConfigError(f"Cannot read YAML file {p}: {exc}") from exc
    return load(text, origin=str(p))


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Split ``---\\n...\\n---\\n<body>`` into (frontmatter_text, body).

    Returns ``(None, text)`` when the document has no frontmatter block.
    """
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None, text
    return match.group(1), match.group(2) or ""


def parse_frontmatter(text: str, *, origin: str = "<string>") -> tuple[dict[str, Any], str]:
    """Parse a Markdown note into (frontmatter mapping, body).

    Raises :class:`ConfigError` when the note has no frontmatter or when the
    frontmatter is not a mapping.
    """
    front_text, body = split_frontmatter(text)
    if front_text is None:
        raise ConfigError(f"{origin}: missing YAML frontmatter (--- ... --- at the top of the file)")
    data = load(front_text, origin=origin)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"{origin}: YAML frontmatter must be a mapping, got {type(data).__name__}")
    return data, body


def to_yaml_scalar(value: Any) -> str:
    """Render a Python value as a single-line YAML scalar.

    Strings are always double-quoted so that values like ``2024-01-01`` or
    ``no`` cannot change type on a round trip. Used by the template renderer,
    which is the only place where the pipeline writes frontmatter.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(to_yaml_scalar(v) for v in value) + "]"
    text = str(value)
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def dump_mapping(mapping: dict[str, Any], *, indent: int = 0) -> str:
    """Render a flat/nested mapping of scalars as YAML lines (no document markers)."""
    pad = " " * indent
    out: list[str] = []
    for key, value in mapping.items():
        if isinstance(value, dict):
            out.append(f"{pad}{key}:")
            out.append(dump_mapping(value, indent=indent + 2))
        elif isinstance(value, (list, tuple)) and value and any(isinstance(v, dict) for v in value):
            raise ValueError("dump_mapping does not support sequences of mappings")
        else:
            out.append(f"{pad}{key}: {to_yaml_scalar(value)}")
    return "\n".join(line for line in out if line != "")


# ---------------------------------------------------------------------------
# minimal fallback reader
# ---------------------------------------------------------------------------

def _fail(line_no: int, origin: str, reason: str) -> YamlSubsetError:
    return YamlSubsetError(
        f"{origin}:{line_no}: {reason} (bundled minimal YAML reader)",
        hint=_INSTALL_HINT,
    )


def _strip_comment(raw: str) -> str:
    """Remove a trailing ``#`` comment that is not inside a quoted scalar."""
    out: list[str] = []
    quote: str | None = None
    prev = ""
    for index, char in enumerate(raw):
        if quote:
            out.append(char)
            if char == quote and prev != "\\":
                quote = None
            prev = "" if (char == "\\" and prev == "\\") else char
            continue
        if char in "\"'":
            quote = char
            out.append(char)
        elif char == "#" and (index == 0 or raw[index - 1] in " \t"):
            break
        else:
            out.append(char)
        prev = char
    return "".join(out).rstrip()


def _parse_quoted(value: str, line_no: int, origin: str) -> str:
    quote = value[0]
    body = value[1:-1]
    if len(value) < 2 or value[-1] != quote:
        raise _fail(line_no, origin, "unterminated quoted scalar")
    if quote == "'":
        return body.replace("''", "'")
    out: list[str] = []
    i = 0
    while i < len(body):
        char = body[i]
        if char != "\\":
            out.append(char)
            i += 1
            continue
        i += 1
        if i >= len(body):
            raise _fail(line_no, origin, "dangling backslash in quoted scalar")
        esc = body[i]
        simple = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "/": "/", "0": "\0"}
        if esc in simple:
            out.append(simple[esc])
            i += 1
        elif esc in "uU":
            width = 4 if esc == "u" else 8
            hexpart = body[i + 1 : i + 1 + width]
            if len(hexpart) != width:
                raise _fail(line_no, origin, "truncated unicode escape")
            out.append(chr(int(hexpart, 16)))
            i += 1 + width
        else:
            raise _fail(line_no, origin, f"unsupported escape sequence \\{esc}")
    return "".join(out)


def _parse_scalar(value: str, line_no: int, origin: str) -> Any:
    value = value.strip()
    if not value:
        return None
    if value[0] in "\"'":
        return _parse_quoted(value, line_no, origin)
    if value[0] in "&*!|>":
        raise _fail(line_no, origin, f"unsupported YAML construct starting with {value[0]!r}")
    if value.startswith("["):
        if not value.endswith("]"):
            raise _fail(line_no, origin, "multi-line flow sequences are not supported")
        return _parse_flow_sequence(value, line_no, origin)
    if value.startswith("{"):
        if value.strip() == "{}":
            return {}
        raise _fail(line_no, origin, "inline flow mappings are not supported")
    lowered = value.lower()
    if lowered in _NULL:
        return None
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    if _INT_RE.match(value):
        return int(value)
    if _FLOAT_RE.match(value):
        return float(value)
    return value


def _split_flow_items(inner: str, line_no: int, origin: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    quote: str | None = None
    prev = ""
    for char in inner:
        if quote:
            current.append(char)
            if char == quote and prev != "\\":
                quote = None
            prev = "" if (char == "\\" and prev == "\\") else char
            continue
        if char in "\"'":
            quote = char
            current.append(char)
        elif char == ",":
            items.append("".join(current))
            current = []
        elif char in "[]{}":
            raise _fail(line_no, origin, "nested flow collections are not supported")
        else:
            current.append(char)
        prev = char
    tail = "".join(current).strip()
    if tail:
        items.append(tail)
    return [item.strip() for item in items if item.strip()]


def _parse_flow_sequence(value: str, line_no: int, origin: str) -> list[Any]:
    inner = value[1:-1].strip()
    if not inner:
        return []
    return [_parse_scalar(item, line_no, origin) for item in _split_flow_items(inner, line_no, origin)]


def _split_key(line: str, line_no: int, origin: str) -> tuple[str, str]:
    """Split ``key: value`` honouring quoted keys and colons inside values."""
    if line[0] in "\"'":
        quote = line[0]
        end = line.find(quote, 1)
        while end != -1 and line[end - 1] == "\\":
            end = line.find(quote, end + 1)
        if end == -1:
            raise _fail(line_no, origin, "unterminated quoted key")
        key = _parse_quoted(line[: end + 1], line_no, origin)
        rest = line[end + 1 :].lstrip()
        if not rest.startswith(":"):
            raise _fail(line_no, origin, "expected ':' after quoted key")
        return key, rest[1:].strip()
    quote: str | None = None
    for index, char in enumerate(line):
        if quote:
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
        elif char == ":" and (index + 1 == len(line) or line[index + 1] in " \t"):
            return line[:index].strip(), line[index + 1 :].strip()
    raise _fail(line_no, origin, "expected 'key: value' mapping entry")


class _Line:
    __slots__ = ("indent", "text", "number")

    def __init__(self, indent: int, text: str, number: int) -> None:
        self.indent = indent
        self.text = text
        self.number = number


def _load_subset(text: str, *, origin: str) -> Any:
    lines: list[_Line] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise _fail(number, origin, "tab indentation is not valid YAML")
        stripped = _strip_comment(raw)
        if not stripped.strip():
            continue
        if stripped.strip() in {"---", "..."}:
            if lines:
                raise _fail(number, origin, "multi-document streams are not supported")
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        lines.append(_Line(indent, stripped.strip(), number))
    if not lines:
        return None
    value, index = _parse_block(lines, 0, lines[0].indent, origin)
    if index != len(lines):
        raise _fail(lines[index].number, origin, "unexpected indentation")
    return value


def _parse_block(lines: list[_Line], index: int, indent: int, origin: str) -> tuple[Any, int]:
    if lines[index].text.startswith("- "):
        return _parse_sequence(lines, index, indent, origin)
    if lines[index].text == "-":
        raise _fail(lines[index].number, origin, "nested sequence items are not supported")
    return _parse_mapping(lines, index, indent, origin)


def _parse_mapping(lines: list[_Line], index: int, indent: int, origin: str) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        line = lines[index]
        if line.indent < indent:
            break
        if line.indent > indent:
            raise _fail(line.number, origin, "unexpected indentation")
        if line.text.startswith("- "):
            raise _fail(line.number, origin, "sequence item inside a mapping")
        key, raw_value = _split_key(line.text, line.number, origin)
        if raw_value:
            result[key] = _parse_scalar(raw_value, line.number, origin)
            index += 1
            continue
        # value on the following, more deeply indented lines
        if index + 1 < len(lines) and lines[index + 1].indent > indent:
            child_indent = lines[index + 1].indent
            value, index = _parse_block(lines, index + 1, child_indent, origin)
            result[key] = value
        elif index + 1 < len(lines) and lines[index + 1].indent == indent and lines[index + 1].text.startswith("- "):
            value, index = _parse_sequence(lines, index + 1, indent, origin)
            result[key] = value
        else:
            result[key] = None
            index += 1
    return result, index


def _parse_sequence(lines: list[_Line], index: int, indent: int, origin: str) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        line = lines[index]
        if line.indent < indent or not line.text.startswith("- "):
            break
        if line.indent > indent:
            raise _fail(line.number, origin, "unexpected indentation")
        item = line.text[2:].strip()
        if not item:
            raise _fail(line.number, origin, "empty sequence item")
        if ": " in item or item.endswith(":"):
            raise _fail(line.number, origin, "mappings inside sequences are not supported")
        result.append(_parse_scalar(item, line.number, origin))
        index += 1
    return result, index
