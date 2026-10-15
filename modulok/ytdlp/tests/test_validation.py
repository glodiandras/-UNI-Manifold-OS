"""Validator behaviour on healthy and on damaged staging trees."""

import json

from conftest import FakeDownloader, make_info

from msp import notes, schema
from msp.pipeline import ingest_url
from msp.validation import validate_staging

URL = "https://zanza.tv/tortenelem/az-okori-athen"


def codes(report):
    return {issue.code for issue in report.issues}


def test_a_freshly_staged_tree_is_valid(config, staged_source):
    report = validate_staging(config)
    assert report.errors == []
    assert report.sources_checked == 1
    assert report.pending_transcripts == 1
    assert report.undecided_anchorable == 1
    assert report.ok is True


def test_a_staged_folder_missing_from_the_archive_is_a_warning(config, staged_source):
    from msp.archive import Archive

    Archive(config.archive_dir).remove("zanza-abc123")
    report = validate_staging(config)
    codes = [issue.code for issue in report.warnings]
    assert "archive.missing_entry" in codes
    assert "--repair-archive" in next(i.message for i in report.warnings
                                     if i.code == "archive.missing_entry")
    assert not report.errors


def test_missing_staging_root_is_only_a_warning(config):
    report = validate_staging(config)
    assert report.ok is True
    assert "staging.missing_root" in codes(report)


def test_missing_media_file_is_an_error(config, staged_source):
    (staged_source / "video.mp4").unlink()
    report = validate_staging(config)
    assert "source.missing_media" in codes(report)
    assert report.ok is False


def test_empty_media_file_is_an_error(config, staged_source):
    (staged_source / "video.mp4").write_bytes(b"")
    assert "source.empty_media" in codes(validate_staging(config))


def test_missing_transcript_is_an_error(config, staged_source):
    (staged_source / schema.TRANSCRIPT_NOTE_NAME).unlink()
    assert "source.missing_transcript" in codes(validate_staging(config))


def test_missing_metadata_is_an_error(config, staged_source):
    (staged_source / schema.METADATA_NAME).unlink()
    assert "source.missing_metadata" in codes(validate_staging(config))


def test_broken_metadata_json_is_an_error(config, staged_source):
    (staged_source / schema.METADATA_NAME).write_text("{not json", encoding="utf-8")
    assert "metadata.invalid_json" in codes(validate_staging(config))


def test_missing_required_field_is_an_error(config, staged_source):
    path = staged_source / schema.SOURCE_NOTE_NAME
    text = path.read_text(encoding="utf-8").replace('source_id: "zanza-abc123"\n', "")
    path.write_text(text, encoding="utf-8")
    assert "source.missing_field" in codes(validate_staging(config))


def test_empty_required_field_is_an_error(config, staged_source):
    notes.update_frontmatter(staged_source / schema.SOURCE_NOTE_NAME, {"title": ""})
    assert "source.empty_field" in codes(validate_staging(config))


def test_unknown_enum_value_is_an_error(config, staged_source):
    notes.update_frontmatter(staged_source / schema.SOURCE_NOTE_NAME, {"pipeline_status": "weird"})
    assert "source.bad_enum" in codes(validate_staging(config))


def test_broken_frontmatter_is_reported_not_crashed(config, staged_source):
    (staged_source / schema.SOURCE_NOTE_NAME).write_text("no frontmatter here\n", encoding="utf-8")
    report = validate_staging(config)
    assert "source.unreadable" in codes(report)


def test_source_id_mismatch_between_note_and_transcript(config, staged_source):
    notes.update_frontmatter(staged_source / schema.TRANSCRIPT_NOTE_NAME, {"source_id": "other-id"})
    assert "transcript.source_id_mismatch" in codes(validate_staging(config))


def test_manifest_mismatch_is_an_error(config, staged_source):
    path = staged_source / schema.MANIFEST_NAME
    data = json.loads(path.read_text(encoding="utf-8"))
    data["source_id"] = "other-id"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert "manifest.source_id_mismatch" in codes(validate_staging(config))


