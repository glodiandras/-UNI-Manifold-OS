"""Shared fixtures. No test in this suite touches the network."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from msp.config import Config
from msp.downloader import DownloadRequest, DownloadResult, Downloader

TAXONOMY = ["Történelem", "Fizika", "Irodalom", "Besorolatlan"]
ALIASES = {"tortenelem": "Történelem", "fizika": "Fizika", "matek": "Matematika"}


def make_config(tmp_path: Path, **overrides: Any) -> Config:
    """A hermetic config rooted in a temporary directory."""
    data: dict[str, Any] = {
        "output_root": "./staging",
        "video": {"max_height": 1080, "preferred_extension": "mp4"},
        "metadata": {"save_json": True, "save_raw_info": False},
        "transcript": {"enabled": False, "status": "pending", "backend": "auto"},
        "subtitles": {"download": False, "languages": ["hu"]},
        "organization": {
            "provider_folder": True,
            "subject_folder": True,
            "default_subject": "Besorolatlan",
            "provider_names": {"zanza.tv": "Zanza", "youtube": "YouTube", "generic": "Web"},
        },
        "subjects": {"taxonomy": TAXONOMY, "aliases": ALIASES},
        "archive": {"enabled": True, "dir": "./archive"},
        "logging": {"dir": "./logs", "level": "DEBUG", "json_events": False},
        "playlist": {"enabled": False, "max_items": 3},
        "download": {"retries": 1, "fragment_retries": 1, "socket_timeout": 5, "resume": True},
        "ytdlp": {},
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key] = {**data[key], **value}
        else:
            data[key] = value
    return Config.from_dict(data, project_root=tmp_path)


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return make_config(tmp_path)


def make_info(
    *,
    video_id: str = "abc123",
    title: str = "Az ókori Athén",
    url: str = "https://zanza.tv/tortenelem/az-okori-athen",
    duration: int = 612,
    height: int = 360,
    extractor: str = "generic",
) -> dict[str, Any]:
    """A yt-dlp-shaped info dict, including fields that must be dropped."""
    return {
        "id": video_id,
        "title": title,
        "webpage_url": url,
        "original_url": url,
        "extractor": extractor,
        "extractor_key": extractor.capitalize(),
        "duration": duration,
        "description": "Leírás.",
        "uploader": "Zanza.tv",
        "upload_date": "20240115",
        "width": int(height * 16 / 9),
        "height": height,
        "fps": 25,
        "ext": "mp4",
        "format_id": "18",
        "vcodec": "avc1",
        "acodec": "mp4a",
        "filesize": 1234567,
        "language": "hu",
        # must never reach metadata.json:
        "url": "https://cdn.example/signed?token=SECRET",
        "http_headers": {"Cookie": "secret"},
        "view_count": 4242,
        "formats": [
            {"format_id": "18", "ext": "mp4", "height": height, "width": int(height * 16 / 9),
             "vcodec": "avc1", "acodec": "mp4a", "filesize": 1234567},
            {"format_id": "137", "ext": "mp4", "height": 1080, "width": 1920,
             "vcodec": "avc1", "acodec": "none", "filesize": 9999999},
            {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a"},
        ],
        "subtitles": {"hu": [{"ext": "vtt", "url": "https://example/sub.vtt"}]},
        "automatic_captions": {},
    }


class FakeDownloader(Downloader):
    """Deterministic stand-in for yt-dlp: writes a small file, no network."""

    name = "fake"

    def __init__(self, info: dict[str, Any] | None = None, *, media_bytes: bytes = b"FAKEMEDIA") -> None:
        self.info = info if info is not None else make_info()
        self.media_bytes = media_bytes
        self.probe_calls: list[str] = []
        self.download_calls: list[DownloadRequest] = []
        self.fail_with: Exception | None = None
        self.subtitle_text: str | None = None

    @property
    def version(self) -> str:
        return "fake-1.0"

    def probe(self, url: str, *, allow_playlist: bool = False, flat: bool = False) -> dict[str, Any]:
        self.probe_calls.append(url)
        if self.fail_with is not None:
            raise self.fail_with
        return dict(self.info)

    def download(self, request: DownloadRequest) -> DownloadResult:
        self.download_calls.append(request)
        if self.fail_with is not None:
            raise self.fail_with
        target = Path(request.target_dir)
        target.mkdir(parents=True, exist_ok=True)
        media = target / f"{request.stem}.mp4"
        media.write_bytes(self.media_bytes)
        subtitles = []
        if self.subtitle_text is not None:
            subtitle = target / f"{request.stem}.hu.vtt"
            subtitle.write_text(self.subtitle_text, encoding="utf-8")
            subtitles.append(subtitle)
        info = dict(self.info)
        info["requested_downloads"] = [{"filepath": str(media)}]
        return DownloadResult(media_path=media, info=info, subtitle_files=subtitles)


@pytest.fixture
def downloader() -> FakeDownloader:
    return FakeDownloader()


@pytest.fixture
def real_project_root() -> Path:
    """The actual repository root, for tests that read the shipped config."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _isolate_project_root(monkeypatch, tmp_path):
    """Never let a test pick up the developer's own project root."""
    monkeypatch.delenv("MSP_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("MSP_CONFIG", raising=False)
    yield


@pytest.fixture
def staged_source(tmp_path, config, downloader):
    """One fully staged source folder, produced through the real pipeline."""
    from msp.pipeline import ingest_url

    outcome = ingest_url(
        "https://zanza.tv/tortenelem/az-okori-athen",
        config=config, downloader=downloader, subject="Történelem",
    )
    assert outcome.status == "downloaded", outcome.message
    return outcome.path


def copy_tree(src: Path, dst: Path) -> Path:
    shutil.copytree(src, dst)
    return dst
