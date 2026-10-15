"""End-to-end staging with a fake downloader - no network, no real media."""

import json

import pytest
from conftest import FakeDownloader, make_info

from msp import notes, schema
from msp.archive import Archive
from msp.errors import DownloadFailedError, InvalidURLError, PlaylistGuardError, VideoUnavailableError
from msp.pipeline import (
    STATUS_DOWNLOADED,
    STATUS_DRY_RUN,
    STATUS_FAILED,
    STATUS_SKIPPED,
    UrlItem,
    ingest_many,
    ingest_playlist,
    ingest_url,
    iter_source_dirs,
    looks_like_url_list,
    parse_url_list,
    validate_url,
)

URL = "https://zanza.tv/tortenelem/az-okori-athen"


# --- URL handling -----------------------------------------------------------

def test_validate_url_accepts_http_and_https():
    assert validate_url(" https://a.b/c ") == "https://a.b/c"


@pytest.mark.parametrize("bad", ["", "   ", "file:///etc/passwd", "javascript:alert(1)", "https://"])
def test_validate_url_rejects_everything_else(bad):
    with pytest.raises(InvalidURLError):
        validate_url(bad)


def test_parse_url_list(tmp_path):
    listing = tmp_path / "urls.txt"
    listing.write_text(
        "# comment\n"
        "\n"
        "https://zanza.tv/a | Történelem\n"
        "https://zanza.tv/b\n"
        "https://zanza.tv/c | Fizika  # trailing comment\n",
        encoding="utf-8",
    )
    items = parse_url_list(listing)
    assert [item.url for item in items] == ["https://zanza.tv/a", "https://zanza.tv/b", "https://zanza.tv/c"]
    assert [item.subject for item in items] == ["Történelem", None, "Fizika"]


def test_empty_url_list_is_an_error(tmp_path):
    listing = tmp_path / "urls.txt"
    listing.write_text("# only comments\n", encoding="utf-8")
    with pytest.raises(InvalidURLError):
        parse_url_list(listing)


def test_url_list_detection(tmp_path):
    listing = tmp_path / "urls.txt"
    listing.write_text("https://x\n", encoding="utf-8")
    assert looks_like_url_list(str(listing)) is True
    assert looks_like_url_list("https://zanza.tv/x") is False
    assert looks_like_url_list(str(tmp_path / "missing.txt")) is False


# --- the happy path ---------------------------------------------------------

def test_ingest_creates_the_specified_layout(config, downloader):
    outcome = ingest_url(URL, config=config, downloader=downloader)
    assert outcome.status == STATUS_DOWNLOADED

    folder = outcome.path
    assert folder == config.output_root / "Zanza" / "Történelem" / "Az ókori Athén"
    for name in ("video.mp4", schema.SOURCE_NOTE_NAME, schema.TRANSCRIPT_NOTE_NAME,
                 schema.METADATA_NAME, schema.MANIFEST_NAME):
        assert (folder / name).is_file(), name


def test_the_three_files_agree_on_the_source_id(staged_source):
    front, _ = notes.read_note(staged_source / schema.SOURCE_NOTE_NAME)
    tfront, _ = notes.read_note(staged_source / schema.TRANSCRIPT_NOTE_NAME)
    manifest = json.loads((staged_source / schema.MANIFEST_NAME).read_text(encoding="utf-8"))
    metadata = json.loads((staged_source / schema.METADATA_NAME).read_text(encoding="utf-8"))

    assert front["source_id"] == "zanza-abc123"
    assert tfront["source_id"] == front["source_id"]
    assert manifest["source_id"] == front["source_id"]
    assert metadata["pipeline"]["source_id"] == front["source_id"]


def test_source_note_records_what_was_really_downloaded(staged_source):
    front, _ = notes.read_note(staged_source / schema.SOURCE_NOTE_NAME)
    assert front["media_file"] == "video.mp4"
    assert front["resolution"] == "640x360"
    assert front["duration"] == "00:10:12"
    assert front["pipeline_status"] == "downloaded"
    assert front["provider"] == "Zanza"


def test_transcript_placeholder_is_pending(staged_source):
    tfront, body = notes.read_note(staged_source / schema.TRANSCRIPT_NOTE_NAME)
    assert tfront["transcript_status"] == "pending"
    assert tfront["transcript_postprocessed"] is False
    assert "[00:" not in body      # no invented timestamps


