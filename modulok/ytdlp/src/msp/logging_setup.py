"""Structured logging: a readable terminal, a full text log, a JSONL event log.

* terminal - short lines, no timestamps, warnings and errors marked;
* ``logs/pipeline-YYYY-MM-DD.log`` - everything, with timestamps;
* ``logs/events.jsonl`` - one JSON object per event, for later analysis
  (which sources failed, what resolution each download really got, ...).
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER_NAME = "msp"

_LEVEL_PREFIX = {
    logging.DEBUG: "debug: ",
    logging.INFO: "",
    logging.WARNING: "WARNING: ",
    logging.ERROR: "ERROR: ",
    logging.CRITICAL: "CRITICAL: ",
}


class ConsoleFormatter(logging.Formatter):
    """Terse, human-facing output (spec section 20)."""

    def format(self, record: logging.LogRecord) -> str:
        prefix = _LEVEL_PREFIX.get(record.levelno, "")
        return f"{prefix}{record.getMessage()}"


class JsonlHandler(logging.Handler):
    """Append one JSON object per record to logs/events.jsonl."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload: dict[str, Any] = {
                "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
                "level": record.levelname,
                "event": getattr(record, "event", record.name),
                "message": record.getMessage(),
            }
            fields = getattr(record, "fields", None)
            if isinstance(fields, dict):
                for key, value in fields.items():
                    if key not in payload:
                        payload[key] = _jsonable(value)
            if record.exc_info:
                payload["exception"] = self.format(record)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:  # pragma: no cover - logging must never break a run
            self.handleError(record)


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return str(value)


def configure(
    *,
    log_dir: Path | None = None,
    level: str = "INFO",
    json_events: bool = True,
    quiet: bool = False,
    verbose: bool = False,
) -> logging.Logger:
    """Configure and return the pipeline logger. Safe to call more than once."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    console_level = logging.WARNING if quiet else (logging.DEBUG if verbose else logging.INFO)
    console = logging.StreamHandler(stream=sys.stderr)
    console.setLevel(console_level)
    console.setFormatter(ConsoleFormatter())
    logger.addHandler(console)

    if log_dir is not None:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            file_level = getattr(logging, str(level).upper(), logging.INFO)
            day = datetime.now().strftime("%Y-%m-%d")
            file_handler = logging.FileHandler(log_dir / f"pipeline-{day}.log", encoding="utf-8")
            file_handler.setLevel(file_level)
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)-8s %(name)s %(message)s")
            )
            logger.addHandler(file_handler)
            if json_events:
                jsonl = JsonlHandler(log_dir / "events.jsonl")
                jsonl.setLevel(file_level)
                logger.addHandler(jsonl)
        except OSError as exc:  # pragma: no cover - keep running without file logs
            logger.warning("Cannot write logs to %s: %s", log_dir, exc)
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    return logging.getLogger(LOGGER_NAME if not name else f"{LOGGER_NAME}.{name}")


def event(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    event: str,
    **fields: Any,
) -> None:
    """Log a message that also carries machine-readable fields."""
    logger.log(level, message, extra={"event": event, "fields": fields})


def info_event(logger: logging.Logger, message: str, *, event_name: str, **fields: Any) -> None:
    event(logger, logging.INFO, message, event=event_name, **fields)


def warn_event(logger: logging.Logger, message: str, *, event_name: str, **fields: Any) -> None:
    event(logger, logging.WARNING, message, event=event_name, **fields)


def error_event(logger: logging.Logger, message: str, *, event_name: str, **fields: Any) -> None:
    event(logger, logging.ERROR, message, event=event_name, **fields)
