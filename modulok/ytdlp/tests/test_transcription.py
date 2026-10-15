"""Subtitle parsing, transcript rendering and the backend registry."""

import json

import pytest

from msp import notes, schema
from msp.errors import TranscriptionError
from msp.transcription import (
    Segment,
    TranscriptResult,
    backend_status,
    get_backend,
    render_transcript_body,
    select_backend,
    write_transcript,
)
from msp.transcription.subtitles import SubtitlesBackend, parse_subtitle_file, parse_time

VTT = """WEBVTT
Kind: captions
Language: hu

00:00:00.000 --> 00:00:03.500
Az ókori Athén

00:00:03.500 --> 00:00:07.000
Az ókori Athén a demokrácia bölcsője

00:01:32.000 --> 00:01:36.000
<c>Második</c> mondat.
"""

SRT = """1
00:00:00,000 --> 00:00:03,500
Első mondat.

2
00:01:32,000 --> 00:01:36,000
Második mondat.
"""


def test_parse_time_accepts_both_separators():
    assert parse_time("00:01:32.500") == 92.5
    assert parse_time("00:01:32,500") == 92.5
    assert parse_time("01:32.000") == 92.0


def test_vtt_parsing_strips_tags_and_rolling_repetition(tmp_path):
    path = tmp_path / "video.hu.vtt"
    path.write_text(VTT, encoding="utf-8")
    segments = parse_subtitle_file(path)
    assert [segment.text for segment in segments] == [
        "Az ókori Athén a demokrácia bölcsője",
        "Második mondat.",
    ]
    assert segments[1].start == 92.0


def test_srt_parsing_ignores_cue_numbers(tmp_path):
    path = tmp_path / "video.srt"
    path.write_text(SRT, encoding="utf-8")
    segments = parse_subtitle_file(path)
    assert [segment.text for segment in segments] == ["Első mondat.", "Második mondat."]


def test_body_uses_zero_padded_markers():
    body = render_transcript_body([
        Segment(start=0, text="első"),
        Segment(start=92, text="második"),
    ])
    assert body == "[00:00:00]\n\nelső\n\n[00:01:32]\n\nmásodik\n"


def test_grouping_merges_nearby_segments():
    body = render_transcript_body(
        [Segment(start=0, text="a"), Segment(start=5, text="b"), Segment(start=40, text="c")],
        group_seconds=30,
    )
    assert body == "[00:00:00]\n\na b\n\n[00:00:40]\n\nc\n"


def test_empty_transcripts_are_refused():
    with pytest.raises(TranscriptionError):
        render_transcript_body([])


def test_text_is_not_altered_beyond_whitespace():
    original = "  szöveg   sok    szóközzel  "
    assert Segment(start=0, text=original).cleaned().text == "szöveg sok szóközzel"


def test_write_transcript_updates_note_and_manifest(config, staged_source):
    result = TranscriptResult(
        segments=[Segment(start=0, text="első", confidence=0.9),
                  Segment(start=92, text="második", confidence=0.7)],
        engine="test-engine", language="hu", model="test-model",
    )
    write_transcript(staged_source, result, config=config)

    front, body = notes.read_note(staged_source / schema.TRANSCRIPT_NOTE_NAME)
    assert front["transcript_status"] == "completed"
    assert front["transcript_engine"] == "test-engine"
    assert front["transcript_postprocessed"] is False
    assert front["transcript_confidence"] == pytest.approx(0.8)
    assert "[00:01:32]" in body

    manifest = json.loads((staged_source / schema.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["transcript_status"] == "completed"
    assert manifest["nn_anchorable"] is None      # still the owner's decision


def test_write_transcript_refuses_a_non_source_folder(config, tmp_path):
    with pytest.raises(TranscriptionError):
        write_transcript(tmp_path, TranscriptResult(segments=[Segment(0, "x")], engine="e"),
                         config=config)


def test_subtitles_backend_end_to_end(config, staged_source):
    (staged_source / "video.hu.vtt").write_text(VTT, encoding="utf-8")
    backend = SubtitlesBackend(config)
    assert backend.is_available(staged_source)

    result = backend.transcribe(staged_source / "video.mp4", language="hu", folder=staged_source)
    assert result.engine.startswith("subtitles:")
    assert result.postprocessed is False
    write_transcript(staged_source, result, config=config)

    front, body = notes.read_note(staged_source / schema.TRANSCRIPT_NOTE_NAME)
    assert front["transcript_status"] == "completed"
    assert "demokrácia bölcsője" in body


def test_subtitles_backend_reports_why_it_cannot_run(config, staged_source):
    backend = SubtitlesBackend(config)
    reason = backend.unavailable_reason(staged_source)
    assert reason and "vtt" in reason


def test_backend_registry(config):
    assert {name for name, _ in backend_status(config)} == {
        "subtitles", "faster_whisper", "mlx_whisper", "whisper_cpp",
    }
    with pytest.raises(TranscriptionError):
        get_backend("nonexistent", config)


def test_select_backend_none_and_unavailable(config, tmp_path):
    from conftest import make_config

    off = make_config(tmp_path, transcript={"backend": "none"})
    with pytest.raises(TranscriptionError):
        select_backend(off)

    with pytest.raises(TranscriptionError) as excinfo:
        select_backend(config, "whisper_cpp")
    assert "not usable" in excinfo.value.message


def test_auto_selection_picks_subtitles_when_a_file_exists(config, staged_source):
    (staged_source / "video.hu.vtt").write_text(VTT, encoding="utf-8")
    assert select_backend(config, "auto", staged_source).name == "subtitles"


def test_auto_selection_fails_loudly_when_nothing_is_available(config, staged_source, monkeypatch):
    # Independent of what happens to be installed on the developer's machine.
    from msp.transcription import faster_whisper as fw, mlx_whisper as mlx, whisper_cpp as wcpp

    for module, cls in ((fw, "FasterWhisperBackend"), (mlx, "MlxWhisperBackend"),
                        (wcpp, "WhisperCppBackend")):
        monkeypatch.setattr(getattr(module, cls), "unavailable_reason",
                            lambda self, folder=None: "not installed (test)")
    with pytest.raises(TranscriptionError) as excinfo:
        select_backend(config, "auto", staged_source)
    assert "pending" in (excinfo.value.hint or "")
