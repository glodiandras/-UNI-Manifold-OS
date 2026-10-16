"""A nem natív videó konvertálása beolvasáskor (C20a; CLAUDE.md 9. döntés: „natív lejátszó + ffmpeg-konverzió a beolvasáskor”).

A WKWebView natív lejátszója az mp4/mov/m4v konténerben álló H.264/HEVC videót és AAC/MP3/ALAC hangot játssza; az MKV, a WebM, az AVI,
az FLV és az AV1/VP9-videó nem. A konvertálás **csak az új beolvasásra** fut (letöltés, behúzott fájl): a meglévő videókhoz nem nyúl
(`bin/mos video felmeres` csak jelent). Az ffmpeg a `runtime/ffmpeg/ffmpeg` (pinelt build, `bin/mos runtime fetch ffmpeg`); ffprobe nincs,
a konténert, a kodekeket és a hosszt az `ffmpeg -i` kimenetéből olvassuk.

Szabály: ha a kodekek natívak (csak a konténer nem), **remux** (`-c copy`, veszteségmentes, másodpercek); különben a nem natív
folyam újrakódolódik (videó: `libx264 -crf`, hang: `aac`), a natív folyam másolódik. A kimenet `.part`-ba készül, ellenőrzés után
(hossz ±1% / ±1 s, a folyamok megvannak) kerül a helyére; az **eredeti nem törlődik** (`archive/` alá költözik indokkal, vagy
`.eredeti` néven marad). A kódolás alacsony prioritású (`os.nice(19)` a gyermekben, nem a PATH-os `nice`) és kevés szál: az app használata
közben is használható marad.

**Javító 3 (A3-19)**: a csere **soha nem ír felül**: a meglévő `<törzs>.mp4` (webm-forrásnál) vagy `<név>.eredeti` a kódolás ELŐTT megállítja a
konvertálást (`KonvertalasHiba`, az eredeti és a meglévő fájl érintetlen), és a csere maga is kizáró átnevezés (`tartos.rename_excl`); a
második lépés hibája visszaállítja az eredetit. Az archiválás hibája (`OSError`) nem veszíti el a fájlt: az eredeti `.eredeti` néven marad.
"""
from __future__ import annotations

import dataclasses
import os
import re
import shutil
import subprocess
from pathlib import Path

NATIV_KONTENER = (".mp4", ".m4v", ".mov")
ALAP_VIDEO = ("h264", "hevc")
ALAP_HANG = ("aac", "mp3", "alac")
HOSSZ_TURES_SZAZALEK = 1.0
HOSSZ_TURES_MP = 1.0

_BEMENET = re.compile(r"^Input #0, ([^,\n]+(?:,[^,\n]+)*), from ", re.M)
_HOSSZ = re.compile(r"^\s*Duration: (\d+):(\d{2}):(\d{2}(?:\.\d+)?)", re.M)
_FOLYAM = re.compile(r"^\s*Stream #\d+:\d+(?:\[[^\]]*\])?(?:\([^)]*\))?: (Video|Audio|Subtitle|Data|Attachment): (.*)$", re.M)
_KODEK = re.compile(r"^([A-Za-z0-9_]+)")
_MERET = re.compile(r"[, ](\d{2,5})x(\d{2,5})[, \[]")


class KonvertalasHiba(RuntimeError):
    """A konvertálás nem sikerült (az eredeti érintetlen)."""


@dataclasses.dataclass(frozen=True)
class Felmeres:
    """Egy médiafájl `ffmpeg -i` szerinti tulajdonságai."""
    konteneres: str = ""            # pl. "mov,mp4,m4a,3gp,3g2,mj2" vagy "matroska,webm"
    video: str | None = None        # az első (nem borító) videófolyam kodekje: h264, hevc, av1, vp9, …
    hang: str | None = None         # az első hangfolyam kodekje
    hossz_s: float | None = None
    szelesseg: int | None = None
    magassag: int | None = None

    def mp4_csalad(self) -> bool:
        return any(t in self.konteneres.split(",") for t in ("mp4", "mov"))


