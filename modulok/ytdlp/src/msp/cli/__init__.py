"""Command line entry points.

Every CLI shares the same skeleton: parse arguments, load the config, set up
logging, run, and translate a typed :class:`~msp.errors.PipelineError` into a
readable message plus a meaningful exit code.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Callable

from ..config import Config
from ..errors import PipelineError
from ..logging_setup import configure, get_logger

EPILOG_COMMON = (
    "Configuration: config/config.yaml (override with --config or $MSP_CONFIG).\n"
    "This tool writes only into the staging repository, never into a production vault."
)


def add_common_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    from .. import __version__

    parser.add_argument("--version", action="version",
                        version=f"multimedia-source-pipeline {__version__}")
    parser.add_argument("--config", metavar="PATH", help="alternative config file")
    parser.add_argument("--output-root", metavar="PATH", help="override output_root from the config")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug output on the terminal")
    parser.add_argument("-q", "--quiet", action="store_true", help="warnings and errors only")
    return parser


def load_context(args: argparse.Namespace) -> tuple[Config, logging.Logger]:
    """Load the configuration and configure logging for a CLI run."""
    config = Config.load(getattr(args, "config", None), output_root=getattr(args, "output_root", None))
    logger = configure(
        log_dir=config.log_dir,
        level=config.logging.level,
        json_events=config.logging.json_events,
        quiet=getattr(args, "quiet", False),
        verbose=getattr(args, "verbose", False),
    )
    logger.debug("config: %s", config.config_path or "<defaults>")
    logger.debug("output_root: %s", config.output_root)
    return config, logger


def run_cli(entry: Callable[[argparse.Namespace], int], args: argparse.Namespace) -> int:
    """Execute a CLI body with uniform error handling (spec section 21)."""
    try:
        return entry(args)
    except PipelineError as exc:
        get_logger().debug("pipeline error", exc_info=True)
        print(f"ERROR: {exc.render()}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("\nInterrupted. Partial downloads were kept; re-run the same command to resume.",
              file=sys.stderr)
        return 130
    except BrokenPipeError:  # pragma: no cover - `| head` and friends
        return 0


def resolve_existing_path(value: str, *, what: str = "path") -> Path:
    path = Path(value).expanduser()
    if not path.exists():
        raise PipelineError(f"{what} does not exist: {path}")
    return path
