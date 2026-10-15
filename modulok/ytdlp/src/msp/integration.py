"""Hand-off of a staged source folder to a downstream integrator (owner decision 2026-09-19).

The owner's words: "Az a lényeg, hogy a ytdlp része legyen, mert ezáltal, ezt összeköthetjük
1 db workflowra (link bemenet -> transcript & videó -> videó, transcript & metadata integrálása
a kért programmal)" - one workflow: a link goes in, this pipeline stages the video, its metadata
and its transcript, and then the integration program takes over.

What this module does, and what it deliberately does not do:

* it runs ``integration.command`` from the config once per staged source folder, with every
  ``{folder}`` replaced by the folder's absolute path (and ``{project_root}`` by this
  repository's root), and reports the exit code and the tail of the output;
* it never reads or writes the vault itself. The command belongs to the receiving system (for the
  Manifold vault: ``media.py auto --staging {folder}``), which decides everything - placement,
  links, logging - under its own protocol, and records the result by setting
  ``integration_status`` in the folder's integration.json;
* a failed hand-off never turns a successful download into a failure: the staged folder stays
  valid, and ``integrate.py --pending`` retries it later.

``integration_status`` is how the receiving system answers back, and the three answers mean
different things here (schema: ``pending | in_review | integrated | rejected``):

``integrated``
    done - the source is in the vault.
``in_review``
    the integrator stopped and is **asking the owner** (it could not decide where the video
    belongs or which notes it should be linked to). Nothing is wrong, and re-running the
    hand-off would only repeat the question, so ``--pending`` leaves these alone; the answer is
    given in the receiving system's own interface. ``--retry-review`` hands them over again -
    for the case where the integrator lost the half-finished run.
``pending``
    not integrated yet (or the integrator failed before it could decide anything).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from . import schema
from .config import Config
from .errors import ConfigError
from .logging_setup import info_event, warn_event

STATUS_OK = "ok"
STATUS_FAILED = "failed"
STATUS_TIMEOUT = "timeout"

_TAIL_CHARS = 1500


@dataclass
class HandoffResult:
    folder: Path
    status: str
    returncode: int | None = None
    output_tail: str = ""
    integration_status: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK


def build_command(config: Config, folder: Path) -> list[str]:
    """The configured command with its placeholders substituted - no shell, no word splitting.

    ``{folder}`` is the staged source folder. ``{project_root}`` is this repository's root, so
    the command can name its neighbours on the same drive relatively (e.g.
    ``{project_root}/../../bin/mos``) and survives the drive being mounted elsewhere
    - the 2026-09-19, 2026-09-23 and 2026-09-24 moves each broke an absolute path here. An argument that
    starts with ``{project_root}`` is normalised, so logs show a plain path.
    """
    if not config.integration.command:
        raise ConfigError(
            "integration.command is not set",
            hint="Set integration.command in config/config.yaml (it must contain {folder}).",
        )
    target = str(Path(folder).resolve())
    root = str(config.project_root)
    out = []
    for part in config.integration.command:
        value = part.replace("{folder}", target).replace("{project_root}", root)
        out.append(os.path.normpath(value) if part.startswith("{project_root}") else value)
    return out


def read_integration_status(folder: Path) -> str | None:
    path = Path(folder) / schema.MANIFEST_NAME
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("integration_status")
    except (OSError, ValueError):
        return None


def run_handoff(
    folder: Path,
    *,
    config: Config,
    logger: logging.Logger,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> HandoffResult:
    """Hand one staged folder to the integrator. Never raises for a failing integrator."""
    folder = Path(folder)
    cmd = build_command(config, folder)
    info_event(logger, f"Integrating: {folder.name}", event_name="integration.start",
               folder=str(folder), command=cmd[0])
    try:
        proc = runner(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                      timeout=config.integration.timeout_seconds)
    except subprocess.TimeoutExpired:
        warn_event(logger, f"    integration timed out after {config.integration.timeout_seconds} s: {folder.name}",
                   event_name="integration.timeout", folder=str(folder))
        return HandoffResult(folder, STATUS_TIMEOUT, integration_status=read_integration_status(folder))
    except OSError as exc:
        warn_event(logger, f"    integration command could not start: {exc}",
                   event_name="integration.failed", folder=str(folder))
        return HandoffResult(folder, STATUS_FAILED, output_tail=str(exc),
                             integration_status=read_integration_status(folder))
    tail = ((proc.stdout or "") + (proc.stderr or ""))[-_TAIL_CHARS:]
    status = STATUS_OK if proc.returncode == 0 else STATUS_FAILED
    result = HandoffResult(folder, status, proc.returncode, tail, read_integration_status(folder))
    event = info_event if result.ok else warn_event
    # The tail goes into the event log too, not only to stdout: on 2026-09-19, 119 hand-offs stopped
    # with exit 2 and the reason could not be recovered afterwards, because only the code was logged.
    extra = {} if result.ok else {"output_tail": tail[-800:]}
    event(logger, f"    integration {'finished' if result.ok else 'stopped'} (exit {proc.returncode}, "
                  f"integration_status: {result.integration_status})",
          event_name="integration.done" if result.ok else "integration.stopped",
          folder=str(folder), returncode=proc.returncode, integration_status=result.integration_status, **extra)
    return result


def pending_folders(
    root: Path,
    subjects: Iterable[str] | None = None,
    statuses: Iterable[str] = ("pending",),
) -> list[Path]:
    """Staged source folders under ``root`` with one of ``statuses`` (default: ``pending``).

    ``in_review`` is deliberately not in the default: that folder is a question waiting for the
    owner in the receiving system, and handing it over again would only ask it a second time.
    """
    wanted = {s for s in subjects} if subjects else None
    keep = set(statuses)
    out = []
    for path in sorted(Path(root).rglob(schema.MANIFEST_NAME)):
        folder = path.parent
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("integration_status") not in keep:
            continue
        if wanted and data.get("suggested_subject") not in wanted:
            continue
        out.append(folder)
    return out


def status_counts(root: Path, subjects: Iterable[str] | None = None) -> dict[str, int]:
    """How many staged sources stand in each ``integration_status`` (unreadable ones: ``?``)."""
    wanted = {s for s in subjects} if subjects else None
    out: dict[str, int] = {}
    for path in sorted(Path(root).rglob(schema.MANIFEST_NAME)):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            out["?"] = out.get("?", 0) + 1
            continue
        if wanted and data.get("suggested_subject") not in wanted:
            continue
        key = str(data.get("integration_status") or "?")
        out[key] = out.get(key, 0) + 1
    return out
