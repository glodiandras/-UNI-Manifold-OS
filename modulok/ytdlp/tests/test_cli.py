"""CLI smoke tests: argument handling, exit codes, output shape."""

import json

import pytest
from conftest import FakeDownloader, TAXONOMY

from msp.cli import download as download_cli
from msp.cli import inspect as inspect_cli
from msp.cli import transcribe as transcribe_cli
from msp.cli import validate as validate_cli

URL = "https://zanza.tv/tortenelem/az-okori-athen"

CONFIG_YAML = """
output_root: "./staging"
video:
  max_height: 720
  preferred_extension: mp4
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
playlist:
  max_items: 3
crawl:
  delay_seconds: 0
"""


@pytest.fixture
def cli_project(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    taxonomy = "\n".join(f'    - "{name}"' for name in TAXONOMY)
    (tmp_path / "config" / "config.yaml").write_text(
        CONFIG_YAML.format(taxonomy=taxonomy), encoding="utf-8"
    )
    monkeypatch.setenv("MSP_PROJECT_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def fake_backend(monkeypatch):
    downloader = FakeDownloader()
    monkeypatch.setattr(download_cli, "create_downloader", lambda config, **kw: downloader)
    monkeypatch.setattr(download_cli, "require_ytdlp", lambda config: None)
    monkeypatch.setattr(inspect_cli, "create_downloader", lambda config, **kw: downloader)
    monkeypatch.setattr(inspect_cli, "require_ytdlp", lambda config: None)
    return downloader


# --- help / usage -----------------------------------------------------------

@pytest.mark.parametrize("module", [download_cli, inspect_cli, validate_cli, transcribe_cli])
def test_help_exits_cleanly(module, capsys):
    with pytest.raises(SystemExit) as excinfo:
        module.main(["--help"])
    assert excinfo.value.code == 0
    assert "usage:" in capsys.readouterr().out


def test_download_without_arguments_is_a_usage_error(cli_project, capsys):
    assert download_cli.main([]) == 64
    assert "at least one URL" in capsys.readouterr().err


def test_transcribe_without_arguments_is_a_usage_error(cli_project, capsys):
    assert transcribe_cli.main([]) == 64
    assert "use --pending" in capsys.readouterr().err


def test_inspect_without_arguments_is_a_usage_error(cli_project, capsys):
    assert inspect_cli.main([]) == 64


# --- download ---------------------------------------------------------------

def test_check_reports_dependencies_and_config(cli_project, capsys):
    assert download_cli.main(["--check"]) == 0
    out = capsys.readouterr().out
    assert "yt-dlp" in out and "FFmpeg" in out
    assert "best[height<=720][ext=mp4]" in out


def test_dry_run_writes_nothing(cli_project, fake_backend, capsys):
    assert download_cli.main([URL, "--dry-run"]) == 0
    assert not fake_backend.download_calls
    assert not (cli_project / "staging").exists()


def test_download_creates_the_staging_layout(cli_project, fake_backend, capsys):
    assert download_cli.main([URL]) == 0
    folder = cli_project / "staging" / "Zanza" / "Történelem" / "Az ókori Athén"
    assert (folder / "source.md").is_file()
    assert "Staged under" in capsys.readouterr().out


def test_download_reports_failures_with_exit_code_1(cli_project, fake_backend, capsys):
    from msp.errors import VideoUnavailableError

    fake_backend.fail_with = VideoUnavailableError("private video")
    assert download_cli.main([URL]) == 1
    assert "private video" in capsys.readouterr().err


def test_batch_file_is_detected(cli_project, fake_backend, capsys):
    listing = cli_project / "urls.txt"
    listing.write_text(f"{URL} | Fizika\n", encoding="utf-8")
    assert download_cli.main([str(listing)]) == 0
    assert (cli_project / "staging" / "Zanza" / "Fizika").is_dir()


def test_invalid_url_exits_with_a_usage_code(cli_project, fake_backend, capsys):
    # 64 = EX_USAGE: a single bad URL is a usage error, not a download failure.
    assert download_cli.main(["ftp://example.com/video.mp4"]) == 64
    assert "http" in capsys.readouterr().err


def test_an_invalid_url_does_not_abort_a_batch(cli_project, fake_backend, capsys, tmp_path):
    listing = tmp_path / "urls.txt"
    listing.write_text(f"ftp://example.com/video.mp4\n{URL}\n", encoding="utf-8")
    assert download_cli.main([str(listing)]) == 1        # one item failed
    out = capsys.readouterr().out
    assert "Downloaded: 1" in out and "Failed: 1" in out


def test_output_root_override(cli_project, fake_backend, tmp_path):
    other = tmp_path / "elsewhere"
    assert download_cli.main([URL, "--output-root", str(other)]) == 0
    assert (other / "Zanza" / "Történelem" / "Az ókori Athén" / "source.md").is_file()


# --- inspect ----------------------------------------------------------------

def test_inspect_url_lists_usable_formats(cli_project, fake_backend, capsys):
    assert inspect_cli.main([URL]) == 0
    out = capsys.readouterr().out
    assert "Usable formats" in out
    assert "Planned path" in out
    # merging is on, so the 1080p video-only stream counts as reachable
    assert "1920x1080" in out
    assert "NOTE" not in out


def test_inspect_warns_when_merging_is_disabled(cli_project, fake_backend, capsys):
    alt = cli_project / "config" / "nomerge.yaml"
    alt.write_text(
        (cli_project / "config" / "config.yaml").read_text(encoding="utf-8").replace(
            "  preferred_extension: mp4", "  preferred_extension: mp4\n  allow_merge: false"
        ),
        encoding="utf-8",
    )
    assert inspect_cli.main([URL, "--config", str(alt)]) == 0
    out = capsys.readouterr().out
    # only the 360p pre-muxed format is usable now, below the 720p cap
    assert "NOTE" in out
    assert "1920x1080" not in out


def test_inspect_json_output(cli_project, fake_backend, capsys):
    assert inspect_cli.main([URL, "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["source_id"] == "zanza-abc123"
    assert data["progressive_formats"][0]["resolution"] == "640x360"


def test_inspect_staging_summary(cli_project, fake_backend, capsys):
    download_cli.main([URL])
    capsys.readouterr()
    assert inspect_cli.main(["--staging"]) == 0
    out = capsys.readouterr().out
    assert "zanza-abc123" in out
    assert "transcripts pending: 1" in out


# --- validate ---------------------------------------------------------------

def test_validate_passes_on_a_fresh_tree(cli_project, fake_backend, capsys):
    download_cli.main([URL])
    capsys.readouterr()
    assert validate_cli.main([]) == 0
    assert "OK - no structural problems." in capsys.readouterr().out


def test_validate_fails_on_a_broken_tree(cli_project, fake_backend, capsys):
    download_cli.main([URL])
    capsys.readouterr()
    (cli_project / "staging" / "Zanza" / "Történelem" / "Az ókori Athén" / "video.mp4").unlink()
    assert validate_cli.main([]) == 1
    assert "FAILED" in capsys.readouterr().out


def test_validate_json_output(cli_project, fake_backend, capsys):
    download_cli.main([URL])
    capsys.readouterr()
    assert validate_cli.main(["--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["sources_checked"] == 1


def test_strict_mode_fails_on_warnings(cli_project, fake_backend, capsys):
    download_cli.main([URL, "--subject", "Asztrofizika"])
    capsys.readouterr()
    assert validate_cli.main([]) == 0
    assert validate_cli.main(["--strict"]) == 1


# --- transcribe -------------------------------------------------------------

def test_list_backends(cli_project, capsys):
    assert transcribe_cli.main(["--list-backends"]) == 0
    out = capsys.readouterr().out
    assert "faster_whisper" in out and "subtitles" in out


def test_transcribe_pending_without_a_backend_fails_loudly(cli_project, fake_backend, capsys):
    download_cli.main([URL])
    capsys.readouterr()
    assert transcribe_cli.main(["--pending"]) == 1
    out = capsys.readouterr()
    assert "Failed: 1" in out.out
    # the transcript must still be a placeholder, never invented
    note = cli_project / "staging" / "Zanza" / "Történelem" / "Az ókori Athén" / "transcript.md"
    assert "pending" in note.read_text(encoding="utf-8")


def test_transcribe_with_subtitles_backend(cli_project, fake_backend, capsys):
    download_cli.main([URL])
    folder = cli_project / "staging" / "Zanza" / "Történelem" / "Az ókori Athén"
    (folder / "video.hu.vtt").write_text(
        "WEBVTT\n\n00:00:00.000 --> 00:00:03.000\nElső mondat.\n", encoding="utf-8"
    )
    capsys.readouterr()
    assert transcribe_cli.main(["--pending", "--backend", "subtitles"]) == 0
    text = (folder / "transcript.md").read_text(encoding="utf-8")
    assert "[00:00:00]" in text and "Első mondat." in text
    assert 'transcript_status: "completed"' in text


def test_transcribe_rejects_a_non_source_folder(cli_project, capsys, tmp_path):
    assert transcribe_cli.main([str(tmp_path)]) != 0


def test_transcribe_dry_run_changes_nothing(cli_project, fake_backend, capsys):
    download_cli.main([URL])
    folder = cli_project / "staging" / "Zanza" / "Történelem" / "Az ókori Athén"
    (folder / "video.hu.vtt").write_text(
        "WEBVTT\n\n00:00:00.000 --> 00:00:03.000\nElső mondat.\n", encoding="utf-8"
    )
    before = (folder / "transcript.md").read_text(encoding="utf-8")
    capsys.readouterr()
    assert transcribe_cli.main(["--pending", "--dry-run"]) == 0
    assert (folder / "transcript.md").read_text(encoding="utf-8") == before


@pytest.mark.parametrize("module", [download_cli, inspect_cli, validate_cli, transcribe_cli])
def test_version_flag(module, capsys):
    with pytest.raises(SystemExit) as excinfo:
        module.main(["--version"])
    assert excinfo.value.code == 0
    assert "multimedia-source-pipeline" in capsys.readouterr().out


def test_crawl_stages_every_video_page_of_a_listing(cli_project, fake_backend, monkeypatch, capsys):
    from msp.crawl import Page

    pages = {
        "https://zanza.tv/robots.txt": Page("https://zanza.tv/robots.txt", 404),
        "https://zanza.tv/tortenelem": Page("https://zanza.tv/tortenelem", 200, "text/html",
                                            '<a href="/tortenelem/az-okori-athen">Athén</a>'),
        URL: Page(URL, 200, "text/html", '<iframe src="https://www.youtube.com/embed/abc123def"></iframe>'),
    }
    monkeypatch.setattr(download_cli, "create_fetcher", lambda config: pages.__getitem__)
    assert download_cli.main(["--crawl", "https://zanza.tv/tortenelem"]) == 0
    assert (cli_project / "staging" / "Zanza" / "Történelem" / "Az ókori Athén" / "source.md").is_file()
    assert fake_backend.probe_calls == [URL]


def test_crawl_errors_are_reported_with_a_hint(cli_project, fake_backend, monkeypatch, capsys):
    from msp.crawl import Page

    pages = {
        "https://zanza.tv/robots.txt": Page("https://zanza.tv/robots.txt", 404),
        "https://zanza.tv/tortenelem": Page("https://zanza.tv/tortenelem", 200, "text/html", "<p>üres</p>"),
    }
    monkeypatch.setattr(download_cli, "create_fetcher", lambda config: pages.__getitem__)
    assert download_cli.main(["--crawl", "https://zanza.tv/tortenelem"]) == 65
    err = capsys.readouterr().err
    assert "No video page" in err and "->" in err


def test_crawl_and_playlist_cannot_be_combined(cli_project, fake_backend, capsys):
    assert download_cli.main(["--crawl", "--playlist", URL]) == 64
    assert "cannot be combined" in capsys.readouterr().err


def test_repair_archive_restores_entries_without_downloading(cli_project, fake_backend, capsys):
    from msp.archive import Archive
    from msp.config import Config

    assert download_cli.main([URL]) == 0
    config = Config.load(project_root=cli_project)
    assert Archive(config.archive_dir).remove("zanza-abc123") is True
    fake_backend.probe_calls.clear()

    assert validate_cli.main(["--repair-archive"]) == 0
    captured = capsys.readouterr()
    assert "1 entry(ies) restored" in captured.err
    assert "zanza-abc123" in captured.err
    assert "archive.missing_entry" not in captured.out
    assert Archive(config.archive_dir).get("zanza-abc123") is not None
    assert fake_backend.probe_calls == []

