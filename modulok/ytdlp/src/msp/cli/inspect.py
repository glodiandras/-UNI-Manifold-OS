"""``inspect.py`` - look at a URL (or at the staging tree) without downloading.

The format table answers the question that decides download quality: *which
resolutions does this site actually offer, and which of them can be assembled
into one file here?*
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..downloader import create_downloader, is_playlist, require_ytdlp
from ..fsio import human_size, read_json
from ..metadata import best_available_height, iter_formats, progressive_formats, resolution_of
from ..naming import make_source_id
from ..notes import read_note
from ..pipeline import iter_source_dirs, plan_target_dir, validate_url
from ..providers import resolve_provider
from ..schema import MANIFEST_NAME
from ..subjects import resolve_subject
from ..timestamps import format_timestamp
from . import EPILOG_COMMON, add_common_arguments, load_context, run_cli

DESCRIPTION = """\
Inspect a video URL (metadata, available formats, planned staging path) or
summarise what is already staged. Nothing is downloaded and nothing is written.
"""

EXAMPLES = """\
examples:
  inspect.py "https://zanza.tv/tortenelem/az-okori-athen"
  inspect.py "https://..." --formats     # full format table
  inspect.py --staging                   # overview of the staging tree
  inspect.py "https://..." --json        # machine readable
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="inspect.py",
        description=DESCRIPTION,
        epilog=EXAMPLES + "\n" + EPILOG_COMMON,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", nargs="?", help="video URL to inspect")
    parser.add_argument("--formats", action="store_true", help="list every format, not just pre-muxed ones")
    parser.add_argument("--staging", action="store_true", help="summarise the staging tree instead")
    parser.add_argument("--subject", metavar="NAME", help="subject to assume when planning the path")
    parser.add_argument("--json", action="store_true", dest="as_json", help="JSON output")
    return add_common_arguments(parser)


def _inspect_staging(config, as_json: bool) -> int:
    rows = []
    for folder in iter_source_dirs(config.output_root):
        try:
            front, _ = read_note(folder / "source.md")
        except Exception as exc:  # noqa: BLE001 - reported per row
            rows.append({"path": str(folder), "error": str(exc)})
            continue
        manifest_path = folder / MANIFEST_NAME
        manifest = read_json(manifest_path) if manifest_path.is_file() else {}
        transcript_status = "?"
        transcript = folder / str(front.get("transcript_file") or "transcript.md")
        if transcript.is_file():
            try:
                tfront, _ = read_note(transcript)
                transcript_status = str(tfront.get("transcript_status") or "?")
            except Exception:  # noqa: BLE001 - shown as '?'
                transcript_status = "unreadable"
        rows.append({
            "source_id": front.get("source_id"),
            "title": front.get("title"),
            "provider": front.get("provider"),
            "subject": front.get("subject"),
            "transcript_status": transcript_status,
            "integration_status": manifest.get("integration_status") if isinstance(manifest, dict) else None,
            "nn_anchorable": manifest.get("nn_anchorable") if isinstance(manifest, dict) else None,
            "path": str(folder.relative_to(config.output_root)),
        })

    if as_json:
        print(json.dumps({"staging_root": str(config.output_root), "sources": rows},
                         ensure_ascii=False, indent=2))
        return 0

    print(f"Staging root: {config.output_root}")
    print(f"Sources: {len(rows)}")
    if rows:
        print()
        print(f"{'source_id':24} {'transcript':12} {'subject':16} title")
        print("-" * 96)
        for row in rows:
            if row.get("error"):
                print(f"{'?':24} {'?':12} {'?':16} {row['path']}  ({row['error']})")
                continue
            print(
                f"{str(row['source_id'])[:24]:24} {str(row['transcript_status'])[:12]:12} "
                f"{str(row.get('subject') or '-')[:16]:16} {row['title']}"
            )
        pending = sum(1 for row in rows if row.get("transcript_status") == "pending")
        undecided = sum(1 for row in rows if row.get("nn_anchorable") is None and not row.get("error"))
        print()
        print(f"transcripts pending: {pending}")
        print(f"nn_anchorable undecided: {undecided}  (vault owner's decision, see CLAUDE.md)")
    return 0


