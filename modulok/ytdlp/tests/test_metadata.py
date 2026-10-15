"""Metadata curation: keep what is stable, drop what is volatile or sensitive."""

from conftest import make_info

from msp.metadata import (
    best_available_height,
    best_progressive_height,
    curate,
    iter_formats,
    progressive_formats,
    resolution_of,
    subtitle_languages,
)


def curated():
    return curate(
        make_info(),
        page_url="https://zanza.tv/tortenelem/az-okori-athen",
        source_id="zanza-abc123",
        downloaded_at="2026-09-04T10:00:00+00:00",
        media_file="video.mp4",
        format_selector="best[height<=1080][ext=mp4]/best",
        ytdlp_version="2026.08.19",
    )


def test_expected_fields_are_present():
    data = curated()
    for key in ("id", "title", "url", "uploader", "upload_date", "duration",
                "description", "webpage_url", "extractor", "resolution", "fps"):
        assert key in data, key


def test_url_is_the_page_not_the_signed_media_url():
    data = curated()
    assert data["url"] == "https://zanza.tv/tortenelem/az-okori-athen"
    assert "token=SECRET" not in str(data)


def test_volatile_and_sensitive_fields_are_dropped():
    data = curated()
    for key in ("view_count", "http_headers", "formats", "automatic_captions"):
        assert key not in data
    assert "Cookie" not in str(data)


def test_duration_is_also_stored_as_hms():
    assert curated()["duration_hms"] == "00:10:12"


def test_pipeline_provenance_block():
    block = curated()["pipeline"]
    assert block["source_id"] == "zanza-abc123"
    assert block["ffmpeg_used"] is False
    assert block["media_file"] == "video.mp4"
    assert block["yt_dlp_version"] == "2026.08.19"


def test_unknown_fields_are_omitted_not_invented():
    info = {"id": "x", "title": "T", "webpage_url": "https://x"}
    data = curate(info, page_url="https://x", source_id="s", downloaded_at="now",
                  media_file=None, format_selector="best")
    assert "uploader" not in data
    assert "resolution" not in data
    assert data["pipeline"]["media_file"] is None or "media_file" not in data["pipeline"]


def test_progressive_format_detection():
    info = make_info()
    assert [fmt.format_id for fmt in progressive_formats(info)] == ["18"]
    assert best_progressive_height(info) == 360
    assert len(iter_formats(info)) == 3


def test_video_only_and_audio_only_formats_are_not_progressive():
    formats = {fmt.format_id: fmt for fmt in iter_formats(make_info())}
    assert formats["137"].is_progressive is False   # video only
    assert formats["140"].is_progressive is False   # audio only


def test_resolution_helpers():
    assert resolution_of({"width": 640, "height": 360}) == "640x360"
    assert resolution_of({"height": 360}) == "360p"
    assert resolution_of({}) is None
    assert subtitle_languages(make_info()) == ["hu"]
    assert subtitle_languages(make_info(), automatic=True) == []


# --- merging (1080p) --------------------------------------------------------

def test_best_available_height_sees_video_only_streams():
    info = make_info()
    info["formats"] = [
        {"format_id": "18", "ext": "mp4", "height": 360, "width": 640,
         "vcodec": "avc1", "acodec": "mp4a"},
        {"format_id": "137", "ext": "mp4", "height": 1080, "width": 1440,
         "vcodec": "avc1", "acodec": "none"},
    ]
    assert best_progressive_height(info) == 360     # what a single file offers
    assert best_available_height(info) == 1080      # what merging can reach


def test_best_available_height_ignores_storyboards():
    info = make_info()
    info["formats"] = [
        {"format_id": "sb0", "ext": "mhtml", "height": 9000, "width": 9000,
         "vcodec": "images", "acodec": "none"},
        {"format_id": "18", "ext": "mp4", "height": 360, "width": 640,
         "vcodec": "avc1", "acodec": "mp4a"},
    ]
    assert best_available_height(info) == 360


def test_ffmpeg_used_is_recorded_when_streams_were_merged():
    info = make_info()
    info["requested_formats"] = [{"format_id": "137"}, {"format_id": "140"}]
    data = curate(info, page_url="https://x", source_id="s", downloaded_at="now",
                  media_file="video.mp4", format_selector="bestvideo+bestaudio")
    assert data["pipeline"]["ffmpeg_used"] is True


def test_ffmpeg_used_is_false_for_a_single_file_download():
    data = curate(make_info(), page_url="https://x", source_id="s", downloaded_at="now",
                  media_file="video.mp4", format_selector="best")
    assert data["pipeline"]["ffmpeg_used"] is False