def test_manifest_leaves_the_vault_decision_open(staged_source):
    manifest = json.loads((staged_source / schema.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["nn_anchorable"] is None
    assert manifest["integration_status"] == "pending"
    assert manifest["suggested_topics"] == []
    assert manifest["suggested_subject"] == "Történelem"


def test_archive_entry_is_written(config, downloader, tmp_path):
    ingest_url(URL, config=config, downloader=downloader)
    archive = Archive(config.archive_dir)
    entry = archive.get("zanza-abc123")
    assert entry is not None
    assert entry.path == "Zanza/Történelem/Az ókori Athén"
    assert entry.video_id == "abc123"


def test_explicit_subject_overrides_the_heuristic(config, downloader):
    outcome = ingest_url(URL, config=config, downloader=downloader, subject="Fizika")
    assert outcome.path.parent.name == "Fizika"


def test_subject_folder_can_be_switched_off(tmp_path, downloader):
    from conftest import make_config

    config = make_config(tmp_path, organization={"subject_folder": False})
    outcome = ingest_url(URL, config=config, downloader=downloader)
    assert outcome.path == config.output_root / "Zanza" / "Az ókori Athén"


def test_unsafe_titles_are_sanitised(config):
    downloader = FakeDownloader(make_info(title="Rész 1/2: <ütős> [teszt] #1"))
    outcome = ingest_url(URL, config=config, downloader=downloader)
    assert outcome.path.name == "Rész 1-2- -ütős- -teszt- -1"
    assert outcome.path.is_dir()


# --- duplicate protection ---------------------------------------------------

def test_second_run_is_skipped(config, downloader):
    first = ingest_url(URL, config=config, downloader=downloader)
    second = ingest_url(URL, config=config, downloader=downloader)
    assert second.status == STATUS_SKIPPED
    assert second.path == first.path
    assert len(downloader.download_calls) == 1


def test_force_downloads_again(config, downloader):
    ingest_url(URL, config=config, downloader=downloader)
    outcome = ingest_url(URL, config=config, downloader=downloader, force=True)
    assert outcome.status == STATUS_DOWNLOADED
    assert len(downloader.download_calls) == 2
    assert downloader.download_calls[-1].overwrite is True


def test_force_never_destroys_a_finished_transcript(config, downloader):
    outcome = ingest_url(URL, config=config, downloader=downloader)
    transcript = outcome.path / schema.TRANSCRIPT_NOTE_NAME
    notes.update_frontmatter(transcript, {"transcript_status": "completed"})
    notes.replace_body(transcript, "[00:00:00]\n\nvaló szöveg\n")

    ingest_url(URL, config=config, downloader=downloader, force=True)
    front, body = notes.read_note(transcript)
    assert front["transcript_status"] == "completed"
    assert "való szöveg" in body


def test_force_preserves_owner_decisions_in_the_manifest(config, downloader):
    outcome = ingest_url(URL, config=config, downloader=downloader)
    path = outcome.path / schema.MANIFEST_NAME
    data = json.loads(path.read_text(encoding="utf-8"))
    data["nn_anchorable"] = True
    data["integration_status"] = "integrated"
    path.write_text(json.dumps(data), encoding="utf-8")

    ingest_url(URL, config=config, downloader=downloader, force=True)
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded["nn_anchorable"] is True
    assert reloaded["integration_status"] == "integrated"


def test_a_removed_folder_is_downloaded_again(config, downloader):
    import shutil

    outcome = ingest_url(URL, config=config, downloader=downloader)
    shutil.rmtree(outcome.path)
    again = ingest_url(URL, config=config, downloader=downloader)
    assert again.status == STATUS_DOWNLOADED


def test_different_videos_with_the_same_title_get_separate_folders(config):
    first = ingest_url(URL, config=config, downloader=FakeDownloader(make_info(video_id="one")))
    second = ingest_url("https://zanza.tv/tortenelem/masik",
                        config=config, downloader=FakeDownloader(make_info(video_id="two")))
    assert first.path != second.path
    assert second.path.name == "Az ókori Athén (zanza-two)"
    assert len(list(iter_source_dirs(config.output_root))) == 2


# --- failures ---------------------------------------------------------------

def test_failures_are_returned_not_raised(config):
    downloader = FakeDownloader()
    downloader.fail_with = VideoUnavailableError("The video is gone")
    outcome = ingest_url(URL, config=config, downloader=downloader)
    assert outcome.status == STATUS_FAILED
    assert "gone" in outcome.message
    assert not list(iter_source_dirs(config.output_root))


def test_a_missing_media_file_is_a_failure(config, monkeypatch):
    downloader = FakeDownloader()

    def broken(request):
        request.target_dir.mkdir(parents=True, exist_ok=True)
        from msp.downloader import DownloadResult
        return DownloadResult(media_path=None, info=downloader.info)

    monkeypatch.setattr(downloader, "download", broken)
    outcome = ingest_url(URL, config=config, downloader=downloader)
    assert outcome.status == STATUS_FAILED
    assert isinstance(outcome.error, DownloadFailedError)


def test_an_empty_media_file_is_a_failure(config):
    downloader = FakeDownloader(media_bytes=b"")
    outcome = ingest_url(URL, config=config, downloader=downloader)
    assert outcome.status == STATUS_FAILED
    assert "empty" in outcome.message


# --- dry run ----------------------------------------------------------------

def test_dry_run_writes_nothing(config, downloader):
    outcome = ingest_url(URL, config=config, downloader=downloader, dry_run=True)
    assert outcome.status == STATUS_DRY_RUN
    assert not downloader.download_calls
    assert not config.output_root.exists() or not list(iter_source_dirs(config.output_root))
    assert not (config.archive_dir / "index.json").exists()
    assert "would download" in outcome.message


# --- batch ------------------------------------------------------------------

def test_batch_continues_after_a_failure(config, monkeypatch):
    downloader = FakeDownloader()
    calls = {"n": 0}
    original = downloader.probe

    def flaky(url, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise VideoUnavailableError("private video")
        info = original(url, **kwargs)
        info["id"] = f"id{calls['n']}"
        info["title"] = f"Videó {calls['n']}"
        return info

    monkeypatch.setattr(downloader, "probe", flaky)
    summary = ingest_many(
        [UrlItem("https://zanza.tv/a"), UrlItem("https://zanza.tv/b"), UrlItem("https://zanza.tv/c")],
        config=config, downloader=downloader,
    )
    assert (summary.downloaded, summary.failed, summary.total) == (2, 1, 3)
    assert "Downloaded: 2" in summary.render()


def test_batch_skips_already_staged_items(config, downloader):
    ingest_url(URL, config=config, downloader=downloader)
    summary = ingest_many([URL, URL], config=config, downloader=downloader)
    assert summary.skipped == 2


def test_batch_subject_hints_are_used(config, downloader):
    summary = ingest_many([UrlItem("https://example.org/x", subject="Fizika")],
                          config=config, downloader=downloader)
    assert summary.outcomes[0].path.parent.name == "Fizika"


# --- playlists --------------------------------------------------------------

def _playlist_downloader(count):
    downloader = FakeDownloader()
    entries = [
        {"webpage_url": f"https://zanza.tv/item{i}", "title": f"Item {i}", "id": f"id{i}"}
        for i in range(count)
    ]

    def probe(url, *, allow_playlist=False, flat=False):
        if url.endswith("/playlist"):
            return {"_type": "playlist", "title": "Sorozat", "entries": entries}
        index = url.rsplit("item", 1)[-1]
        return make_info(video_id=f"id{index}", title=f"Item {index}", url=url)

    downloader.probe = probe  # type: ignore[method-assign]
    return downloader


def test_playlist_url_is_refused_without_the_flag(config):
    downloader = _playlist_downloader(2)
    outcome = ingest_url("https://zanza.tv/playlist", config=config, downloader=downloader)
    assert outcome.status == STATUS_FAILED
    assert isinstance(outcome.error, PlaylistGuardError)
    assert "--playlist" in (outcome.error.hint or "")


def test_playlist_mode_ingests_every_entry(config):
    downloader = _playlist_downloader(2)
    summary = ingest_playlist("https://zanza.tv/playlist", config=config, downloader=downloader)
    assert summary.downloaded == 2


def test_playlist_larger_than_the_limit_aborts(config):
    downloader = _playlist_downloader(5)   # config fixture sets max_items = 3
    with pytest.raises(PlaylistGuardError) as excinfo:
        ingest_playlist("https://zanza.tv/playlist", config=config, downloader=downloader)
    assert "--max-items" in (excinfo.value.hint or "")


def test_playlist_limit_can_be_raised_per_run(config):
    downloader = _playlist_downloader(5)
    summary = ingest_playlist("https://zanza.tv/playlist", config=config,
                              downloader=downloader, max_items=10)
    assert summary.downloaded == 5


# --- embedding sites (zanza.tv -> YouTube) ----------------------------------

def _embedded_info():
    """What yt-dlp really returns for a zanza.tv page: the YouTube video."""
    info = make_info(video_id="kdkQvYe6eS4", title="A Hunyadiak kora",
                     url="https://www.youtube.com/watch?v=kdkQvYe6eS4", extractor="youtube")
    info["extractor_key"] = "Youtube"
    return info


def test_embedded_media_is_staged_under_the_requested_site(config):
    downloader = FakeDownloader(_embedded_info())
    outcome = ingest_url("https://zanza.tv/tortenelem/magyarsag/hunyadiak-kora",
                         config=config, downloader=downloader)
    assert outcome.status == STATUS_DOWNLOADED
    assert outcome.path == config.output_root / "Zanza" / "Történelem" / "A Hunyadiak kora"
    assert outcome.source_id == "zanza-kdkQvYe6eS4"


def test_the_real_media_origin_is_recorded_not_hidden(config):
    downloader = FakeDownloader(_embedded_info())
    outcome = ingest_url("https://zanza.tv/tortenelem/magyarsag/hunyadiak-kora",
                         config=config, downloader=downloader)
    front, _ = notes.read_note(outcome.path / schema.SOURCE_NOTE_NAME)
    assert front["url"] == "https://zanza.tv/tortenelem/magyarsag/hunyadiak-kora"
    assert front["media_url"] == "https://www.youtube.com/watch?v=kdkQvYe6eS4"
    assert front["provider_video_id"] == "kdkQvYe6eS4"

    metadata = json.loads((outcome.path / schema.METADATA_NAME).read_text(encoding="utf-8"))
    assert metadata["extractor"] == "Youtube"
    assert metadata["webpage_url"] == "https://www.youtube.com/watch?v=kdkQvYe6eS4"


def test_media_url_is_omitted_when_it_equals_the_requested_url(config, staged_source):
    front, _ = notes.read_note(staged_source / schema.SOURCE_NOTE_NAME)
    assert "media_url" not in front


# --- automatic transcription (transcript.enabled) ---------------------------

class _StubBackend:
    """Stands in for a local ASR engine - no model, no audio, no network."""

    name = "stub"

    def __init__(self, segments=None, error=None):
        self.segments = segments
        self.error = error
        self.calls = []

    def transcribe(self, media_path, *, language=None, folder=None):
        from msp.errors import TranscriptionError
        from msp.transcription.base import Segment, TranscriptResult

        self.calls.append({"media": media_path, "language": language})
        if self.error:
            raise TranscriptionError(self.error)
        return TranscriptResult(
            segments=[Segment(start=0.0, end=2.0, text="Korvin Áruház."),
                      Segment(start=92.0, end=95.0, text="Hunyadi János.")],
            engine="stub:test",
            language=language,
            model="test",
            postprocessed=False,
        )


def _with_stub(monkeypatch, backend):
    monkeypatch.setattr("msp.transcription.registry.select_backend", lambda *a, **k: backend)


def test_download_transcribes_when_enabled(tmp_path, monkeypatch, downloader):
    from conftest import make_config

    backend = _StubBackend()
    _with_stub(monkeypatch, backend)
    config = make_config(tmp_path, transcript={"enabled": True, "language": "hu"})

    outcome = ingest_url("https://zanza.tv/tortenelem/az-okori-athen",
                         config=config, downloader=downloader)

    front, body = notes.read_note(outcome.path / schema.TRANSCRIPT_NOTE_NAME)
    assert front["transcript_status"] == "completed"
    assert front["transcript_postprocessed"] is False
    assert "[00:00:00]" in body and "[00:01:32]" in body
    assert "Korvin Áruház." in body
    # the configured language reaches the engine instead of being auto-detected
    assert backend.calls[0]["language"] == "hu"
    # and the manifest agrees with the note
    manifest = json.loads((outcome.path / schema.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["transcript_status"] == "completed"


def test_download_keeps_the_placeholder_when_disabled(tmp_path, monkeypatch, downloader):
    from conftest import make_config

    backend = _StubBackend()
    _with_stub(monkeypatch, backend)
    config = make_config(tmp_path, transcript={"enabled": False})

    outcome = ingest_url("https://zanza.tv/tortenelem/az-okori-athen",
                         config=config, downloader=downloader)

    front, _ = notes.read_note(outcome.path / schema.TRANSCRIPT_NOTE_NAME)
    assert front["transcript_status"] == "pending"
    assert backend.calls == []


def test_a_failing_transcription_does_not_fail_the_download(tmp_path, monkeypatch, downloader):
    from conftest import make_config

    _with_stub(monkeypatch, _StubBackend(error="no model installed"))
    config = make_config(tmp_path, transcript={"enabled": True})

    outcome = ingest_url("https://zanza.tv/tortenelem/az-okori-athen",
                         config=config, downloader=downloader)

    assert outcome.status == STATUS_DOWNLOADED
    assert (outcome.path / "video.mp4").is_file()
    front, _ = notes.read_note(outcome.path / schema.TRANSCRIPT_NOTE_NAME)
    assert front["transcript_status"] == "pending"   # retryable with --pending
