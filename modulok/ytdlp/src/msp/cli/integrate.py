"""``integrate.py`` - hand staged sources to the downstream integrator (owner decision 2026-09-19)."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..integration import (
    pending_folders,
    read_integration_status,
    run_handoff,
    status_counts,
)
from . import EPILOG_COMMON, add_common_arguments, load_context, run_cli

DESCRIPTION = """\
Hand staged source folders to integration.command - the second half of the one
workflow the owner asked for: link -> transcript & video (download.py) ->
video, transcript & metadata integrated (the integrator).

This tool never reads or writes a vault. It only starts the configured
command, once per folder, with {folder} replaced by the folder's path; the
integrator decides everything under its own rules and writes its answer back
into integration.json:

  integrated   done, the source is in the receiving system
  in_review    the integrator is asking you - it could not decide where the
               video belongs, or which notes it carries. Answer it in the
               receiving system's own interface; --pending skips these, so a
               re-run does not repeat the question (--retry-review overrides)
  pending      not integrated yet

  integrate.py FOLDER [FOLDER ...]      the given source folders
  integrate.py --pending                every folder still 'pending' under output_root
  integrate.py --pending --subject Irodalom --limit 5
  integrate.py --status                 what stands where (no hand-off)
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="integrate.py",
        description=DESCRIPTION,
        epilog=EPILOG_COMMON,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("folders", nargs="*", metavar="FOLDER", help="staged source folder(s)")
    parser.add_argument("--pending", action="store_true",
                        help="every source folder whose integration_status is 'pending'")
    parser.add_argument("--retry-review", action="store_true",
                        help="with --pending: hand off the 'in_review' folders as well (they are "
                             "questions waiting for you, so this only helps when the integrator "
                             "lost the half-finished run)")
    parser.add_argument("--status", action="store_true",
                        help="print how many staged sources stand in each integration_status, "
                             "and hand off nothing")
    parser.add_argument("--subject", action="append", metavar="NAME",
                        help="with --pending or --status: only this subject (repeatable)")
    parser.add_argument("--limit", type=int, metavar="N", help="with --pending: at most N folders")
    parser.add_argument("--dry-run", action="store_true", help="list what would be handed off")
    return add_common_arguments(parser)


def _print_status(config, subjects) -> None:
    counts = status_counts(config.output_root, subjects)
    total = sum(counts.values())
    order = ["integrated", "in_review", "pending", "rejected", "?"]
    line = " · ".join(f"{name} {counts[name]}" for name in order if counts.get(name))
    print(f"{total} staged source(s) under {config.output_root}")
    print(f"  {line or 'nothing'}")
    if counts.get("in_review"):
        print(f"  {counts['in_review']} source(s) wait for your decision in the receiving system "
              f"(where the video belongs, or which notes it carries).")


def _run(args: argparse.Namespace) -> int:
    config, logger = load_context(args)
    if args.status:
        _print_status(config, args.subject)
        return 0
    if args.pending:
        statuses = ("pending", "in_review") if args.retry_review else ("pending",)
        folders = pending_folders(config.output_root, args.subject, statuses)
    else:
        folders = [Path(f).expanduser().resolve() for f in args.folders]
    if args.limit is not None:
        folders = folders[: args.limit]
    if not folders:
        print("Nothing to integrate." if args.pending else "Give a source folder, --pending or --status.")
        if args.pending:
            _print_status(config, args.subject)
        return 0 if args.pending else 64
    failed = 0
    after: list[str | None] = []
    for folder in folders:
        if args.dry_run:
            print(f"  would hand off: {folder}  (integration_status: {read_integration_status(folder)})")
            continue
        result = run_handoff(folder, config=config, logger=logger)
        print(f"  [{result.status}] {folder.name} (integration_status: {result.integration_status})")
        after.append(result.integration_status)
        # 'in_review' is the integrator asking the owner, not a failure: the run stopped on
        # purpose, and the answer is given in the receiving system.
        if not result.ok and result.integration_status != "in_review":
            failed += 1
            if result.output_tail:
                print("    " + result.output_tail.strip().replace("\n", "\n    ")[-800:])
    if not args.dry_run:
        done = sum(1 for s in after if s == "integrated")
        asking = sum(1 for s in after if s == "in_review")
        print(f"\nHanded off: {len(folders)} · integrated: {done} · waiting for your decision: "
              f"{asking} · failed: {failed}")
        if asking:
            print("The integrator could not decide on its own for those - answer it in the "
                  "receiving system's interface.")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_cli(_run, args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