def felmeres_szoveg(stderr: str) -> Felmeres:
    """Az `ffmpeg -i` stderr-jének elemzése (a kimenetet nem tesszük a hívóra: tesztelhető fixtúrákkal)."""
    m = _BEMENET.search(stderr)
    konteneres = m.group(1) if m else ""
    m = _HOSSZ.search(stderr)
    hossz = (int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))) if m else None
    video = hang = None
    sz = mg = None
    for tipus, tobbi in _FOLYAM.findall(stderr):
        k = _KODEK.match(tobbi.strip())
        kodek = k.group(1) if k else None
        if tipus == "Video" and video is None and "(attached pic)" not in tobbi:
            video = kodek
            mm = _MERET.search(", " + tobbi)
            if mm:
                sz, mg = int(mm.group(1)), int(mm.group(2))
        elif tipus == "Audio" and hang is None:
            hang = kodek
    return Felmeres(konteneres, video, hang, hossz, sz, mg)


def felmeres(ffmpeg: str, fajl: str | Path, *, idokorlat_s: int = 60) -> Felmeres:
    """A fájl tulajdonságai: `ffmpeg -i` (kimenet nélkül hívva 1-es kilépési kóddal tér vissza — ez itt normális)."""
    try:
        p = subprocess.run([ffmpeg, "-hide_banner", "-nostdin", "-i", str(fajl)], capture_output=True, text=True,
                           errors="replace", timeout=idokorlat_s)
    except (OSError, subprocess.SubprocessError) as e:
        raise KonvertalasHiba(f"az ffmpeg nem futtatható: {e}") from e
    return felmeres_szoveg(p.stderr)


def nativ_e(f: Felmeres, kiterjesztes: str, *, video: tuple = ALAP_VIDEO, hang: tuple = ALAP_HANG) -> tuple[bool, str]:
    """Natívan lejátszható-e (a WKWebView-ban) → (igen/nem, az ok, ha nem). A konténer és a kodek is számít."""
    kit = kiterjesztes.lower()
    if kit not in NATIV_KONTENER or not f.mp4_csalad():
        return False, f"nem natív konténer ({kit or '?'}: {f.konteneres or 'ismeretlen'})"
    if f.video is None:
        return False, "nincs videófolyam"
    if f.video not in video:
        return False, f"nem natív videókodek ({f.video})"
    if f.hang is not None and f.hang not in hang:
        return False, f"nem natív hangkodek ({f.hang})"
    return True, ""


def terv(f: Felmeres, kiterjesztes: str, *, video: tuple = ALAP_VIDEO, hang: tuple = ALAP_HANG) -> dict:
    """A konvertálás terve: `{"mod": "nativ" | "remux" | "atkodol", "video": "copy" | "libx264", "hang": "copy" | "aac" | None, "ok"}`."""
    ok_nativ, ok = nativ_e(f, kiterjesztes, video=video, hang=hang)
    if ok_nativ:
        return {"mod": "nativ", "video": "copy", "hang": "copy" if f.hang else None, "ok": ""}
    video_ok = f.video in video
    hang_ok = f.hang is None or f.hang in hang
    return {"mod": "remux" if (video_ok and hang_ok) else "atkodol",
            "video": "copy" if video_ok else "libx264", "hang": ("copy" if hang_ok else "aac") if f.hang else None, "ok": ok}


def parancs(ffmpeg: str, forras: Path, cel: Path, t: dict, f: Felmeres, *, crf: int = 20, szal: int = 2) -> list[str]:
    """Az ffmpeg parancssor (a `nice` a hívóé): az első videó- és hangfolyam, felirat- és adatfolyam nélkül, `faststart`."""
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
           "-i", str(forras), "-map", "0:v:0", "-map", "0:a:0?", "-sn", "-dn", "-threads", str(max(1, szal))]
    if t["video"] == "copy":
        cmd += ["-c:v", "copy"] + (["-tag:v", "hvc1"] if f.video == "hevc" else [])
    else:
        cmd += ["-c:v", "libx264", "-crf", str(crf), "-preset", "medium", "-pix_fmt", "yuv420p"]
    if t["hang"] == "copy":
        cmd += ["-c:a", "copy"]
    elif t["hang"] == "aac":
        cmd += ["-c:a", "aac", "-b:a", "160k"]
    return cmd + ["-movflags", "+faststart", "-f", "mp4", str(cel)]