def test_missing_manifest_is_a_warning(config, staged_source):
    (staged_source / schema.MANIFEST_NAME).unlink()
    report = validate_staging(config)
    assert "manifest.missing" in codes(report)
    assert report.ok is True


def test_duplicate_source_ids_are_detected(config, downloader, tmp_path):
    import shutil

    first = ingest_url(URL, config=config, downloader=downloader).path
    shutil.copytree(first, first.parent / "Másolat")
    assert "staging.duplicate_source_id" in codes(validate_staging(config))


def test_bad_timestamp_format_in_a_transcript_is_an_error(config, staged_source):
    notes.replace_body(staged_source / schema.TRANSCRIPT_NOTE_NAME, "[1:32]\n\nszöveg\n")
    assert "transcript.bad_timestamp" in codes(validate_staging(config))


def test_out_of_order_timestamps_are_a_warning(config, staged_source):
    notes.replace_body(staged_source / schema.TRANSCRIPT_NOTE_NAME,
                       "[00:01:00]\n\na\n\n[00:00:30]\n\nb\n")
    report = validate_staging(config)
    assert "transcript.unordered" in codes(report)
    assert report.ok is True


def test_completed_transcript_without_timestamps_is_a_warning(config, staged_source):
    notes.update_frontmatter(staged_source / schema.TRANSCRIPT_NOTE_NAME,
                             {"transcript_status": "completed"})
    notes.replace_body(staged_source / schema.TRANSCRIPT_NOTE_NAME, "csak szöveg\n")
    assert "transcript.no_timestamps" in codes(validate_staging(config))


def test_postprocessed_transcript_is_flagged(config, staged_source):
    notes.update_frontmatter(staged_source / schema.TRANSCRIPT_NOTE_NAME,
                             {"transcript_status": "completed", "transcript_postprocessed": True})
    notes.replace_body(staged_source / schema.TRANSCRIPT_NOTE_NAME, "[00:00:00]\n\nszöveg\n")
    assert "transcript.postprocessed" in codes(validate_staging(config))


def test_unknown_subject_is_a_warning(config, downloader):
    ingest_url(URL, config=config, downloader=downloader, subject="Asztrofizika")
    report = validate_staging(config)
    assert "source.unknown_subject" in codes(report)
    assert report.ok is True


def test_leftover_part_files_are_reported(config, staged_source):
    (staged_source / "video.mp4.part").write_bytes(b"partial")
    assert "source.leftover_files" in codes(validate_staging(config))


def test_orphan_media_without_a_source_note(config, staged_source):
    orphan = config.output_root / "Zanza" / "Történelem" / "Árva"
    orphan.mkdir(parents=True)
    (orphan / "video.mp4").write_bytes(b"data")
    assert "staging.orphan_file" in codes(validate_staging(config))


def test_dangling_archive_entry_is_reported(config, downloader):
    import shutil

    outcome = ingest_url(URL, config=config, downloader=downloader)
    other = FakeDownloader(make_info(video_id="second", title="Másik"))
    ingest_url("https://zanza.tv/tortenelem/masik", config=config, downloader=other)
    shutil.rmtree(outcome.path)
    assert "archive.dangling_entry" in codes(validate_staging(config))


def test_report_serialises_to_json(config, staged_source):
    data = validate_staging(config).to_dict()
    assert data["sources_checked"] == 1
    assert data["errors"] == 0
    assert isinstance(data["issues"], list)


def test_broken_wikilink_in_the_transcript_is_an_error(config, staged_source):
    notes.update_frontmatter(staged_source / schema.TRANSCRIPT_NOTE_NAME,
                             {"media": "[[missing-file.mp4]]"})
    assert "note.broken_link" in codes(validate_staging(config))


def test_generated_wikilinks_resolve(config, staged_source):
    """[[source]] and [[video.mp4]] must point at files that are really there."""
    report = validate_staging(config)
    assert "note.broken_link" not in codes(report)


def test_manually_renamed_unsafe_folder_is_a_warning(config, staged_source):
    renamed = staged_source.parent / "A Hunyadiak [kora]"
    staged_source.rename(renamed)
    report = validate_staging(config)
    assert "staging.unsafe_path" in codes(report)
    assert report.ok is True
