"""The hand-off to the downstream integrator (owner decision 2026-09-19).

What is pinned here: the pipeline only starts the configured command (no shell, {folder}
substituted), never touches anything but that; a failing or hanging integrator never turns a
download into a failure; only 'pending' sources are handed off; the config refuses a hand-off
that could not work. No network, no vault: the integrator is a stub script.
"""

import json
import subprocess
import sys

import pytest
from conftest import FakeDownloader, TAXONOMY, make_config

from msp import integration
from msp.cli import download as download_cli
from msp.cli import integrate as integrate_cli
from msp.errors import ConfigError

URL = "https://zanza.tv/tortenelem/az-okori-athen"

# The stub integrator: marks the folder integrated, or fails when STUB_EXIT is set. STUB_STATUS
# writes another integration_status - 'in_review' is the real integrator stopping to ask the owner
# (it exits non-zero, because its run did not finish).
STUB = """\
import json, os, pathlib, sys
folder = pathlib.Path(sys.argv[1])
(folder.parent / "handed-off.txt").open("a", encoding="utf-8").write(folder.name + "\\n")
code = int(os.environ.get("STUB_EXIT", "0"))
status = os.environ.get("STUB_STATUS") or ("integrated" if code == 0 else "")
if status:
    p = folder / "integration.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["integration_status"] = status
    p.write_text(json.dumps(d), encoding="utf-8")
print("stub done")
sys.exit(code)
"""

CONFIG_YAML = """
output_root: "./staging"
organization:
  provider_folder: true
  subject_folder: true
  default_subject: "Besorolatlan"
  provider_names:
    zanza.tv: "Zanza"
subjects:
  taxonomy:
{taxonomy}
  aliases:
    tortenelem: "Történelem"
logging:
  dir: "./logs"
  level: "DEBUG"
  json_events: false
integration:
  enabled: {enabled}
  command: ["{python}", "{stub}", "{{folder}}"]
  timeout_seconds: 30
"""


def _project(tmp_path, monkeypatch, enabled=False):
    (tmp_path / "config").mkdir()
    stub = tmp_path / "stub.py"
    stub.write_text(STUB, encoding="utf-8")
    (tmp_path / "config" / "config.yaml").write_text(CONFIG_YAML.format(
        taxonomy="\n".join(f'    - "{name}"' for name in TAXONOMY),
        enabled=str(enabled).lower(), python=sys.executable, stub=stub), encoding="utf-8")
    monkeypatch.setenv("MSP_PROJECT_ROOT", str(tmp_path))
    downloader = FakeDownloader()
    monkeypatch.setattr(download_cli, "create_downloader", lambda config, **kw: downloader)
    monkeypatch.setattr(download_cli, "require_ytdlp", lambda config: None)
    return tmp_path


def _folder(root):
    return root / "staging" / "Zanza" / "Történelem" / "Az ókori Athén"


def _status(folder):
    return json.loads((folder / "integration.json").read_text(encoding="utf-8"))["integration_status"]


# --- config -----------------------------------------------------------------

def test_integration_is_off_by_default(tmp_path):
    config = make_config(tmp_path)
    assert config.integration.enabled is False and config.integration.command == ()


def test_enabled_without_a_command_is_refused(tmp_path):
    with pytest.raises(ConfigError):
        make_config(tmp_path, integration={"enabled": True})


def test_a_command_without_the_folder_placeholder_is_refused(tmp_path):
    with pytest.raises(ConfigError):
        make_config(tmp_path, integration={"command": ["integrator", "--all"]})


def test_build_command_substitutes_every_placeholder_without_a_shell(tmp_path):
    config = make_config(tmp_path, integration={"command": ["tool", "--staging", "{folder}", "x={folder}"]})
    folder = tmp_path / "A folder with spaces; and $(no) shell"
    cmd = integration.build_command(config, folder)
    assert cmd == ["tool", "--staging", str(folder.resolve()), f"x={folder.resolve()}"]