def _ellenoriz(eredeti: Felmeres, uj: Felmeres) -> None:
    if eredeti.video is not None and uj.video is None:
        raise KonvertalasHiba("az eredményben nincs videófolyam")
    if eredeti.hang is not None and uj.hang is None:
        raise KonvertalasHiba("az eredményben nincs hangfolyam")
    if eredeti.hossz_s and uj.hossz_s is not None:
        tures = max(HOSSZ_TURES_MP, eredeti.hossz_s * HOSSZ_TURES_SZAZALEK / 100)
        if abs(uj.hossz_s - eredeti.hossz_s) > tures:
            raise KonvertalasHiba(f"a hossz eltér: {eredeti.hossz_s:.1f} s → {uj.hossz_s:.1f} s")
    elif eredeti.hossz_s and uj.hossz_s is None:
        raise KonvertalasHiba("az eredmény hossza nem olvasható")


def _alacsony_prioritas() -> None:
    """A gyermekben, az `exec` előtt: `nice 19` (a PATH-os `nice` helyett; A3-18)."""
    try:
        os.nice(19)
    except OSError:
        pass


def _eredeti_archivalas(eredeti: Path, gyoker: Path, relativ: str, *, nev: str | None = None) -> Path:
    """Az eredeti az `archive/` alá (nem törlünk): `<gyökér>/<relatív>/<név>`, az `INDOK.md`-vel; ütközésnél számozott név."""
    cel_mappa = gyoker / relativ
    cel_mappa.mkdir(parents=True, exist_ok=True)
    nev = nev or eredeti.name
    cel = cel_mappa / nev
    i = 1
    while cel.exists():
        cel = cel_mappa / f"{Path(nev).stem}.{i}{Path(nev).suffix}"
        i += 1
    try:
        shutil.move(str(eredeti), str(cel))
    except OSError:
        if eredeti.exists():            # a fél-másolat nem maradhat félig írva; az eredeti a helyén van
            cel.unlink(missing_ok=True)
        raise
    indok = gyoker / "INDOK.md"
    if not indok.exists():
        indok.write_text("# A konvertálás előtti eredeti videók\n\nA videólánc a nem natív formátumú (MKV, WebM, AV1/VP9) letöltést a "
                         "beolvasáskor mp4-re konvertálta; a staging a konvertáltat tartalmazza, az eredeti ide "
                         "került, mert automatikus törlés nincs. A mappa bármikor törölhető a felhasználó jóváhagyásával.\n", encoding="utf-8")
    return cel


