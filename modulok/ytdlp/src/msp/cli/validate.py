"""``validate.py`` - structural check of the staging repository."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..archive import rebuild_missing_entries
from ..logging_setup import info_event, warn_event
from ..validation import validate_staging
from . import EPILOG_COMMON, add_common_arguments, load_context, run_cli

DESCRIPTION = """\
Check that every staged source is complete and internally consistent:
required frontmatter fields, referenced files, duplicate source ids, valid
metadata JSON, timestamp format in transcripts, and manifest agreement.

Exit code: 0 when there is no ERROR, 1 otherwise (--strict also fails on
warnings), so it can be used in a pre-integration check.

--repair-archive additionally rebuilds index entries that a staged folder has
but the archive does not (an interrupted run, or two runs overwriting each
other's index). It reads the staged folders only: nothing is downloaded and no
entry is ever removed.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate.py",
        description=DESCRIPTION,
        epilog=EPILOG_COMMON,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("path", nargs="?", metavar="PATH",
                        help="staging root or a single source folder (default: output_root)")
    parser.add_argument("--json", action="store_true", dest="as_json", help="JSON report")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    parser.add_argument("--no-archive-check", action="store_true",
                        help="skip checking the download archive against the tree")
    parser.add_argument("--repair-archive", action="store_true",
                        help="add a missing archive entry for every staged folder, from the "
                             "folder itself (no download, nothing removed)")
    return add_common_arguments(parser)


def _run(args: argparse.Namespace) -> int:
    config, logger = load_context(args)
    root = Path(args.path).expanduser() if args.path else None

    if args.repair_archive:
        rebuilt = rebuild_missing_entries(config)
        for entry in rebuilt.restored:
            info_event(logger, f"    archive entry restored: {entry.source_id} -> {entry.path}",
                       event_name="archive.entry_restored", source_id=entry.source_id, path=entry.path)
        for path, reason in rebuilt.unreadable:
            warn_event(logger, f"    cannot read {path}: {reason}",
                       event_name="archive.unreadable", path=path)
        info_event(logger, f"archive: {len(rebuilt.restored)} entry(ies) restored from the staging tree",
                   event_name="archive.repaired", restored=len(rebuilt.restored),
                   unreadable=len(rebuilt.unreadable))
    report = validate_staging(config, root=root, check_archive=not args.no_archive_check)

    if args.as_json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(report.render())

    if report.errors:
        return 1
    if args.strict and report.warnings:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_cli(_run, args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