def test_build_command_resolves_project_root_relative_neighbours(tmp_path):
    config = make_config(tmp_path, integration={
        "command": ["{project_root}/../OS/venv/bin/python", "-B", "{project_root}/../Vault/media.py",
                    "--staging", "{folder}", "keep={project_root}"]})
    folder = tmp_path / "src"
    cmd = integration.build_command(config, folder)
    parent = config.project_root.parent
    assert cmd[0] == str(parent / "OS" / "venv" / "bin" / "python")
    assert cmd[2] == str(parent / "Vault" / "media.py")
    assert cmd[4] == str(folder.resolve())
    assert cmd[5] == f"keep={config.project_root}"  # only leading placeholders are normalised


# --- run_handoff ------------------------------------------------------------

def test_a_stopped_integrator_logs_its_output_tail(tmp_path, caplog):
    config = make_config(tmp_path, integration={"command": ["tool", "{folder}"]})
    import logging
    logger = logging.getLogger("msp.test.tail")
    with caplog.at_level(logging.INFO, logger="msp.test.tail"):
        integration.run_handoff(tmp_path, config=config, logger=logger,
                                runner=lambda cmd, **kw: subprocess.CompletedProcess(cmd, 2, "", "the reason why"))
    stopped = [r for r in caplog.records if getattr(r, "event", None) == "integration.stopped"]
    assert len(stopped) == 1
    assert "the reason why" in stopped[0].fields["output_tail"]


def test_a_failing_integrator_is_reported_not_raised(tmp_path):
    config = make_config(tmp_path, integration={"command": ["tool", "{folder}"]})
    result = integration.run_handoff(
        tmp_path, config=config, logger=__import__("logging").getLogger("t"),
        runner=lambda cmd, **kw: subprocess.CompletedProcess(cmd, 3, "", "boom"))
    assert (result.status, result.returncode, result.ok) == ("failed", 3, False)
    assert "boom" in result.output_tail


def test_a_hanging_integrator_times_out(tmp_path):
    config = make_config(tmp_path, integration={"command": ["tool", "{folder}"], "timeout_seconds": 1})

    def hang(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])

    result = integration.run_handoff(tmp_path, config=config,
                                     logger=__import__("logging").getLogger("t"), runner=hang)
    assert result.status == "timeout"


def test_pending_folders_filters_status_and_subject(tmp_path):
    for name, status, subject in (("a", "pending", "Irodalom"), ("b", "integrated", "Irodalom"),
                                  ("c", "pending", "Történelem")):
        (tmp_path / name).mkdir()
        (tmp_path / name / "integration.json").write_text(
            json.dumps({"integration_status": status, "suggested_subject": subject}), encoding="utf-8")
    assert [p.name for p in integration.pending_folders(tmp_path)] == ["a", "c"]
    assert [p.name for p in integration.pending_folders(tmp_path, ["Irodalom"])] == ["a"]


# --- the one workflow: download.py --integrate ------------------------------

def test_download_with_integrate_hands_off_the_staged_folder(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, monkeypatch)
    assert download_cli.main([URL, "--integrate"]) == 0
    folder = _folder(root)
    assert _status(folder) == "integrated"
    assert "[ok] Az ókori Athén" in capsys.readouterr().out


def test_download_without_the_flag_does_not_hand_off(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch)
    assert download_cli.main([URL]) == 0
    assert _status(_folder(root)) == "pending"
    assert not (_folder(root).parent / "handed-off.txt").exists()


def test_enabled_config_hands_off_unless_no_integrate(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch, enabled=True)
    assert download_cli.main([URL, "--no-integrate"]) == 0
    assert _status(_folder(root)) == "pending"
    assert download_cli.main([URL]) == 0                 # skipped download, still pending -> handed off
    assert _status(_folder(root)) == "integrated"


def test_a_failing_integrator_keeps_the_download_successful(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, monkeypatch)
    monkeypatch.setenv("STUB_EXIT", "2")
    assert download_cli.main([URL, "--integrate"]) == 0
    assert _status(_folder(root)) == "pending"
    assert "[failed]" in capsys.readouterr().out