def _inspect_url(args, config, logger) -> int:
    url = validate_url(args.url)
    require_ytdlp(config)
    downloader = create_downloader(config, progress=False)
    info = downloader.probe(url, allow_playlist=True)

    if is_playlist(info):
        entries = [entry for entry in (info.get("entries") or []) if isinstance(entry, dict)]
        payload = {
            "type": "playlist",
            "title": info.get("title"),
            "count": len(entries),
            "entries": [
                {"title": entry.get("title"), "url": entry.get("webpage_url") or entry.get("url")}
                for entry in entries
            ],
        }
        if args.as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Playlist: {payload['title']}  ({payload['count']} items)")
            for entry in payload["entries"]:
                print(f"  - {entry['title'] or '?'}\n    {entry['url']}")
            print("\nDownload it with:  download.py URL --playlist")
        return 0

    provider = resolve_provider(url, info, config)
    video_id = info.get("id")
    source_id = make_source_id(provider.slug, str(video_id) if video_id else None,
                               info.get("webpage_url") or url)
    subject = resolve_subject(url, info, config, explicit=args.subject)
    target = plan_target_dir(
        config, provider_folder=provider.folder_name, subject=subject.name,
        title=str(info.get("title") or source_id), source_id=source_id,
    )
    progressive = progressive_formats(info)
    duration = info.get("duration")

    payload = {
        "type": "video",
        "source_id": source_id,
        "title": info.get("title"),
        "provider": provider.display_name,
        "extractor": provider.extractor,
        "url": info.get("webpage_url") or url,
        "duration_seconds": duration,
        "duration": format_timestamp(duration) if isinstance(duration, (int, float)) else None,
        "uploader": info.get("uploader"),
        "upload_date": info.get("upload_date"),
        "language": info.get("language"),
        "resolution_reported": resolution_of(info),
        "subtitles": sorted((info.get("subtitles") or {}).keys()),
        "automatic_captions": sorted((info.get("automatic_captions") or {}).keys()),
        "suggested_subject": subject.name,
        "subject_source": subject.source,
        "planned_path": str(target),
        "format_selector": config.video.effective_format_selector,
        "progressive_formats": [
            {"format_id": fmt.format_id, "ext": fmt.ext, "resolution": fmt.resolution,
             "fps": fmt.fps, "filesize": fmt.filesize}
            for fmt in progressive
        ],
    }
    if args.as_json:
        if args.formats:
            payload["all_formats"] = [
                {"format_id": fmt.format_id, "ext": fmt.ext, "resolution": fmt.resolution,
                 "vcodec": fmt.vcodec, "acodec": fmt.acodec, "progressive": fmt.is_progressive}
                for fmt in iter_formats(info)
            ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"Title       : {payload['title']}")
    print(f"Provider    : {payload['provider']}  (extractor: {payload['extractor']})")
    print(f"Source ID   : {source_id}")
    print(f"Duration    : {payload['duration'] or '?'}")
    print(f"Uploader    : {payload['uploader'] or '-'}")
    print(f"Language    : {payload['language'] or 'not reported'}")
    print(f"Subtitles   : {', '.join(payload['subtitles']) or 'none'}"
          + (f"   (auto: {', '.join(payload['automatic_captions'])})" if payload['automatic_captions'] else ""))
    print(f"Subject     : {subject.name}  (from: {subject.source})")
    print(f"Planned path: {target}")
    print(f"Selector    : {payload['format_selector']}")
    print()
    merge = config.video.allow_merge
    best_available = best_available_height(info)
    best_muxed = progressive[0].height if progressive else None
    usable = ([fmt for fmt in iter_formats(info) if fmt.height and not fmt.is_storyboard]
              if merge else progressive)
    usable = sorted(usable, key=lambda fmt: fmt.height or 0, reverse=True)[:12]
    if usable:
        print("Usable formats"
              + (" (video-only streams are muxed with the best audio):" if merge
                 else " - pre-muxed only, video.allow_merge is false:"))
        print(f"  {'id':10} {'ext':6} {'resolution':12} {'fps':>5}  {'size':>10}  kind")
        for fmt in usable:
            kind = "muxed" if fmt.is_progressive else "video-only"
            print(f"  {fmt.format_id[:10]:10} {str(fmt.ext or '?')[:6]:6} {fmt.resolution:12} "
                  f"{f'{fmt.fps:.0f}' if fmt.fps else '-':>5}  {human_size(fmt.filesize):>10}  {kind}")
        reachable = best_available if merge else best_muxed
        if reachable and reachable < config.video.max_height:
            if best_available and reachable >= best_available:
                print(f"\n  NOTE: {reachable}p is the highest resolution this video is "
                      "published in - the target is unreachable for this source, "
                      "not for the pipeline.")
            else:
                print(f"\n  NOTE: only {reachable}p is reachable, below the {config.video.max_height}p "
                      f"target (this video offers up to {best_available}p).\n"
                      "        Enable video.allow_merge, and check FFmpeg + the JS runtime "
                      "with:  python3 scripts/download.py --check")
    else:
        print("No usable video format found for this URL.")
    if args.formats:
        print("\nAll formats:")
        print(f"  {'id':12} {'ext':6} {'resolution':12} {'vcodec':12} {'acodec':12} muxed")
        for fmt in iter_formats(info):
            print(f"  {fmt.format_id[:12]:12} {str(fmt.ext or '?')[:6]:6} {fmt.resolution:12} "
                  f"{str(fmt.vcodec or '-')[:12]:12} {str(fmt.acodec or '-')[:12]:12} "
                  f"{'yes' if fmt.is_progressive else 'no'}")
    return 0


def _run(args: argparse.Namespace) -> int:
    config, logger = load_context(args)
    if args.staging or not args.url:
        if not args.staging and not args.url:
            build_parser().print_help(sys.stderr)
            print("\nERROR: give a URL, or use --staging.", file=sys.stderr)
            return 64
        return _inspect_staging(config, args.as_json)
    return _inspect_url(args, config, logger)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_cli(_run, args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
