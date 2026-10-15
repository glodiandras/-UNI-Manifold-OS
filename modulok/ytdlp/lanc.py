"""A `video_letoltes` feladat lépése (C20a): link → letöltés (yt-dlp) → konvertálás, ha nem natív → staging → pillanatkép az ytdlp tárba.

A lánc **a vaultba nem ír** (a bevitel a C20b gépi-írás `mozgat` művelete): a staging (`{ytdlp}/staging`) a letöltő saját munkamappája, az
ytdlp tároló (`var/ytdlp.git`) a szöveges részének pillanatképe. Hálózatot csak a letöltés használ (D3). Modellt nem tölt be.

A letöltést az `msp` (a legacy másolata) végzi; ez a modul a 2.0-s környezetet adja neki (útvonalak a `config/os.toml`-ból, a pinelt ffmpeg),
a konvertálást a letöltés és a staging-írás **közé** teszi (`KonvertaloLetolto`), így a `source.md`, `metadata.json` és `integration.json` már a
natív fájl nevét tartalmazza, és az eredeti az `archive/` alá kerül. A pillanatkép két rövid, kör-záras szakasz (a letöltés alatt a zár
szabad): előtte a kézi változások külön commitba (L14), utána a lánc útjai egy gépi commitba (`Mos-Forras: mos-video`, `Mos-Feladat`).

**Javító 3 (A3-08, A3-09, A3-17, A3-18)**: a gépi commit útlistája **csak** az `ingest_url` által visszaadott célmappák és az archívum alatti,
tartalmilag szöveges (nem NUL-bájtos, nem nagy, nem bináris kiterjesztésű) utak — a `{ytdlp}` munkafa a modul kódját és konfigját is
tartalmazza, azt a lánc soha nem commitolja (a letöltés alatt a felhasználó szerkeszthet). Az ffmpeg a `[utak] ffmpeg`, a futás előtt a
`config/runtime-pins.env` sha256-jával ellenőrizve (zárva hibázik); a node a `[utak] node`; a PATH-ból, a környezetből semmi nem jön.
"""
from __future__ import annotations

import dataclasses
import os
import sys
import unicodedata
from pathlib import Path
from typing import Callable

from . import eszkoz, konvertalas

SZOVEGES_MAX_BAJT = 8 << 20          # a gépi commitba kerülő szöveges fájl legfeljebb ekkora (a source.md, metadata.json ennek töredéke)
SZOVEGES_MINTA_BAJT = 8192           # a NUL-bájt keresése az elejében

SRC = Path(__file__).resolve().parent / "src"


def msp():
    """A másolt `msp` csomag moduljai (a `src/` az import-útra)."""
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    import msp.archive as archivum
    import msp.config as konfig
    import msp.downloader as letolto
    import msp.pipeline as folyamat
    return konfig, letolto, folyamat, archivum


def msp_konfig(cfg, staging: Path | None = None):
    """Az `msp` konfigurációja a 2.0 útjaival: a staging a `[utak] staging`, az archívum a `[utak] ytdlp_archivum`, az ffmpeg a `[utak] ffmpeg`
    (az `msp` maga semmit nem keres: A3-17), a node a `[utak] node`, ha megvan (A3-18). Az ffmpeg hash-ellenőrzése a `letoltes` dolga."""
    konfig, *_ = msp()
    kiindulo = konfig.Config.load(project_root=cfg.path("ytdlp"), output_root=staging or cfg.path("staging"))
    node = cfg.path("node")
    yt = dataclasses.replace(kiindulo.ytdlp, ffmpeg_location=str(cfg.path("ffmpeg")),
                             node_location=str(node) if node.is_file() and os.access(node, os.X_OK) else "auto")
    return dataclasses.replace(kiindulo, ytdlp=yt, archive=dataclasses.replace(kiindulo.archive, dir=str(cfg.path("ytdlp_archivum"))))


def _video_beallitas(cfg) -> dict:
    v = cfg.section("video")
    return {"crf": int(v.get("konvertalas_crf", 20)), "szal": int(v.get("konvertalas_szal", 2)),
            "nativ": tuple(v.get("nativ_video", konvertalas.ALAP_VIDEO)), "hang": tuple(v.get("nativ_hang", konvertalas.ALAP_HANG)),
            "megtart": bool(v.get("eredeti_megtart", True))}