def test_an_integrated_source_is_not_handed_off_again(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch)
    assert download_cli.main([URL, "--integrate"]) == 0
    assert download_cli.main([URL, "--integrate"]) == 0
    log = (_folder(root).parent / "handed-off.txt").read_text(encoding="utf-8").splitlines()
    assert log == ["Az ókori Athén"]


# --- integrate.py -----------------------------------------------------------

def test_integrate_pending_hands_off_every_pending_source(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, monkeypatch)
    assert download_cli.main([URL]) == 0
    assert integrate_cli.main(["--pending", "--dry-run"]) == 0
    assert _status(_folder(root)) == "pending"
    assert integrate_cli.main(["--pending"]) == 0
    assert _status(_folder(root)) == "integrated"
    assert integrate_cli.main(["--pending"]) == 0
    assert "Nothing to integrate" in capsys.readouterr().out


# --- in_review: the integrator asking the owner ------------------------------
#
# The receiving system answers `in_review` when it stopped to ask a question it may not answer
# itself (where the video belongs, which notes it carries). That is not a failure here: the run
# is not finished, the staged folder is intact, and the answer is given in the receiving system.

def test_in_review_is_a_question_not_a_failure(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, monkeypatch)
    monkeypatch.setenv("STUB_EXIT", "2")
    monkeypatch.setenv("STUB_STATUS", "in_review")
    assert download_cli.main([URL]) == 0
    assert integrate_cli.main(["--pending"]) == 0          # a question is not an error
    out = capsys.readouterr().out
    assert _status(_folder(root)) == "in_review"
    assert "waiting for your decision: 1" in out and "failed: 0" in out


def test_pending_leaves_in_review_alone_and_retry_review_asks_again(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, monkeypatch)
    monkeypatch.setenv("STUB_EXIT", "2")
    monkeypatch.setenv("STUB_STATUS", "in_review")
    assert download_cli.main([URL, "--integrate"]) == 0
    capsys.readouterr()
    assert integrate_cli.main(["--pending"]) == 0
    assert "Nothing to integrate" in capsys.readouterr().out
    handed = (_folder(root).parent / "handed-off.txt").read_text(encoding="utf-8").splitlines()
    assert handed == ["Az ókori Athén"]                    # not handed off a second time
    assert integrate_cli.main(["--pending", "--retry-review"]) == 0
    handed = (_folder(root).parent / "handed-off.txt").read_text(encoding="utf-8").splitlines()
    assert handed == ["Az ókori Athén", "Az ókori Athén"]


def test_download_reports_the_sources_that_wait_for_a_decision(tmp_path, monkeypatch, capsys):
    _project(tmp_path, monkeypatch)
    monkeypatch.setenv("STUB_EXIT", "2")
    monkeypatch.setenv("STUB_STATUS", "in_review")
    assert download_cli.main([URL, "--integrate"]) == 0    # the download is still a success
    assert "wait for your decision" in capsys.readouterr().out


def test_status_counts_every_integration_status(tmp_path):
    for name, status, subject in (("a", "pending", "Irodalom"), ("b", "in_review", "Irodalom"),
                                  ("c", "integrated", "Történelem")):
        (tmp_path / name).mkdir()
        (tmp_path / name / "integration.json").write_text(
            json.dumps({"integration_status": status, "suggested_subject": subject}), encoding="utf-8")
    assert integration.status_counts(tmp_path) == {"pending": 1, "in_review": 1, "integrated": 1}
    assert integration.status_counts(tmp_path, ["Irodalom"]) == {"pending": 1, "in_review": 1}
    assert [p.name for p in integration.pending_folders(tmp_path, None, ("pending", "in_review"))] == ["a", "b"]


def test_status_reports_without_handing_anything_off(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, monkeypatch)
    assert download_cli.main([URL]) == 0
    capsys.readouterr()
    assert integrate_cli.main(["--status"]) == 0
    assert "pending 1" in capsys.readouterr().out
    assert not (_folder(root).parent / "handed-off.txt").exists()
