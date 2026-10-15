"""Markdown note templates and their (deliberately tiny) renderer.

Rules of the template language - all of it:

* ``{{key}}`` is replaced by the value of ``key``.
* Inside the YAML frontmatter (between the first two ``---`` lines) the value
  is written as a YAML scalar, so strings are quoted and ``None`` becomes
  ``null``.
* In the body the value is inserted verbatim (it may span several lines).
* A frontmatter line whose placeholders are **all missing from the value map**
  is dropped. Passing ``None`` explicitly is different: it keeps the line and
  writes ``null``. That is how optional fields disappear while required-but-
  unknown fields stay visible as ``null``.
* A missing placeholder anywhere else is an error, not an empty string.

The constants below are the source of truth. ``templates/source.md`` and
``templates/transcript.md`` are user-editable copies: when they exist they win,
so the note layout can be changed without touching the code.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from .errors import PipelineError
from .yamlio import to_yaml_scalar

PLACEHOLDER_RE = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")

SOURCE_TEMPLATE_NAME = "source.md"
TRANSCRIPT_TEMPLATE_NAME = "transcript.md"


class TemplateError(PipelineError):
    """A template referenced a value that was not supplied."""


DEFAULT_SOURCE_TEMPLATE = """---
type: {{type}}
source_type: {{source_type}}
source_id: {{source_id}}
title: {{title}}
provider: {{provider}}
url: {{url}}
media_url: {{media_url}}
subject: {{subject}}
language: {{language}}
duration: {{duration}}
duration_seconds: {{duration_seconds}}
resolution: {{resolution}}
uploader: {{uploader}}
upload_date: {{upload_date}}
provider_video_id: {{provider_video_id}}
media_file: {{media_file}}
transcript_file: {{transcript_file}}
metadata_file: {{metadata_file}}
downloaded_at: {{downloaded_at}}
pipeline_status: {{pipeline_status}}
schema_version: {{schema_version}}
---

# {{title}}

- Media: [{{media_file}}]({{media_file_href}})
- Transcript: [{{transcript_file}}]({{transcript_file_href}})
- Metadata: `{{metadata_file}}`
- Original page: {{url}}

> [!info] Staging source record
> This note is a **source**, not a knowledge note. It records where a media
> file came from; it does not claim anything about its content.
> Read `CLAUDE.md` in the repository root before deriving any knowledge note
> or vault link from it.
"""

DEFAULT_TRANSCRIPT_TEMPLATE = """---
type: {{type}}
source_id: {{source_id}}
source_note: {{source_note}}
media: {{media}}
language: {{language}}
transcript_status: {{transcript_status}}
transcript_postprocessed: {{transcript_postprocessed}}
transcript_engine: {{transcript_engine}}
transcript_model: {{transcript_model}}
transcript_confidence: {{transcript_confidence}}
transcript_generated_at: {{transcript_generated_at}}
schema_version: {{schema_version}}
---

# {{title}} — Transcript

{{body}}
"""

PENDING_TRANSCRIPT_BODY = """> [!warning] No transcript yet
> `transcript_status: pending` - this file is a placeholder. Nothing has been
> transcribed, so nothing here may be quoted or anchored.
>
> Generate one with:
> `python3 scripts/transcribe.py "<this folder>"`
"""


def load_template(name: str, templates_dir: Path | None = None) -> str:
    """Return a template, preferring a user-edited copy in ``templates/``."""
    defaults = {
        SOURCE_TEMPLATE_NAME: DEFAULT_SOURCE_TEMPLATE,
        TRANSCRIPT_TEMPLATE_NAME: DEFAULT_TRANSCRIPT_TEMPLATE,
    }
    if name not in defaults:
        raise TemplateError(f"Unknown template: {name}")
    if templates_dir is not None:
        candidate = Path(templates_dir) / name
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8")
            except OSError as exc:
                raise TemplateError(f"Cannot read template {candidate}: {exc}") from exc
            if text.strip():
                return text
    return defaults[name]


def _frontmatter_bounds(lines: list[str]) -> tuple[int, int] | None:
    if not lines or lines[0].strip() != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return 1, index
    return None


def render(template_text: str, values: Mapping[str, Any]) -> str:
    """Render a template (see the module docstring for the whole language)."""
    lines = template_text.splitlines()
    bounds = _frontmatter_bounds(lines)
    front_range = range(bounds[0], bounds[1]) if bounds else range(0)

    out: list[str] = []
    for index, line in enumerate(lines):
        keys = PLACEHOLDER_RE.findall(line)
        in_frontmatter = index in front_range
        if keys and in_frontmatter and all(key not in values for key in keys):
            continue  # optional field that was not supplied at all
        missing = [key for key in keys if key not in values]
        if missing:
            raise TemplateError(
                f"Template placeholder(s) without a value: {', '.join(sorted(set(missing)))}"
            )

        def substitute(match: re.Match[str]) -> str:
            value = values[match.group(1)]
            if in_frontmatter:
                return to_yaml_scalar(value)
            return "" if value is None else str(value)

        out.append(PLACEHOLDER_RE.sub(substitute, line))
    rendered = "\n".join(out)
    return rendered if rendered.endswith("\n") else rendered + "\n"