class KonvertaloLetolto:
    """Az `msp.downloader.Downloader` burkolója: a letöltés után a nem natív videót a helyén natívvá teszi (konvertalas.konvertal).

    A `Downloader` ABC-t nem örökli (a `msp` import nélkül importálható marad); az `msp.pipeline` csak a `probe`, `download` és
    `version` metódusokat használja. Konvertálási hiba nem hibáztatja a letöltést: a letöltött fájl marad, a hiba a naplóban és a
    `result.info["manifold_konvertalas"]`-ban."""
    name = "konvertalo"

    def __init__(self, belso, *, ffmpeg: str, staging: Path, eredeti_gyoker: Path | None, beallitas: dict, log: Callable[[str], None]):
        self._belso, self._ffmpeg, self._staging = belso, ffmpeg, Path(staging)
        self._eredeti, self._b, self._log = eredeti_gyoker, beallitas, log

    @property
    def version(self):
        return self._belso.version

    def probe(self, url, **kw):
        return self._belso.probe(url, **kw)

    def download(self, request):
        eredmeny = self._belso.download(request)
        if not eredmeny.media_path:
            return eredmeny
        forras = Path(eredmeny.media_path)
        try:
            relativ = str(Path(request.target_dir).resolve().relative_to(self._staging.resolve()))
        except ValueError:
            relativ = Path(request.target_dir).name
        try:
            r = konvertalas.konvertal(self._ffmpeg, forras, eredeti_gyoker=self._eredeti if self._b["megtart"] else None, relativ=relativ,
                                      crf=self._b["crf"], szal=self._b["szal"], nativ=self._b["nativ"], hang=self._b["hang"], log=self._log)
        except konvertalas.KonvertalasHiba as e:
            self._log(f"FIGYELEM: a konvertálás nem sikerült, a letöltött fájl marad ({forras.name}): {e}")
            eredmeny.info["manifold_konvertalas"] = {"mod": "hiba", "hiba": str(e)}
            return eredmeny
        eredmeny.info["manifold_konvertalas"] = {k: r[k] for k in ("mod", "ok", "mp")}
        if r["mod"] in ("remux", "atkodol"):
            self._log(f"konvertálva ({r['mod']}, {r['mp']} s): {Path(r['ut']).name}")
            eredmeny.media_path = Path(r["ut"])
        return eredmeny


# ------------------------------------------------------------------ pillanatkép az ytdlp tárba

def ytdlp_tar(cfg):
    """Az élő ytdlp pillanatkép-tároló, vagy `None` (nincs `var/ytdlp.git` vagy a munkafa)."""
    from core import frame
    return frame.live_repos(cfg).get("ytdlp")


def pillanat_elo(cfg, log=print) -> bool:
    """A felhasználó (és a kód) nem rögzített változásai külön `Mos-Forras: kezi` commitba, a lánc útjai ELŐTT (L14)."""
    from core import frame
    repo = ytdlp_tar(cfg)
    if repo is None:
        log("[video] az ytdlp pillanatkép-tároló nem élő: a staging pillanatkép nélkül készül")
        return False
    with frame.run_lock(cfg, wait=True, log=log):
        sha = repo.commit("kézi változások a videólánc előtt", {"Mos-Forras": "kezi"})
    if sha:
        log(f"[video] kézi változások rögzítve az ytdlp tárban ({str(sha)[:10]})")
    return True


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def celok_relativ(munkafa: Path, celok) -> list[str]:
    """A célmappák (és az archívum) a munkafához képest, `/`-jelekkel, NFC-ben; a munkafán kívüli és a munkafa gyökere maga kimarad."""
    gy = Path(os.path.realpath(munkafa))
    ki: list[str] = []
    for c in celok or ():
        try:
            rel = Path(os.path.realpath(c)).relative_to(gy).as_posix()
        except ValueError:
            continue
        if rel not in ("", "."):
            ki.append(_nfc(rel))
    return ki


def szoveges_utak(munkafa: Path, utak: list[str], max_bajt: int = SZOVEGES_MAX_BAJT) -> list[str]:
    """Az útlistából a szöveges, kis fájlok (A3-09): a bináris kiterjesztésű (`core/mediatipus.py`), a symlink, a `max_bajt`-nál nagyobb és a
    NUL-bájtot tartalmazó fájl kimarad. A már nem létező út (törlés) átmegy: a törlés is változás, és a git nem vesz fel olyat, ami nincs."""
    from core import mediatipus
    ki: list[str] = []
    for u in utak:
        if mediatipus.binaris_e(u):
            continue
        p = Path(munkafa) / u
        try:
            if os.path.lexists(p):
                if p.is_symlink() or not p.is_file() or p.stat().st_size > max_bajt:
                    continue
                with open(p, "rb") as f:
                    if b"\0" in f.read(SZOVEGES_MINTA_BAJT):
                        continue
        except OSError:
            continue
        ki.append(u)
    return ki


