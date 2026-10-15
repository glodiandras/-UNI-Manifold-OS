"""Download archive (duplicate protection) and the integration manifest."""

import pytest

from msp import schema
from conftest import FakeDownloader, make_info

from msp.archive import Archive, ArchiveEntry, rebuild_missing_entries, source_folder_is_complete
from msp.manifest import build_manifest, read_manifest, update_manifest, write_manifest


def entry(source_id="zanza-abc", **kwargs):
    data = dict(url="https://zanza.tv/x", path="Zanza/Történelem/Az ókori Athén",
                downloaded_at="2026-09-04T10:00:00+00:00", provider="Zanza",
                title="Az ókori Athén", media_file="video.mp4",
                extractor="Generic", video_id="abc")
    data.update(kwargs)
    return ArchiveEntry(source_id=source_id, **data)


def test_archive_round_trip(tmp_path):
    archive = Archive(tmp_path / "archive")
    archive.add(entry())
    reloaded = Archive(tmp_path / "archive")
    assert "zanza-abc" in reloaded
    assert reloaded.get("zanza-abc").title == "Az ókori Athén"
    assert len(reloaded) == 1


def test_archive_writes_a_ytdlp_compatible_file(tmp_path):
    archive = Archive(tmp_path / "archive")
    archive.add(entry())
    assert (tmp_path / "archive" / "downloaded.txt").read_text(encoding="utf-8").strip() == "generic abc"


def test_archive_lookup_by_url_and_removal(tmp_path):
    archive = Archive(tmp_path / "archive")
    archive.add(entry())
    assert archive.find_by_url("https://zanza.tv/x").source_id == "zanza-abc"
    assert archive.find_by_url("https://other") is None
    assert archive.remove("zanza-abc") is True
    assert archive.remove("zanza-abc") is False
    assert len(Archive(tmp_path / "archive")) == 0


def test_disabled_archive_stores_nothing(tmp_path):
    archive = Archive(tmp_path / "archive", enabled=False)
    archive.add(entry())
    assert not (tmp_path / "archive").exists()
    assert len(Archive(tmp_path / "archive")) == 0


def test_corrupt_index_does_not_crash_the_archive(tmp_path):
    (tmp_path / "archive").mkdir()
    (tmp_path / "archive" / "index.json").write_text('{"entries": "not a mapping"}', encoding="utf-8")
    assert len(Archive(tmp_path / "archive")) == 0


def test_folder_completeness_needs_a_note_and_a_non_empty_media_file(tmp_path):
    folder = tmp_path / "src"
    folder.mkdir()
    assert source_folder_is_complete(folder) is False

    (folder / schema.SOURCE_NOTE_NAME).write_text("---\n---\n", encoding="utf-8")
    assert source_folder_is_complete(folder) is False

    (folder / "video.mp4").write_bytes(b"")
    assert source_folder_is_complete(folder) is False

    (folder / "video.mp4").write_bytes(b"data")
    assert source_folder_is_complete(folder) is True


def test_partial_downloads_do_not_count_as_complete(tmp_path):
    folder = tmp_path / "src"
    folder.mkdir()
    (folder / schema.SOURCE_NOTE_NAME).write_text("---\n---\n", encoding="utf-8")
    (folder / "video.mp4.part").write_bytes(b"partial")
    assert source_folder_is_complete(folder) is False


# --- two runs at the same time ---------------------------------------------

def test_a_save_keeps_what_another_run_added_meanwhile(tmp_path):
    """The web UI and a terminal command write the same index file."""
    first = Archive(tmp_path / "archive")
    first.add(entry("zanza-first"))

    second = Archive(tmp_path / "archive")          # loads the index as it is now
    second.add(entry("zanza-second", url="https://zanza.tv/second"))
    first.add(entry("zanza-third", url="https://zanza.tv/third"))   # saves its own view

    reloaded = Archive(tmp_path / "archive")
    assert sorted(e.source_id for e in reloaded) == ["zanza-first", "zanza-second", "zanza-third"]
    assert first.get("zanza-second") is not None    # the merge also fixes our own view