def konvertal(ffmpeg: str, forras: str | Path, *, eredeti_gyoker: str | Path | None = None, relativ: str = "", crf: int = 20,
              szal: int = 2, nativ: tuple = ALAP_VIDEO, hang: tuple = ALAP_HANG, log=lambda s: None) -> dict:
    """Egy videó natívvá tétele **a helyén** (a `<törzs>.mp4` a forrás mellé kerül; ha a forrás maga az `.mp4`, annak helyére).

    → `{"mod": "nativ" | "remux" | "atkodol", "ut": <a végleges út>, "eredeti": <az archivált/megtartott eredeti útja | None>,
    "ok": <miért nem natív>, "mp": <másodperc>}`. Natív forrásnál semmi nem történik. Hiba esetén (`KonvertalasHiba`) az eredeti
    érintetlen, a `.part` törölve. `eredeti_gyoker=None`: az eredeti `<név>.eredeti` néven marad a forrás mellett."""
    import time
    forras = Path(forras)
    f = felmeres(ffmpeg, forras)
    if f.video is None:
        return {"mod": "kihagy", "ut": str(forras), "eredeti": None, "ok": "nincs videófolyam", "mp": 0.0}
    t = terv(f, forras.suffix, video=nativ, hang=hang)
    if t["mod"] == "nativ":
        return {"mod": "nativ", "ut": str(forras), "eredeti": None, "ok": "", "mp": 0.0}
    vegleges = forras.with_suffix(".mp4")
    part = vegleges.with_name(vegleges.name + ".part")
    felre = forras.with_name(forras.name + ".eredeti")
    for foglalt, mi in ((felre, "az eredeti megőrzési neve"), (vegleges, "a végleges név")):
        if foglalt != forras and os.path.lexists(foglalt):
            raise KonvertalasHiba(f"{mi} már foglalt, nem írom felül: {foglalt.name}")
    cmd = parancs(ffmpeg, forras, part, t, f, crf=crf, szal=szal)
    log(f"konvertálás ({t['mod']}): {forras.name} — {t['ok']}")
    t0 = time.monotonic()
    try:
        # a stderr a stdoutra olvad (a `-progress pipe:1` kulcs=érték sorai között a hibasorok): nincs holtpont, a hiba a farokban
        utolso, farok = -1, []
        with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
                              preexec_fn=_alacsony_prioritas) as p:
            for sor in p.stdout:
                if sor.startswith("out_time_us="):
                    if f.hossz_s:
                        try:
                            szazalek = int(min(99, int(sor.split("=", 1)[1]) / 1e6 / f.hossz_s * 100))
                        except ValueError:
                            continue
                        if szazalek >= utolso + 10:
                            utolso = szazalek
                            log(f"konvertálás: {szazalek}%")
                elif "=" not in sor.split(" ")[0]:
                    farok = (farok + [sor.strip()])[-8:]
            kod = p.wait()
        if kod != 0:
            raise KonvertalasHiba(f"az ffmpeg hibával állt le ({kod}): {' | '.join(farok)[-400:]}")
        _ellenoriz(f, felmeres(ffmpeg, part))
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    # a csere: kizáró átnevezésekkel, soha nem írunk felül (A3-19)
    from core import tartos
    eredeti_ut = felre
    try:
        if vegleges == forras:      # az .mp4 forrásnál az `.eredeti` az előfeltétel, a `.part` utána kerül a helyére
            tartos.rename_excl(forras, felre)
            try:
                tartos.rename_excl(part, vegleges)
            except OSError:
                tartos.rename_excl(felre, forras)       # nincs lejátszható fájl nélküli állapot: az eredeti visszakerül
                raise
        else:                       # előbb a lejátszható új fájl; a forrás csak utána kapja az `.eredeti` nevet
            tartos.rename_excl(part, vegleges)
            try:
                tartos.rename_excl(forras, felre)
            except OSError as e:
                log(f"FIGYELEM: az eredeti nem nevezhető át ({e}); az új fájl a helyén, az eredeti a nevén marad: {forras.name}")
                eredeti_ut = forras
    except OSError as e:
        part.unlink(missing_ok=True)
        raise KonvertalasHiba(f"a csere nem sikerült ({e}); az eredeti érintetlen") from e
    ki = {"mod": t["mod"], "ut": str(vegleges), "eredeti": str(eredeti_ut), "ok": t["ok"], "mp": round(time.monotonic() - t0, 1)}
    if eredeti_gyoker is not None and eredeti_ut == felre:
        try:
            ki["eredeti"] = str(_eredeti_archivalas(felre, Path(eredeti_gyoker), relativ, nev=forras.name))
        except OSError as e:        # az eredeti `.eredeti` néven a forrás mellett marad (nem törlünk, nem veszítünk)
            ki["archivalas_hiba"] = str(e)
            log(f"FIGYELEM: az eredeti archiválása nem sikerült ({e}); a staging-ben marad: {felre.name}")
    return ki
