"""``transcribe.py`` - fill in transcript.md for already staged sources."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..config import Config
from ..errors import PipelineError, TranscriptionError
from ..notes import read_note
from ..pipeline import iter_source_dirs
from ..schema import SOURCE_NOTE_NAME, TRANSCRIPT_NOTE_NAME
from ..transcription.registry import AUTO_ORDER
from ..transcription import describe_backends, select_backend, write_transcript
from . import EPILOG_COMMON, add_common_arguments, load_context, run_cli

DESCRIPTION = """\
Generate transcript.md for staged sources with a pluggable, local backend.

Transcription is separate from downloading on purpose: a download only ever
creates a 'pending' placeholder. Nothing is ever invented - when no backend is
available the transcript stays pending and the command fails loudly.

Fidelity: the text is written exactly as the engine produced it (no punctuation
repair, no rephrasing), because a later integration step may need to quote it
character for character.
"""

EXAMPLES = """\
examples:
  transcribe.py --list-backends
  transcribe.py "staging/Zanza/Történelem/Az ókori Athén"
  transcribe.py "staging/.../video.mp4" --backend faster_whisper
  transcribe.py --pending --language hu
  transcribe.py --pending --dry-run
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="transcribe.py",
        description=DESCRIPTION,
        epilog=EXAMPLES + "\n" + EPILOG_COMMON,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("paths", nargs="*", metavar="PATH",
                        help="source folder(s) or media file(s) inside the staging tree")
    parser.add_argument("--pending", action="store_true",
                        help="process every staged source whose transcript is still pending")
    parser.add_argument("--backend", metavar="NAME",
                        help="subtitles | faster_whisper | whisper_cpp | auto (default: config)")
    parser.add_argument("--language", metavar="CODE", help="language hint for the engine")
    parser.add_argument("--group-seconds", type=float, default=0.0, metavar="N",
                        help="merge segments into blocks of about N seconds (0 = one block per segment)")
    parser.add_argument("--force", action="store_true",
                        help="re-transcribe even if the transcript is already completed")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would be transcribed, write nothing")
    parser.add_argument("--list-backends", action="store_true",
                        help="show which transcription backends are usable and why")
    return add_common_arguments(parser)


def _resolve_folder(value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_file():
        path = path.parent
    if not path.is_dir():
        raise TranscriptionError(f"Not a folder: {value}")
    if not (path / SOURCE_NOTE_NAME).is_file():
        raise TranscriptionError(
            f"{path} is not a staged source folder ({SOURCE_NOTE_NAME} is missing).",
            hint="Pass the folder that contains source.md, or use --pending.",
        )
    return path


def _transcript_status(folder: Path) -> str:
    path = folder / TRANSCRIPT_NOTE_NAME
    if not path.is_file():
        return "missing"
    try:
        front, _ = read_note(path)
    except PipelineError:
        return "unreadable"
    return str(front.get("transcript_status") or "pending")


def _media_path(folder: Path) -> Path:
    front, _ = read_note(folder / SOURCE_NOTE_NAME)
    media_file = str(front.get("media_file") or "")
    candidate = folder / media_file if media_file else None
    if candidate and candidate.is_file():
        return candidate
    raise TranscriptionError(
        f"The media file is missing in {folder}" + (f": {media_file}" if media_file else ""),
        hint="Re-download the source with download.py.",
    )


def _collect_targets(args: argparse.Namespace, config: Config) -> list[Path]:
    folders: list[Path] = [_resolve_folder(value) for value in args.paths]
    if args.pending:
        for folder in iter_source_dirs(config.output_root):
            if folder in folders:
                continue
            if _transcript_status(folder) in {"pending", "missing", "failed"}:
                folders.append(folder)
    return folders


def _run(args: argparse.Namespace) -> int:
    config, logger = load_context(args)

    if args.list_backends:
        print(describe_backends(config))
        print("\nSelection order for 'auto': " + " -> ".join(AUTO_ORDER))
        return 0

    if not args.paths and not args.pending:
        build_parser().print_help(sys.stderr)
        print("\nERROR: give a path, or use --pending.", file=sys.stderr)
        return 64

    folders = _collect_targets(args, config)
    if not folders:
        print("Nothing to transcribe.")
        return 0

    done = 0
    skipped = 0
    failed = 0
    for folder in folders:
        status = _transcript_status(folder)
        if status == "completed" and not args.force:
            logger.info("SKIPPED - transcript already completed: %s", folder.name)
            skipped += 1
            continue
        try:
            media = _media_path(folder)
            backend = select_backend(config, args.backend, folder)
            if args.dry_run:
                logger.info("DRY-RUN would transcribe %s with backend '%s'", folder.name, backend.name)
                done += 1
                continue
            logger.info("Transcribing: %s  (backend: %s)", folder.name, backend.name)
            result = backend.transcribe(media, language=args.language or config.transcript.language,
                                        folder=folder)
            if config.transcript.postprocess:
                logger.warning(
                    "    transcript.postprocess is on, but no post-processing step is implemented; "
                    "the text is written verbatim and transcript_postprocessed stays false."
                )
            write_transcript(folder, result, config=config,
                             group_seconds=args.group_seconds, logger=logger)
            done += 1
        except PipelineError as exc:
            logger.error("FAILED %s: %s", folder.name, exc.message)
            if exc.hint:
                logger.warning("  -> %s", exc.hint)
            failed += 1

    print()
    print(f"Transcribed: {done}")
    print(f"Skipped: {skipped}")
    print(f"Failed: {failed}")
    print(f"Total: {len(folders)}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_cli(_run, args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