def pillanat_utan(cfg, darab: int, log=print, *, celok=None, uzenet: str | None = None, tetel: str | None = None) -> str | None:
    """A lánc által írt utak egy gépi commitba az ytdlp tárban (`Mos-Forras: mos-video`, `Mos-Feladat`). → a commit sha-ja.

    A `celok` a lánc saját mappái (az `ingest_url` visszaadott célmappái, az archívum): a commitba **csak** az ezek alatti, szöveges utak
    kerülnek (A3-08). A munkafa többi piszkos útja (a `modulok/ytdlp` kódja, konfigja, a felhasználó közbeni szerkesztése) érintetlen marad,
    és a következő `pillanat_elo` `kezi` commitja viszi. `celok` nélkül nincs mit commitolni."""
    from core import frame, snapshot
    repo = ytdlp_tar(cfg)
    if repo is None:
        return None
    with frame.run_lock(cfg, wait=True, log=log):
        elok = celok_relativ(repo.work_tree, celok)
        sajat = [u for u in repo.dirty_paths() if any(_nfc(u) == c or _nfc(u).startswith(c + "/") for c in elok)]
        utak = szoveges_utak(repo.work_tree, sajat)
        if len(utak) < len(sajat):
            log(f"[video] {len(sajat) - len(utak)} nem szöveges vagy túl nagy út kimarad a pillanatképből")
        if not utak:
            return None
        trailerek = {snapshot.TRAILER_RUN: frame.new_id("VIDEO"), snapshot.TRAILER_ITEM: tetel or f"letoltes-{darab}",
                     "Mos-Forras": "mos-video"}
        if os.environ.get("MOS_FELADAT"):
            trailerek[snapshot.TRAILER_TASK] = os.environ["MOS_FELADAT"]
        sha = repo.commit_machine(uzenet or f"videólánc: {darab} forrás letöltve a stagingbe", trailerek, utak)
    log(f"[video] pillanatkép az ytdlp tárban: {len(utak)} út ({str(sha)[:10] if sha else '-'})")
    return sha


# ------------------------------------------------------------------ a lánc

