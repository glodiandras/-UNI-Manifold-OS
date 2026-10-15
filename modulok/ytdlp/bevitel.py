"""Behúzott/kiválasztott helyi videó- vagy hangfájl a stagingbe (C20b, 7. pont) — a link nélküli bevitel.

A felület a fájlt darabonként a core beérkező mappájába tölti (`POST /api/video/bejovo` → `{video_bejovo}/<csoport>/`); a
`video_integralas` feladat lépése ezzel a modullal **staging-forrásmappát** készít belőle (a msp sémája szerint: `video.<kit>`,
`source.md`, `metadata.json`, `integration.json`; átirat nincs — a lánc a router `atirat` modelljével ír át), így a vault-oldali
lánc a linkes és a behúzott forrást ugyanúgy kezeli. A nem natív fájl itt alakul natívvá (`konvertalas.konvertal`, mint a letöltésnél:
az eredeti az `archive/` alá kerül, nem törlődik).

A forrásmappa: `{staging}/Helyi/Besorolatlan/<törzs>/`; az azonosító a fájl sha256-jának eleje (`helyi-<16 hex>`), így ugyanaz a fájl
kétszer behúzva is egy forrás (a második `mar_megvan`/`mar_bent`). A beérkező fájl a forrásmappába **költözik** (`rename_excl`,
azonos köteten), a beérkező mappa a saját `var/` területünk.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path

from core import tartos

from . import elhelyezes, konvertalas, staging

SZOLGALTATO, TARGY = "Helyi", "Besorolatlan"
# Csak videó: a hang a legacy szerint a `Média/` rétegbe kerülne, és a gépi írás `mozgat` videó-profilja a `[video] vault_mappa`
# alá visz — a hangfájl bevitele külön döntés (NAPLO, Ötletek).
KITERJESZTESEK = (".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi")


class BevitelHiba(RuntimeError):
    """A fájl nem vehető át (az ok a fájlé)."""


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for d in iter(lambda: f.read(1 << 20), b""):
            h.update(d)
    return h.hexdigest()


def _json_ir(p: Path, adat: dict) -> None:
    tartos.kizaro_ir(p, (json.dumps(adat, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _fm(adat: dict) -> str:
    return "---\n" + "".join(f"{k}: {json.dumps(v, ensure_ascii=False)}\n" for k, v in adat.items()) + "---\n"


def forrasmappa(cfg, fajl: Path, *, staging_gyoker: Path | None = None, ffmpeg: str | None = None, log=print) -> Path:
    """Egy beérkező fájl → staging-forrásmappa (vagy a már meglévő, ha ugyanez a fájl bent áll). → a forrásmappa útja."""
    fajl = Path(fajl)
    if fajl.is_symlink() or not fajl.is_file() or fajl.stat().st_size == 0:
        raise BevitelHiba(f"nem fájl vagy üres: {fajl.name}")
    kit = fajl.suffix.lower()
    if kit not in KITERJESZTESEK:
        raise BevitelHiba(f"nem videófájl (mp4, m4v, mov, mkv, webm, avi): {fajl.name}")
    gyoker = Path(staging_gyoker or cfg.path("staging"))
    ff = ffmpeg or str(cfg.path("ffmpeg"))
    if konvertalas.felmeres(ff, fajl).video is None:
        raise BevitelHiba(f"a fájlban nincs videófolyam: {fajl.name}")
    sha = _sha256(fajl)
    vid = f"helyi-{sha[:16]}"
    meglevo = staging.keres_azonosito(vid, gyoker)
    if meglevo:
        log(f"[bevitel] már bent áll: {fajl.name} → {meglevo}")
        return Path(meglevo)
    cim = elhelyezes.fajlnev_torzs(fajl.stem)
    d = gyoker / SZOLGALTATO / TARGY / cim
    for i in range(2, 1000):
        if not d.exists():
            break
        d = gyoker / SZOLGALTATO / TARGY / f"{cim} ({i})"
    d.mkdir(parents=True)
    media = d / f"video{kit}"
    tartos.rename_excl(fajl, media)
    v = cfg.section("video")
    try:
        r = konvertalas.konvertal(ff, media, eredeti_gyoker=cfg.path("video_eredeti") if bool(v.get("eredeti_megtart", True)) else None,
                                  relativ=str(d.relative_to(gyoker)), crf=int(v.get("konvertalas_crf", 20)),
                                  szal=int(v.get("konvertalas_szal", 2)),
                                  nativ=tuple(v.get("nativ_video", konvertalas.ALAP_VIDEO)),
                                  hang=tuple(v.get("nativ_hang", konvertalas.ALAP_HANG)), log=log)
        if r.get("mod") in ("remux", "atkodol"):
            media = Path(r["ut"])
    except konvertalas.KonvertalasHiba as e:
        log(f"[bevitel] FIGYELEM: a konvertálás nem sikerült, az eredeti marad ({fajl.name}): {e}")
    f = konvertalas.felmeres(ff, media)
    hossz = int(round(f.hossz_s)) if f.hossz_s else None
    most = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    meta = {"id": vid, "title": cim, "url": None, "webpage_url": None, "uploader": None, "upload_date": None, "duration": hossz,
            "description": f"Helyi fájl: {fajl.name}", "extractor": "helyi",
            "resolution": f"{f.szelesseg}x{f.magassag}" if f.szelesseg else None, "ext": media.suffix.lstrip("."),
            "vcodec": f.video, "acodec": f.hang, "filesize": media.stat().st_size,
            "pipeline": {"schema_version": 1, "source_id": vid, "downloaded_at": most, "eredeti_nev": fajl.name, "sha256": sha}}
    _json_ir(d / "metadata.json", meta)
    src ={"type": "source", "source_type": "video", "source_id": vid, "title": cim, "provider": SZOLGALTATO,
           "url": None, "subject": None, "language": None, "duration_seconds": hossz, "provider_video_id": vid,
           "media_file": media.name, "metadata_file": "metadata.json", "downloaded_at": most, "pipeline_status": "downloaded",
           "schema_version": 1}
    tartos.kizaro_ir(d / "source.md", (_fm(src) + f"\n# {cim}\n\nHelyi fájlból (a felületen behúzva): `{fajl.name}`.\n").encode("utf-8"))
    _json_ir(d / "integration.json", {"schema_version": 1, "source_id": vid, "source_note": "source.md", "media": media.name,
                                      "metadata": "metadata.json", "provider": SZOLGALTATO, "url": None, "title": cim,
                                      "language": None, "duration_seconds": hossz, "suggested_subject": None,
                                      "subject_source": None, "transcript_status": "missing", "integration_status": "pending"})
    staging.olvas(d)                         # a lánc pontosan így olvassa: a hiba itt derüljön ki, ne a vault-oldalon
    log(f"[bevitel] {fajl.name} → {d}")
    return d


def csoport(cfg, mappa: Path, **kw) -> tuple[list[Path], list[str]]:
    """Egy feltöltött csoport minden fájlja → (forrásmappák, hibák)."""
    ki, hibak = [], []
    for p in sorted(Path(mappa).iterdir()) if Path(mappa).is_dir() else []:
        if p.name.startswith("."):
            continue
        try:
            ki.append(forrasmappa(cfg, p, **kw))
        except (BevitelHiba, OSError, staging.StagingHiba, konvertalas.KonvertalasHiba) as e:
            hibak.append(f"{p.name}: {e}")
    return ki, hibak
