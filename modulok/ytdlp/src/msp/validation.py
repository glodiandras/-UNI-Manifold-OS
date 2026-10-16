"""Staging validation (spec section 19).

Answers one question: *is this staging tree still internally consistent and
safe to hand to the integration step?* Errors are structural breakage; warnings
are things a human should look at but that do not make the tree unusable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import schema
from .archive import Archive
from .config import Config
from .errors import PipelineError
from .fsio import read_json
from .notes import read_note
from .subjects import normalize_subject
from .timestamps import is_valid_timestamp, parse_timestamp

ERROR = "ERROR"
WARNING = "WARNING"
INFO = "INFO"

_MARKER_RE = re.compile(r"^\[([^\]]+)\]\s*$", re.MULTILINE)
_WIKILINK_RE = re.compile(r"\[\[([^\]|#^]+)")


@dataclass(frozen=True)
class Issue:
    level: str
    code: str
    path: str
    message: str

    def render(self) -> str:
        return f"{self.level:7} {self.path}\n        [{self.code}] {self.message}"


@dataclass
class ValidationReport:
    issues: list[Issue] = field(default_factory=list)
    sources_checked: int = 0
    pending_transcripts: int = 0
    undecided_anchorable: int = 0

    def add(self, level: str, code: str, path: Path | str, message: str) -> Issue:
        issue = Issue(level, code, str(path), message)
        self.issues.append(issue)
        return issue

    def of_level(self, level: str) -> list[Issue]:
        return [issue for issue in self.issues if issue.level == level]

    @property
    def errors(self) -> list[Issue]:
        return self.of_level(ERROR)

    @property
    def warnings(self) -> list[Issue]:
        return self.of_level(WARNING)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "sources_checked": self.sources_checked,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "pending_transcripts": self.pending_transcripts,
            "undecided_nn_anchorable": self.undecided_anchorable,
            "issues": [
                {"level": i.level, "code": i.code, "path": i.path, "message": i.message}
                for i in self.issues
            ],
        }

    def render(self) -> str:
        lines: list[str] = []
        for level in (ERROR, WARNING, INFO):
            for issue in self.of_level(level):
                lines.append(issue.render())
        lines.append("")
        lines.append(f"Sources checked: {self.sources_checked}")
        lines.append(f"Errors:          {len(self.errors)}")
        lines.append(f"Warnings:        {len(self.warnings)}")
        lines.append(f"Transcripts pending: {self.pending_transcripts}")
        lines.append(
            f"nn_anchorable undecided: {self.undecided_anchorable} "
            "(the vault owner has not ruled on video sources yet)"
        )
        lines.append("OK - no structural problems." if self.ok else "FAILED - see the errors above.")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# field level checks
# ---------------------------------------------------------------------------

def _check_fields(
    report: ValidationReport,
    path: Path,
    data: dict[str, Any],
    fields: Iterable[schema.FieldSpec],
    *,
    code_prefix: str,
) -> None:
    for spec in fields:
        if spec.name not in data:
            if spec.required:
                report.add(ERROR, f"{code_prefix}.missing_field", path,
                           f"required field '{spec.name}' is missing")
            continue
        value = data[spec.name]
        if value is None or (isinstance(value, str) and not value.strip()):
            if spec.required and not spec.nullable:
                report.add(ERROR, f"{code_prefix}.empty_field", path,
                           f"required field '{spec.name}' is empty")
            continue
        if spec.enum and str(value) not in spec.enum:
            report.add(ERROR, f"{code_prefix}.bad_enum", path,
                       f"'{spec.name}' is {value!r}, expected one of: {', '.join(spec.enum)}")
        expected = spec.kind
        if expected is not str and not isinstance(value, expected):
            report.add(ERROR, f"{code_prefix}.bad_type", path,
                       f"'{spec.name}' should be {getattr(expected, '__name__', expected)}, got {type(value).__name__}")


def _check_wikilinks(
    report: ValidationReport,
    path: Path,
    folder: Path,
    data: dict[str, Any],
    fields: tuple[str, ...],
) -> None:
    """Every [[wikilink]] in the frontmatter must resolve inside the folder.

    Obsidian resolves an unqualified link vault-wide, so this only checks that
    the intended target exists next to the note - which is what integration
    will rewrite the links against.
    """
    for field_name in fields:
        raw = data.get(field_name)
        if not isinstance(raw, str):
            continue
        for target in _WIKILINK_RE.findall(raw):
            name = target.strip()
            if not name:
                continue
            if (folder / name).exists() or (folder / f"{name}.md").exists():
                continue
            report.add(ERROR, "note.broken_link", path,
                       f"'{field_name}' points at [[{name}]], which does not exist in this folder")


def _check_transcript_body(report: ValidationReport, path: Path, body: str, status: str) -> None:
    markers = _MARKER_RE.findall(body)
    timestamps: list[int] = []
    for marker in markers:
        if not is_valid_timestamp(marker):
            report.add(ERROR, "transcript.bad_timestamp", path,
                       f"timestamp marker [{marker}] is not zero-padded HH:MM:SS")
            continue
        timestamps.append(parse_timestamp(marker))
    for previous, current in zip(timestamps, timestamps[1:]):
        if current < previous:
            report.add(WARNING, "transcript.unordered", path,
                       "timestamp markers are not in increasing order")
            break
    if status == "completed" and not timestamps:
        report.add(WARNING, "transcript.no_timestamps", path,
                   "transcript_status is 'completed' but the body has no [HH:MM:SS] markers")


# ---------------------------------------------------------------------------
# per source folder
# ---------------------------------------------------------------------------

def validate_source_folder(report: ValidationReport, folder: Path, config: Config) -> str | None:
    """Validate one staged source. Returns its source_id when readable."""
    source_note = folder / schema.SOURCE_NOTE_NAME
    try:
        front, _ = read_note(source_note)
    except PipelineError as exc:
        report.add(ERROR, "source.unreadable", source_note, str(exc))
        return None

    _check_fields(report, source_note, front, schema.SOURCE_FIELDS, code_prefix="source")
    source_id = str(front.get("source_id") or "") or None

    subject = front.get("subject")
    if subject:
        _, known = normalize_subject(str(subject), config)
        if not known:
            report.add(WARNING, "source.unknown_subject", source_note,
                       f"subject {subject!r} is not in subjects.taxonomy - "
                       "integration will need a mapping decision")

    media_file = str(front.get("media_file") or "")
    if media_file:
        media_path = folder / media_file
        if not media_path.is_file():
            report.add(ERROR, "source.missing_media", source_note,
                       f"media_file '{media_file}' does not exist")
        elif media_path.stat().st_size == 0:
            report.add(ERROR, "source.empty_media", source_note,
                       f"media_file '{media_file}' is empty (0 bytes)")

    metadata_file = str(front.get("metadata_file") or schema.METADATA_NAME)
    metadata_path = folder / metadata_file
    if not metadata_path.is_file():
        report.add(ERROR, "source.missing_metadata", source_note,
                   f"metadata_file '{metadata_file}' does not exist")
    else:
        try:
            metadata = read_json(metadata_path)
            if not isinstance(metadata, dict):
                report.add(ERROR, "metadata.not_object", metadata_path,
                           "metadata.json does not contain a JSON object")
            else:
                pipeline_block = metadata.get("pipeline")
                recorded = (pipeline_block or {}).get("source_id") if isinstance(pipeline_block, dict) else None
                if source_id and recorded and recorded != source_id:
                    report.add(WARNING, "metadata.source_id_mismatch", metadata_path,
                               f"metadata source_id {recorded!r} != source.md {source_id!r}")
        except PipelineError as exc:
            report.add(ERROR, "metadata.invalid_json", metadata_path, str(exc))

    transcript_file = str(front.get("transcript_file") or schema.TRANSCRIPT_NOTE_NAME)
    transcript_path = folder / transcript_file
    if not transcript_path.is_file():
        report.add(ERROR, "source.missing_transcript", source_note,
                   f"transcript_file '{transcript_file}' does not exist")
    else:
        try:
            tfront, tbody = read_note(transcript_path)
            _check_fields(report, transcript_path, tfront, schema.TRANSCRIPT_FIELDS,
                          code_prefix="transcript")
            _check_wikilinks(report, transcript_path, folder, tfront, ("source_note", "media"))
            tid = str(tfront.get("source_id") or "")
            if source_id and tid and tid != source_id:
                report.add(ERROR, "transcript.source_id_mismatch", transcript_path,
                           f"source_id {tid!r} != source.md {source_id!r}")
            status = str(tfront.get("transcript_status") or "")
            if status == "pending":
                report.pending_transcripts += 1
            _check_transcript_body(report, transcript_path, tbody, status)
            if status == "completed" and tfront.get("transcript_postprocessed") is True:
                report.add(WARNING, "transcript.postprocessed", transcript_path,
                           "the text was post-processed, so it is no longer a character-exact "
                           "quote source")
        except PipelineError as exc:
            report.add(ERROR, "transcript.unreadable", transcript_path, str(exc))

    manifest_path = folder / schema.MANIFEST_NAME
    if not manifest_path.is_file():
        report.add(WARNING, "manifest.missing", folder,
                   f"{schema.MANIFEST_NAME} is missing - the integration step has no machine-readable entry")
    else:
        try:
            data = read_json(manifest_path)
            if not isinstance(data, dict):
                report.add(ERROR, "manifest.not_object", manifest_path,
                           "integration.json does not contain a JSON object")
            else:
                _check_fields(report, manifest_path, data, schema.MANIFEST_FIELDS, code_prefix="manifest")
                if source_id and str(data.get("source_id") or "") != source_id:
                    report.add(ERROR, "manifest.source_id_mismatch", manifest_path,
                               f"source_id {data.get('source_id')!r} != source.md {source_id!r}")
                if data.get("nn_anchorable") is None:
                    report.undecided_anchorable += 1
        except PipelineError as exc:
            report.add(ERROR, "manifest.invalid_json", manifest_path, str(exc))

    for component in folder.parts[-3:]:
        if any(char in component for char in "[]#^|"):
            report.add(WARNING, "staging.unsafe_path", folder,
                       f"folder name {component!r} contains a character that breaks an "
                       "Obsidian wikilink ([ ] # ^ |)")
        elif component != component.strip(" ."):
            report.add(WARNING, "staging.unsafe_path", folder,
                       f"folder name {component!r} starts or ends with a space or dot")

    leftovers = [p.name for p in folder.glob("*") if p.suffix in {".part", ".ytdl", ".temp"}]
    if leftovers:
        report.add(WARNING, "source.leftover_files", folder,
                   f"interrupted-download leftovers: {', '.join(sorted(leftovers))}")
    return source_id


# ---------------------------------------------------------------------------
# whole tree
# ---------------------------------------------------------------------------

def _find_orphans(report: ValidationReport, root: Path) -> None:
    media_suffixes = {".mp4", ".mkv", ".webm", ".m4v", ".mov", ".avi", ".flv"}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name == schema.SOURCE_NOTE_NAME:
            continue
        is_media = path.suffix.lower() in media_suffixes
        is_note = path.name in {schema.TRANSCRIPT_NOTE_NAME, schema.MANIFEST_NAME, schema.METADATA_NAME}
        if (is_media or is_note) and not (path.parent / schema.SOURCE_NOTE_NAME).is_file():
            report.add(WARNING, "staging.orphan_file", path,
                       f"{path.name} has no {schema.SOURCE_NOTE_NAME} next to it")


def validate_staging(
    config: Config,
    *,
    root: Path | None = None,
    check_archive: bool = True,
) -> ValidationReport:
    """Validate every staged source under the staging root."""
    from .pipeline import iter_source_dirs

    report = ValidationReport()
    staging_root = Path(root) if root is not None else config.output_root
    if not staging_root.exists():
        report.add(WARNING, "staging.missing_root", staging_root,
                   "the staging root does not exist yet - nothing to validate")
        return report

    seen: dict[str, Path] = {}
    for folder in iter_source_dirs(staging_root):
        report.sources_checked += 1
        source_id = validate_source_folder(report, folder, config)
        if source_id:
            if source_id in seen:
                report.add(ERROR, "staging.duplicate_source_id", folder,
                           f"source_id {source_id!r} is also used by {seen[source_id]}")
            else:
                seen[source_id] = folder

    _find_orphans(report, staging_root)

    if check_archive and config.archive.enabled:
        archive = Archive(config.archive_dir, enabled=True)
        for entry in archive:
            target = staging_root / entry.path
            if not (target / schema.SOURCE_NOTE_NAME).is_file():
                report.add(WARNING, "archive.dangling_entry", archive.index_path,
                           f"{entry.source_id} points to a missing folder: {entry.path}")
        for source_id, folder in sorted(seen.items(), key=lambda item: str(item[1])):
            if archive.get(source_id) is None:
                report.add(WARNING, "archive.missing_entry", folder,
                           f"{source_id} is staged but the archive index does not know it - "
                           "run 'validate.py --repair-archive' to add it (nothing is downloaded)")
    return report
