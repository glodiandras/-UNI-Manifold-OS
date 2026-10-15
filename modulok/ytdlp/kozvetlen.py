"""Közvetlen videófájl a videóoldalon (a 84. döntés javasolt kiegészítése): a beágyazott lejátszó helyett a kiadó saját fájlja.

Sok kurzusoldal a lejátszó mellett a videót letölthető fájlként is linkeli (`<a href="…/lecture1-1080p.mp4">`), több minőségben, HDR- és
szinkronváltozatban, mellette a felirattal (`…/lang/en/lecture1.srt`) és a diákkal (`…/lecture1.pdf`). A YouTube-lejátszó mögötti
letöltést a YouTube bot-ellenőrzése megállíthatja; a kiadó fájlja süti nélkül, őszinte User-Agenttel letölthető. Ez a modul:

* `valaszt(html, oldal_url, beall)` — az oldal `<a href>`-jeiből a beállított elsőbbség szerint (`[video.kozvetlen] minoseg`, alap
  1080p, aztán 720p) a nem kizárt (`kizar`, alap: HDR), **az oldal eredeti nyelvén** álló (a `<html lang>`; a más nyelvű útszakasz —
  `/es/`, `/pt/` — szinkron) változatot választja; mellé a **saját** feliratát (ugyanaz az alapnév, az eredeti nyelv) és a diákat
  (ugyanaz az alapnév, `.pdf`; csak metaadat, nem töltődik le). Ha nincs megfelelő fájl: `None`, és a beágyazott lejátszó marad.
* `srt_vtt(szoveg)` — SubRip → WebVTT (a vault `<törzs>.<nyelv>.vtt` formátuma; L44: kiadói felirat, `NOTE manifold-asr` nélkül).
* `felirat_be(mappa, url, nyelv, mcfg)` — a felirat letöltése a staging forrásmappába (`video.<nyelv>.vtt`, a yt-dlp feliratának helye és
  neve) és belőle a `transcript.md` a msp felirat-motorjával (modell nélkül), így az átirat nem függ a beszédfelismerő modelltől.

Nincs benne oldalspecifikus tudás: a minták és az elsőbbség a `config/os.toml` `[video.kozvetlen]` szakaszában élnek.
"""
from __future__ import annotations

import html as _html
import re
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Callable
from urllib.parse import unquote, urljoin, urlsplit

ALAP = {
    "be": True,
    "kiterjesztes": [".mp4", ".mov", ".m4v"],
    "minoseg": ["1080p", "720p"],
    "kizar": ["hdr"],
    "valtozat_minta": r"[-_.](?:\d{3,4}p|[248]k|hdr|sdr)(?=[-_.]|$)",
    "felirat": [".srt", ".vtt"],
    "nyelv_szegmens": r"^[a-z]{2}(?:[-_][a-z]{2})?$",
    "alap_nyelv": "en",
}
FELIRAT_MAX = 5 * 1024 * 1024
# ISO 639-1: csak ilyen kódú útszakasz nyelv (a `/ai/` — a CS50 AI-hete — vagy egy `/hd/` mappa nem szinkron)
ISO_639_1 = frozenset("""
aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce ch co cr cs cu cv cy da de dv dz ee el en eo es et eu fa ff fi
fj fo fr fy ga gd gl gn gu gv ha he hi ho hr ht hu hy hz ia id ie ig ii ik io is it iu ja jv ka kg ki kj kk kl km kn ko kr ks ku kv kw
ky la lb lg li ln lo lt lu lv mg mh mi mk ml mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om or os pa pi pl ps pt qu rm rn ro
ru rw sa sc sd se sg si sk sl sm sn so sq sr ss st su sv sw ta te tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi vo wa wo xh yi
yo za zh zu""".split())


def beallitas(cfg) -> dict:
    """A `[video.kozvetlen]` szakasz az alapértékekkel kiegészítve (hiányzó kulcs: az alap)."""
    try:
        s = dict(cfg.section("video").get("kozvetlen") or {})
    except Exception:  # noqa: BLE001 — a beállítás hiánya nem hiba: az alap él
        s = {}
    b = {k: s.get(k, v) for k, v in ALAP.items()}
    b["kiterjesztes"] = [str(x).lower() for x in b["kiterjesztes"]]
    b["felirat"] = [str(x).lower() for x in b["felirat"]]
    b["minoseg"] = [str(x).lower() for x in b["minoseg"]]
    b["kizar"] = [str(x).lower() for x in b["kizar"]]
    return b


