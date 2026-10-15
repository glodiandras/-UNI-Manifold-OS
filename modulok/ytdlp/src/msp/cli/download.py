"""``download.py`` - stage one URL, a batch file, a playlist, or a crawled listing page."""

from __future__ import annotations

import argparse
import sys

from ..archive import Archive
from ..crawl import create_fetcher
from ..downloader import check_dependencies, create_downloader, require_ytdlp
from ..errors import PipelineError
from ..integration import read_integration_status, run_handoff
from ..pipeline import (
    STATUS_DOWNLOADED,
    STATUS_FAILED,
    STATUS_SKIPPED,
    BatchSummary,
    UrlItem,
    ingest_crawl,
    ingest_many,
    ingest_playlist,
    ingest_url,
    looks_like_url_list,
    parse_url_list,
)
from . import EPILOG_COMMON, add_common_arguments, load_context, run_cli

DESCRIPTION = """\
Download a video and stage it as an Obsidian-compatible source.

For every source this creates:
    <Provider>/<Subject>/<Title>/video.*        the media file
                                 source.md      the source note (entry point)
                                 transcript.md  transcript or a pending placeholder
                                 metadata.json  curated metadata
                                 integration.json  machine-readable hand-off
"""

EXAMPLES = """\
examples:
  download.py "https://zanza.tv/tortenelem/az-okori-athen"
  download.py urls.txt --subject Történelem
  download.py "https://..." --dry-run          # plan only, no download
  download.py "https://.../playlist" --playlist --max-items 20
  download.py --crawl "https://zanza.tv/tortenelem"   # every video under a subject page
  download.py --check                          # dependency check only
  download.py "https://..." --integrate        # stage, then hand off to integration.command
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="download.py",
        description=DESCRIPTION,
        epilog=EXAMPLES + "\n" + EPILOG_COMMON,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "targets",
        nargs="*",
        metavar="URL|FILE",
        help="video URL(s), or a text file with one URL per line "
             "(optionally 'URL | Subject'; '#' starts a comment)",
    )
    parser.add_argument("--subject", metavar="NAME",
                        help="subject folder for every item in this run (overrides the heuristic)")
    parser.add_argument("--language", metavar="CODE",
                        help="content language to record when the provider does not report one")
    parser.add_argument("--force", action="store_true",
                        help="re-download even if the source is already staged")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would happen; nothing is downloaded or written")
    parser.add_argument("--playlist", action="store_true",
                        help="allow playlist/collection URLs (off by default, spec section 13)")
    parser.add_argument("--crawl", action="store_true",
                        help="treat each URL as a listing page (e.g. a subject or topic page) and "
                             "stage every video page below it; honours robots.txt and its Crawl-delay")
    parser.add_argument("--max-items", type=int, metavar="N",
                        help="item limit for this run with --playlist or --crawl "
                             "(default: playlist.max_items / crawl.max_items)")
    parser.add_argument("--no-archive", action="store_true",
                        help="do not read or write the download archive")
    parser.add_argument("--check", action="store_true",
                        help="print the dependency/configuration check and exit")
    hand_off = parser.add_mutually_exclusive_group()
    hand_off.add_argument("--integrate", action="store_true",
                          help="after staging, hand each source still 'pending' to integration.command "
                               "(the downstream integrator, e.g. the vault's media.py auto --staging)")
    hand_off.add_argument("--no-integrate", action="store_true",
                          help="do not hand off, even if integration.enabled is true")
    return add_common_arguments(parser)


def _run(args: argparse.Namespace) -> int:
    config, logger = load_context(args)

    if args.check:
        print(check_dependencies(config).render())
        print()
        print(config.describe())
        return 0

    if not args.targets:
        build_parser().print_help(sys.stderr)
        print("\nERROR: give at least one URL or a file with URLs.", file=sys.stderr)
        return 64

    if args.crawl and args.playlist:
        print("ERROR: --crawl and --playlist cannot be combined.", file=sys.stderr)
        return 64

    require_ytdlp(config)
    downloader = create_downloader(config)
    archive = Archive(config.archive_dir, enabled=config.archive.enabled and not args.no_archive)
    logger.debug("backend: %s %s", downloader.name, downloader.version or "")

    summary = BatchSummary()
    for target in args.targets:
        if args.crawl:
            pages = parse_url_list(target) if looks_like_url_list(target) else [UrlItem(url=target)]
            fetch = create_fetcher(config)
            for page in pages:
                batch = ingest_crawl(
                    page.url, config=config, downloader=downloader, archive=archive, logger=logger,
                    subject=args.subject, subject_hint=page.subject, force=args.force,
                    dry_run=args.dry_run, max_items=args.max_items, fetch=fetch,
                )
                summary.outcomes.extend(batch.outcomes)
        elif looks_like_url_list(target):
            items = parse_url_list(target)
            logger.info("Batch: %s (%d URLs)", target, len(items))
            batch = ingest_many(
                items, config=config, downloader=downloader, archive=archive, logger=logger,
                subject=args.subject, force=args.force, dry_run=args.dry_run,
            )
            summary.outcomes.extend(batch.outcomes)
        elif args.playlist:
            batch = ingest_playlist(
                target, config=config, downloader=downloader, archive=archive, logger=logger,
                subject=args.subject, force=args.force, dry_run=args.dry_run,
                max_items=args.max_items,
            )
            summary.outcomes.extend(batch.outcomes)
        else:
            summary.add(ingest_url(
                target, config=config, downloader=downloader, archive=archive, logger=logger,
                subject=args.subject, language=args.language, force=args.force, dry_run=args.dry_run,
            ))

    if summary.total > 1 or summary.failed:
        print()
        print(summary.render())
    if summary.failed:
        print("\nFailed items:", file=sys.stderr)
        for outcome in summary.outcomes:
            if outcome.status == STATUS_FAILED:
                print(f"  {outcome.url}\n    {outcome.message}", file=sys.stderr)
    if not args.dry_run and summary.downloaded:
        print(f"\nStaged under: {config.output_root}")
    if not args.dry_run and not args.no_integrate and (args.integrate or config.integration.enabled):
        _hand_off(summary, config=config, logger=logger)
    return 1 if summary.failed else 0


def _hand_off(summary: BatchSummary, *, config, logger) -> None:
    """One workflow (owner decision 2026-09-19): every staged source that is still 'pending' -
    freshly downloaded, or skipped because it was staged earlier - goes to the integrator.
    A failing integrator is reported, never turned into a failed download.

    ``in_review`` in the answer is not a failure: the integrator stopped to ask the owner where
    the video belongs or which notes it carries, and that answer is given in the receiving
    system, not here."""
    folders = []
    for outcome in summary.outcomes:
        if outcome.status in (STATUS_DOWNLOADED, STATUS_SKIPPED) and outcome.path:
            if read_integration_status(outcome.path) == "pending" and outcome.path not in folders:
                folders.append(outcome.path)
    if not folders:
        print("\nIntegration: nothing pending.")
        return
    print(f"\nIntegration: {len(folders)} source(s) -> {config.integration.command[0] if config.integration.command else '?'}")
    asking = 0
    for folder in folders:
        result = run_handoff(folder, config=config, logger=logger)
        print(f"  [{result.status}] {folder.name} (integration_status: {result.integration_status})")
        if result.integration_status == "in_review":
            asking += 1
        elif not result.ok and result.output_tail:
            print("    " + result.output_tail.strip().replace("\n", "\n    ")[-800:])
    if asking:
        print(f"  {asking} source(s) wait for your decision in the receiving system "
              f"(integration_status: in_review).")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_cli(_run, args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
