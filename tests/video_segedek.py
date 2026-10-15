"""Közös segédek a videólánc tesztjeihez (C20a): az `msp` (a legacy másolata) hamis letöltővel, valódi staging-forrásmappák előállítása.

A staging-mappát a valódi `msp.pipeline.ingest_url` állítja elő (nem kézzel írt fixtúra), így az `olvas`, a `leltar`, a `visszajelez` és a
`keres_azonosito` a letöltő valódi kimenetén fut — hálózat nélkül (hamis letöltő, mint a legacy `conftest.py`-ban)."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from tests.helpers import REPO

SRC = REPO / "modulok" / "ytdlp" / "src"
FFMPEG = REPO / "runtime" / "ffmpeg" / "ffmpeg"


def msp():
    """Az `msp` modulok (a `modulok/ytdlp/src` az import-útra)."""
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    import msp.config as konfig
    import msp.downloader as letolto
    import msp.pipeline as folyamat
    return konfig, letolto, folyamat


def ffmpeg_elerheto() -> bool:
    return FFMPEG.is_file()


def pin_es_ffmpeg(cfg, root: Path, tartalom: str = "#!/bin/sh\nexit 0\n", valodi: Path | None = None) -> Path:
    """Az álgyökér `[utak] ffmpeg` helyére egy ffmpeg (alapból hamis; `valodi`: symlink a pinelt buildre) és a hozzá tartozó
    `FFMPEG_BIN_SHA256` pin a `config/runtime-pins.env`-ben (Javító 3, A3-17: a lánc a hash nélküli ffmpeg-et nem futtatja)."""
    ff = cfg.path("ffmpeg")
    ff.parent.mkdir(parents=True, exist_ok=True)
    if ff.is_symlink() or ff.exists():
        ff.unlink()
    if valodi is not None:
        ff.symlink_to(valodi)
    else:
        ff.write_text(tartalom, encoding="utf-8")
        ff.chmod(0o755)
    (root / "config").mkdir(exist_ok=True)
    (root / "config" / "runtime-pins.env").write_text(f"FFMPEG_BIN_SHA256={hashlib.sha256(ff.read_bytes()).hexdigest()}\n", encoding="utf-8")
    return ff


def info(video_id: str = "abc123", cim: str = "Az ókori Athén", url: str = "https://zanza.tv/tortenelem/az-okori-athen",
         hossz: int = 612) -> dict[str, Any]:
    return {"id": video_id, "title": cim, "webpage_url": url, "original_url": url, "extractor": "generic",
            "extractor_key": "Generic", "duration": hossz, "description": "Leírás.", "uploader": "Zanza.tv", "upload_date": "20240115",
            "width": 640, "height": 360, "fps": 25, "ext": "mp4", "format_id": "18", "vcodec": "avc1", "acodec": "mp4a",
            "filesize": 1234567, "language": "hu",
            "formats": [{"format_id": "18", "ext": "mp4", "height": 360, "width": 640, "vcodec": "avc1", "acodec": "mp4a"}],
            "subtitles": {}, "automatic_captions": {}}


def hamis_letolto(inf: dict | None = None, *, bajtok: bytes = b"FAKEMEDIA", fajl=None):
    """Determinisztikus yt-dlp-pótlék: egy kis fájlt ír a célmappába (`fajl(cel_mappa, stem) -> Path`: saját médiafájl, pl. MKV)."""
    _, letolto, _ = msp()

    class Hamis(letolto.Downloader):
        name = "hamis"

        def __init__(self):
            self.info = inf if inf is not None else info()
            self.hivasok: list[str] = []
            self.hiba: Exception | None = None

        @property
        def version(self):
            return "hamis-1.0"

        def probe(self, url, *, allow_playlist=False, flat=False):
            self.hivasok.append(url)
            if self.hiba is not None:
                raise self.hiba
            return dict(self.info)

        def download(self, request):
            if self.hiba is not None:
                raise self.hiba
            cel = Path(request.target_dir)
            cel.mkdir(parents=True, exist_ok=True)
            if fajl is not None:
                media = fajl(cel, request.stem)
            else:
                media = cel / f"{request.stem}.mp4"
                media.write_bytes(bajtok)
            ki = dict(self.info)
            ki["requested_downloads"] = [{"filepath": str(media)}]
            return letolto.DownloadResult(media_path=media, info=ki, subtitle_files=[])

    return Hamis()


def msp_konfig(gyoker: Path, **felulir):
    """Zárt `msp` konfiguráció az ideiglenes `gyoker` alatt (staging, archívum, napló)."""
    konfig, _, _ = msp()
    adat: dict[str, Any] = {
        "output_root": "./staging", "video": {"max_height": 1080, "preferred_extension": "mp4"},
        "metadata": {"save_json": True, "save_raw_info": False},
        "transcript": {"enabled": False, "status": "pending", "backend": "auto"}, "subtitles": {"download": False, "languages": ["hu"]},
        "organization": {"provider_folder": True, "subject_folder": True, "default_subject": "Besorolatlan",
                         "provider_names": {"zanza.tv": "Zanza", "youtube": "YouTube", "generic": "Web"}},
        "subjects": {"taxonomy": ["Történelem", "Fizika", "Irodalom", "Besorolatlan"],
                     "aliases": {"tortenelem": "Történelem", "fizika": "Fizika"}},
        "archive": {"enabled": True, "dir": "./archive"}, "logging": {"dir": "./logs", "level": "WARNING", "json_events": False},
        "playlist": {"enabled": False, "max_items": 3}, "crawl": {}, "download": {"retries": 1, "fragment_retries": 1, "socket_timeout": 5, "resume": True},
        "ytdlp": {},
    }
    adat.update(felulir)
    return konfig.Config.from_dict(adat, project_root=gyoker)


def forras(gyoker: Path, url: str = "https://zanza.tv/tortenelem/az-okori-athen", *, video_id: str = "abc123", cim: str = "Az ókori Athén",
           tema: str = "Történelem", letolto=None, **felulir) -> Path:
    """Egy teljes staging forrásmappa a valódi pipeline-nal (`ingest_url`); → a mappa."""
    _, _, folyamat = msp()
    cfg = msp_konfig(gyoker, **felulir)
    r = folyamat.ingest_url(url, config=cfg, downloader=letolto or hamis_letolto(info(video_id, cim, url)), subject=tema)
    assert r.status == "downloaded", r.message
    return Path(r.path)


def szintetikus_video(cel: Path, kodek: str = "libx264", kontener: str = "mkv", hang: str = "aac", mp: int = 2) -> Path:
    """Egy 2 másodperces teszt-videó az ffmpeg `lavfi` forrásaiból (a pinelt runtime ffmpeg-gel); → a fájl."""
    cel.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(FFMPEG), "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc=duration={mp}:size=320x240:rate=15",
           "-f", "lavfi", "-i", f"sine=frequency=440:duration={mp}", "-c:v", kodek]
    if kodek == "libvpx-vp9":
        cmd += ["-deadline", "realtime", "-cpu-used", "8"]
    elif kodek == "libsvtav1":
        cmd += ["-preset", "12"]
    cmd += ["-c:a", hang, "-shortest", str(cel)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-500:]
    return cel


def masol_mappa(forras_mappa: Path, cel: Path) -> Path:
    shutil.copytree(forras_mappa, cel)
    return cel