class _Linkek(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefek: list[str] = []
        self.nyelv: str | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html" and a.get("lang") and self.nyelv is None:
            self.nyelv = str(a["lang"]).strip()
        elif tag == "a" and a.get("href"):
            self.hrefek.append(a["href"].strip())


def _nyelv_kod(s: str | None) -> str | None:
    s = (s or "").strip().lower().replace("_", "-")
    return s.split("-")[0] or None


def _szegmensek(url: str) -> list[str]:
    return [unquote(x) for x in urlsplit(url).path.split("/") if x]


def _ut_nyelve(url: str, minta: re.Pattern) -> str | None:
    """Az út nyelvi szakasza (a fájlnév előtti mappák közül az utolsó, amely nyelvkódnak látszik), vagy `None`."""
    for seg in reversed(_szegmensek(url)[:-1]):
        if minta.match(seg.lower()) and _nyelv_kod(seg) in ISO_639_1:
            return _nyelv_kod(seg)
    return None


def _jelolok(torzs: str) -> set[str]:
    return {x for x in re.split(r"[-_. ]+", torzs.lower()) if x}


def _alapnev(torzs: str, valtozat: re.Pattern) -> str:
    return valtozat.sub("", torzs).lower()


def valaszt(html: str, oldal_url: str, beall: dict) -> dict | None:
    """Az oldal közvetlen videófájlja a beállított elsőbbség szerint, a saját feliratával és diáival.

    → `{video, minoseg, nyelv, alapnev, felirat, diak}` vagy `None` (nincs megfelelő fájl: a beágyazott lejátszó marad)."""
    if not beall.get("be", True):
        return None
    p = _Linkek()
    p.feed(html)
    p.close()
    nyelvminta = re.compile(str(beall["nyelv_szegmens"]))
    valtozat = re.compile(str(beall["valtozat_minta"]), re.I)
    oldal_nyelv = _nyelv_kod(p.nyelv) or _nyelv_kod(str(beall.get("alap_nyelv") or "")) or None
    linkek: list[str] = []
    for h in p.hrefek:
        u = urljoin(oldal_url, _html.unescape(h)).split("#", 1)[0]
        if u.startswith(("http://", "https://")) and u not in linkek:
            linkek.append(u)

    def kiterj(u: str) -> str:
        return PurePosixPath(urlsplit(u).path).suffix.lower()

    def torzs(u: str) -> str:
        return PurePosixPath(unquote(urlsplit(u).path)).stem

    # 1. a videófájlok: az eredeti nyelvűek (nyelvi útszakasz nélkül, vagy az oldal nyelvén), alapnév szerint csoportosítva
    csoportok: dict[str, list[tuple[str, set[str]]]] = {}
    for u in linkek:
        if kiterj(u) not in beall["kiterjesztes"]:
            continue
        unyelv = _ut_nyelve(u, nyelvminta)
        if unyelv and oldal_nyelv and unyelv != oldal_nyelv:
            continue                                   # szinkron (pl. `/es/`, `/pt/`)
        csoportok.setdefault(_alapnev(torzs(u), valtozat), []).append((u, _jelolok(torzs(u))))
    valasztott = None
    for alap, valtozatok in csoportok.items():             # oldalsorrendben az első csoport, amelyben van elfogadható változat
        for q in beall["minoseg"]:
            jo = [u for u, j in valtozatok if q in j and not (j & set(beall["kizar"]))]
            if jo:
                valasztott = (jo[0], q, alap)
                break
        if valasztott:
            break
    if not valasztott:
        return None
    video, minoseg, alap = valasztott

    # 2. a felirat: ugyanaz az alapnév (a `.en` nyelvi utótag nélkül), az oldal nyelvén (vagy nyelvjelölés nélkül)
    feliratok: list[tuple[int, int, str, str | None]] = []
    for u in linkek:
        k = kiterj(u)
        if k not in beall["felirat"]:
            continue
        t = torzs(u)
        fnyelv = _ut_nyelve(u, nyelvminta)
        m = re.match(r"^(.*)\.([a-z]{2}(?:[-_][a-z]{2})?)$", t, re.I)
        if m and _nyelv_kod(m.group(2)) in ISO_639_1:
            t, fnyelv = m.group(1), fnyelv or _nyelv_kod(m.group(2))
        if _alapnev(t, valtozat) != alap:
            continue
        if fnyelv and oldal_nyelv and fnyelv != oldal_nyelv:
            continue
        feliratok.append((0 if fnyelv else 1, beall["felirat"].index(k), u, fnyelv or oldal_nyelv))
    feliratok.sort(key=lambda x: (x[0], x[1]))
    felirat = feliratok[0][2] if feliratok else None

    # 3. a diák: ugyanaz az alapnév, `.pdf` (csak metaadat; nem töltődik le)
    diak = next((u for u in linkek if kiterj(u) == ".pdf" and _alapnev(torzs(u), valtozat) == alap
                 and _ut_nyelve(u, nyelvminta) in (None, oldal_nyelv)), None)
    return {"video": video, "minoseg": minoseg, "nyelv": oldal_nyelv, "alapnev": alap, "felirat": felirat, "diak": diak}


# ------------------------------------------------------------------ felirat → VTT → transcript.md

_SRT_IDO = re.compile(r"(\d{1,3}:\d{2}:\d{2}),(\d{1,3})")


def srt_vtt(szoveg: str, *, forras: str | None = None) -> str:
    """SubRip (`.srt`) → WebVTT. A szöveg változatlan; az időbélyeg tizedesvesszője pont; a sorszám marad (a WebVTT cue-azonosítója).
    Ha a bemenet már WebVTT, a fejléc után csak a forrás-megjegyzés kerül be. A `NOTE manifold-asr` jel NEM kerül bele (kiadói, L44)."""
    s = szoveg.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    megj = f"NOTE kiadói felirat{': ' + forras if forras else ''}\n\n"
    if s.startswith("WEBVTT"):
        fej, _, torzs = s.partition("\n\n")
        return f"{fej}\n\n{megj}{torzs.lstrip(chr(10))}".rstrip("\n") + "\n"
    blokkok = [b.strip("\n") for b in re.split(r"\n[ \t]*\n", s) if b.strip()]
    ki = ["WEBVTT", "", megj.rstrip("\n"), ""]
    for b in blokkok:
        sorok = b.split("\n")
        ki += [_SRT_IDO.sub(lambda m: f"{m.group(1)}.{m.group(2).ljust(3, '0')}", x) if "-->" in x else x for x in sorok]
        ki.append("")
    return "\n".join(ki).rstrip("\n") + "\n"


def felirat_nev(nyelv: str | None, stem: str = "video") -> str:
    return f"{stem}.{nyelv}.vtt" if nyelv else f"{stem}.vtt"


def felirat_be(mappa: Path, url: str, nyelv: str | None, mcfg, *, fetch: Callable | None = None, log=print) -> str:
    """A kiadói felirat a staging forrásmappába (`video.<nyelv>.vtt`), és belőle a `transcript.md` (a msp `subtitles` motorja, modell
    nélkül). → `"irva"` | `"megvan"` (kész átirat vagy felirat már áll) | `"hiba"` (a videó letöltése ettől nem hibás).

    A letöltés a bejáró őszinte, süti nélküli kérője (`msp.crawl.HttpFetcher`); a meglévő kész átiratot nem írja felül."""
    from msp import notes, schema
    from msp.crawl import create_fetcher
    from msp.transcription.subtitles import SubtitlesBackend
    from msp.transcription.writer import write_transcript

    mappa = Path(mappa)
    atirat = mappa / schema.TRANSCRIPT_NOTE_NAME
    try:
        front, _ = notes.read_note(atirat) if atirat.is_file() else ({}, "")
    except Exception:  # noqa: BLE001
        front = {}
    if str(front.get("transcript_status") or "pending") != "pending":
        return "megvan"
    cel = mappa / felirat_nev(nyelv)
    if not cel.is_file():
        try:
            oldal = (fetch or create_fetcher(mcfg))(url)
        except Exception as e:  # noqa: BLE001 — hálózati hiba: a videó megvan, a felirat később pótolható
            log(f"FIGYELEM: a felirat nem tölthető le ({url}): {getattr(e, 'message', e)}")
            return "hiba"
        if not (200 <= oldal.status < 300) or not oldal.text.strip() or len(oldal.text) > FELIRAT_MAX:
            log(f"FIGYELEM: a felirat nem tölthető le ({url}): HTTP {oldal.status}")
            return "hiba"
        vtt = srt_vtt(oldal.text, forras=url)
        from core import tartos
        tartos.atomi_ir(cel, vtt.encode("utf-8"))
        log(f"felirat: {cel.name} ({url})")
    try:
        r = SubtitlesBackend(mcfg).transcribe(mappa / cel.name, language=nyelv, folder=mappa)
        write_transcript(mappa, r, config=mcfg)
    except Exception as e:  # noqa: BLE001 — a msp típusos hibája; az átirat `pending` marad
        log(f"FIGYELEM: az átirat a feliratból nem készült el: {getattr(e, 'message', e)}")
        return "hiba"
    log(f"átirat a kiadói feliratból: {len(r.segments)} szakasz ({r.engine})")
    return "irva"