def test_a_removal_is_not_resurrected_by_the_merge(tmp_path):
    first = Archive(tmp_path / "archive")
    first.add(entry("zanza-first"))
    second = Archive(tmp_path / "archive")
    second.add(entry("zanza-second", url="https://zanza.tv/second"))

    first.remove("zanza-first")                     # first still has the old view
    reloaded = Archive(tmp_path / "archive")
    assert sorted(e.source_id for e in reloaded) == ["zanza-second"]


def test_the_ytdlp_archive_file_covers_the_merged_entries(tmp_path):
    first = Archive(tmp_path / "archive")
    first.add(entry("zanza-first"))
    second = Archive(tmp_path / "archive")
    second.add(entry("zanza-second", url="https://zanza.tv/second", video_id="def"))
    lines = (tmp_path / "archive" / "downloaded.txt").read_text(encoding="utf-8").split()
    assert "abc" in lines and "def" in lines


# --- rebuilding lost entries -----------------------------------------------

def test_rebuild_restores_an_entry_from_the_staged_folder(config, staged_source):
    archive = Archive(config.archive_dir)
    source_id = archive.get("zanza-abc123").source_id
    assert archive.remove(source_id) is True

    result = rebuild_missing_entries(config)
    assert [e.source_id for e in result.restored] == [source_id]
    restored = Archive(config.archive_dir).get(source_id)
    assert restored.path == str(staged_source.relative_to(config.output_root))
    assert restored.url == "https://zanza.tv/tortenelem/az-okori-athen"
    assert restored.title == "Az ókori Athén"
    assert restored.media_file == "video.mp4"
    assert (restored.extractor, restored.video_id) == ("Generic", "abc123")
    assert restored.downloaded_at


def test_rebuild_is_idempotent_and_never_removes(config, staged_source):
    archive = Archive(config.archive_dir)
    archive.add(entry("zanza-gone", path="Zanza/Történelem/Elköltöztetett"))
    assert rebuild_missing_entries(config).restored == []
    assert Archive(config.archive_dir).get("zanza-gone") is not None


def test_rebuild_ignores_an_unfinished_folder(config, staged_source):
    (staged_source / "video.mp4").unlink()
    Archive(config.archive_dir).remove("zanza-abc123")
    assert rebuild_missing_entries(config).restored == []


def test_rebuild_reports_an_unreadable_note_instead_of_failing(config, staged_source, downloader):
    from msp.pipeline import ingest_url

    second = ingest_url("https://zanza.tv/tortenelem/masik", config=config,
                        downloader=FakeDownloader(make_info(video_id="def456", title="Másik")))
    archive = Archive(config.archive_dir)
    archive.remove("zanza-abc123")
    archive.remove("zanza-def456")
    (staged_source / schema.SOURCE_NOTE_NAME).write_text("---\nnot: [valid\n", encoding="utf-8")

    result = rebuild_missing_entries(config)
    assert [e.source_id for e in result.restored] == ["zanza-def456"]
    assert len(result.unreadable) == 1 and str(staged_source) in result.unreadable[0][0]
    assert second.status == "downloaded"


def test_manifest_shape():
    data = build_manifest(source_id="zanza-abc", title="T", provider="Zanza",
                          url="https://x", media_file="video.mp4", language="hu",
                          duration_seconds=612, suggested_subject="Történelem",
                          subject_source="url")
    assert data["nn_anchorable"] is None          # undecided, never assumed
    assert data["integration_status"] == "pending"
    assert data["suggested_topics"] == []          # never guessed
    assert data["anchor_format"] == "[[video.mp4#t=HH:MM:SS]]"
    assert data["source_note"] == schema.SOURCE_NOTE_NAME


def test_manifest_rejects_unknown_statuses():
    with pytest.raises(ValueError):
        build_manifest(source_id="a", title="t", provider="p", url="u", media_file="v",
                       transcript_status="nope")
    with pytest.raises(ValueError):
        build_manifest(source_id="a", title="t", provider="p", url="u", media_file="v",
                       integration_status="nope")


def test_manifest_update_keeps_unknown_keys(tmp_path):
    path = tmp_path / "integration.json"
    data = build_manifest(source_id="a", title="t", provider="p", url="u", media_file="v")
    data["owner_note"] = "keep me"
    write_manifest(path, data)
    update_manifest(path, {"transcript_status": "completed"})
    reloaded = read_manifest(path)
    assert reloaded["transcript_status"] == "completed"
    assert reloaded["owner_note"] == "keep me"