def letoltes(cfg, urlek: list[str], *, proba_gyoker: Path | None = None, stop_fajl: str | None = None, log=print,
             kozvetlen_tetelek: dict[str, dict] | None = None, felirat_fetch=None, eredmeny_fajl: Path | None = None) -> int:
    """A linkek letöltése a stagingbe. → kilépési kód: 0 minden rendben (vagy már megvolt), 1 legalább egy hiba, 2 hiányzó eszköz.

    `proba_gyoker`: a staging és az archívum ide kerül (nem a `[utak]` szerinti), pillanatkép nincs — a kézi próba.

    A bejárás közvetlen fájljai (84. döntés, javasolt kiegészítés; `kozvetlen_tetelek`, alapból a mentett bejárásokból): ugyanaz az
    `ingest_url` út (duplikátum, archívum, konvertálás), de a forrás-link és a cím az oldalé, a kérés a bejáró őszinte User-Agentjével
    megy, és a letöltés után a kiadói felirat a forrásmappába kerül, belőle az átirat (modell nélkül).

    `eredmeny_fajl` (F4): ide kerül a letöltött vagy már meglévő linkek staging-relatív forrásmappáinak listája (`{"mappak": […]}`),
    a „Letöltés és bevitel” a core-ban ebből adja a bevitelnek a saját mappáit (nem a staging összes várakozó tételét)."""
    from . import kozvetlen
    konfig, letolto, folyamat, archivum = msp()
    staging = proba_gyoker / "staging" if proba_gyoker else cfg.path("staging")
    mcfg = msp_konfig(cfg, staging)
    if proba_gyoker:
        mcfg = dataclasses.replace(mcfg, archive=dataclasses.replace(mcfg.archive, dir=str(proba_gyoker / "archive")))
    try:
        ffmpeg = eszkoz.ffmpeg_ellenorzott(cfg)          # A3-17: az ellenőrzött és a futtatott bináris ugyanaz (`mcfg.ytdlp.ffmpeg_location`)
    except eszkoz.EszkozHiba as e:
        log(f"HIBA: {e}")
        return 2
    try:
        letolto.require_ytdlp(mcfg)
    except Exception as e:  # noqa: BLE001 — az msp típusos hibája, a hint a felhasználónak szól
        log(f"HIBA: {getattr(e, 'message', e)}\n{getattr(e, 'hint', '')}")
        return 2
    b = _video_beallitas(cfg)
    belso = letolto.create_downloader(mcfg, progress=False)
    dl = KonvertaloLetolto(belso, ffmpeg=str(ffmpeg), staging=staging, eredeti_gyoker=(proba_gyoker / "eredeti" if proba_gyoker
                           else cfg.path("video_eredeti")), beallitas=b, log=log)
    if not proba_gyoker:
        pillanat_elo(cfg, log)
    arch = archivum.Archive(mcfg.archive_dir, enabled=mcfg.archive.enabled)
    if kozvetlen_tetelek is None:
        from .bejaras import kozvetlen_tetelek as _kt
        try:
            kozvetlen_tetelek = _kt(cfg)
        except Exception as e:  # noqa: BLE001 — a mentett bejárás olvashatatlan: a link a szokásos úton megy
            log(f"FIGYELEM: a mentett bejárások nem olvashatók ({e}); a linkek a szokásos úton töltődnek le")
            kozvetlen_tetelek = {}
    rossz = letoltve = kihagyva = 0
    kimaradt: list[str] = []
    sajat_mappak: list[str] = []
    celok: list[Path] = [Path(mcfg.archive_dir)]       # A3-08: a gépi commit csak ezek alatti utakat vihet
    try:
        for i, url in enumerate(urlek):
            if stop_fajl and os.path.exists(stop_fajl):
                kimaradt = urlek[i:]
                log(f"A leállítás kérve: {len(kimaradt)} link kimarad.")
                break
            log(f"[manifold-progress] {int(100 * i / max(len(urlek), 1))}%")
            log(f"── {i + 1}/{len(urlek)}: {url}")
            kt = kozvetlen_tetelek.get(url)
            if kt:
                log(f"közvetlen fájl: {kt.get('cim')} ({kt.get('minoseg') or '?'}) — az oldal: {kt.get('oldal')}")
                r = folyamat.ingest_url(url, config=mcfg, downloader=dl, archive=arch, page_url=kt.get("oldal"),
                                        page_title=kt.get("cim"), language=kt.get("nyelv"), user_agent=mcfg.crawl.user_agent)
            else:
                r = folyamat.ingest_url(url, config=mcfg, downloader=dl, archive=arch)
            if getattr(r, "path", None):
                celok.append(Path(r.path))
                if kt and kt.get("felirat") and r.status in (folyamat.STATUS_DOWNLOADED, folyamat.STATUS_SKIPPED):
                    kozvetlen.felirat_be(Path(r.path), kt["felirat"], kt.get("nyelv"), mcfg, fetch=felirat_fetch, log=log)
            if r.status in (folyamat.STATUS_DOWNLOADED, folyamat.STATUS_SKIPPED) and getattr(r, "path", None):
                try:
                    rel = Path(r.path).resolve().relative_to(Path(staging).resolve()).as_posix()
                except (OSError, ValueError):
                    rel = None
                if rel and rel != "." and rel not in sajat_mappak:
                    sajat_mappak.append(rel)
            if r.status == folyamat.STATUS_DOWNLOADED:
                letoltve += 1
                log(f"Kész: {r.path}")
            elif r.status == folyamat.STATUS_SKIPPED:
                kihagyva += 1
                log(f"Már megvan: {r.path}")
            else:
                rossz += 1
                log(f"Hiba: {r.message}" + (f" ({r.error.hint})" if getattr(r.error, 'hint', None) else ""))
        log("[manifold-progress] 100%")
    finally:
        if not proba_gyoker:         # váratlan kivételnél is rögzítjük, ami a stagingbe került (a következő futás ne „kézi változásként” lássa)
            pillanat_utan(cfg, letoltve, log, celok=celok)
    if eredmeny_fajl is not None:
        import json
        from core import tartos
        Path(eredmeny_fajl).parent.mkdir(parents=True, exist_ok=True)
        tartos.atomi_ir(eredmeny_fajl, json.dumps({"mappak": sajat_mappak, "letoltve": letoltve, "megvolt": kihagyva, "hiba": rossz},
                                                  ensure_ascii=False).encode("utf-8"))
    log(f"Összegzés: {letoltve} letöltve, {kihagyva} már megvolt, {rossz} hiba" + (f", {len(kimaradt)} kimaradt" if kimaradt else ""))
    return 1 if rossz else 0
