"""Egy weboldal összes videója (84. döntés, javasolt): bejárás → lista → jóváhagyás → letöltés a meglévő staging-úton.

Két külön fázis, mert a felhasználó a listát látja, mielőtt bármi letöltődne (D3: a hálózatot a jóváhagyott letöltés használja):

1. **felfedezés** (`felfedez`): az `msp.crawl` udvarias bejárója (ugyanaz a gazdagép, a kezdő út alatt, robots.txt, `Crawl-delay`,
   őszinte User-Agent, süti és hitelesítés nélkül, `crawl.max_depth`) a kezdőoldalból elérhető videóoldalakat gyűjti; oldalanként a címet
   (`<title>`) és a beágyazott lejátszó **videójának** linkjét (`beagyazott_videok`: a YouTube-iframe, a `youtu.be`, a CS50 saját
   lejátszója — `video.cs50.io/<YouTube-azonosító>` — a YouTube-videóra, a Vimeo-lejátszó a Vimeo-videóra fordul; ha nincs ilyen, az
   oldal maga megy a yt-dlp általános kinyerőjének). Semmit nem tölt le; az eredmény a `{state}/video-bejaras/<kulcs>.json`-ba kerül
   (`core.videolanc.bejaras_fajl`: a core és a CLI egy helyről számolja).
2. **letöltés** (`letoltendo` + `lanc.letoltes`): a kiválasztott, még meg nem lévő videók a szokásos `ingest_url` úton, tehát a
   duplikátum-védelem, a konvertálás, a felirat és a pillanatkép pontosan az egyedi linkéi. A már stagingben lévő videó kimarad (a
   megszakított letöltés újrafuttatva folytatódik).

**Közvetlen fájl** (a 84. döntés javasolt kiegészítése): ha a videóoldal a kiadó saját videófájlját is linkeli (`<a href="….mp4">`), a
tétel azt választja (`kozvetlen.valaszt`: a `[video.kozvetlen]` elsőbbsége, az oldal eredeti nyelve), a feliratával és a diák linkjével
(csak metaadat); a tétel `forras` mezője mondja meg, melyik út töltődik (`kozvetlen` | `beagyazott`). A letöltés ugyanez az út, a
bejáró őszinte User-Agentjével, utána a felirat a stagingbe (`kozvetlen.felirat_be`).

A bejáró **általános**: a felfedezés (`msp.crawl.walk`) és az „oldallal mit kezdünk” döntés (`msp.crawl.Decision`, itt a videóoldal-
osztályozó) külön van; egy későbbi szöveges oldal → Markdown importáló ugyanazt a `walk`-ot más osztályozóval hívhatja.
"""
from __future__ import annotations

import datetime as _dt
import html as _html
import json
import logging
import os
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin

from . import kozvetlen, lanc

#: beágyazott lejátszó (iframe `src`) → a videó saját linkje. A YouTube-azonosító 11 karakter; a `videoseries` lejátszási lista, nem videó.
BEAGYAZAS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"(?:youtube(?:-nocookie)?\.com/(?:embed|v)/|youtu\.be/|video\.cs50\.io/)(?!videoseries)([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])",
                re.I), "https://www.youtube.com/watch?v={}"),
    (re.compile(r"player\.vimeo\.com/video/(\d+)", re.I), "https://vimeo.com/{}"),
)
CIM_MAX = 200
KOZVETLEN, BEAGYAZOTT = "kozvetlen", "beagyazott"
FORRAS_NEV = {KOZVETLEN: "közvetlen fájl", BEAGYAZOTT: "beágyazott lejátszó"}


class _Lejatszok(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forrasok: list[str] = []
        self.cim: list[str] = []
        self.h1: list[str] = []
        self._hol: str | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "iframe" and a.get("src"):
            self.forrasok.append(("iframe", a["src"].strip()))
        elif tag in ("video", "source") and a.get("src"):
            self.forrasok.append(("media", a["src"].strip()))
        elif tag in ("title", "h1") and self._hol is None:
            self._hol = tag

    def handle_endtag(self, tag):
        if tag == self._hol:
            self._hol = None

    def handle_data(self, data):
        if self._hol == "title":
            self.cim.append(data)
        elif self._hol == "h1":
            self.h1.append(data)


def _video_link(szoveg: str) -> str | None:
    for minta, sablon in BEAGYAZAS:
        m = minta.search(szoveg)
        if m:
            return sablon.format(m.group(1))
    return None


def beagyazott_videok(html: str, oldal_url: str) -> list[str]:
    """Az oldal beágyazott lejátszóinak videó-linkjei oldalsorrendben, ismétlés nélkül: előbb az iframe-ek (a táblázat szerint fordítva),
    utána a `<video>`/`<source>` közvetlen fájljai. Ha egyik sem fordítható, a HTML első felismert lejátszó-linkje; üres lista, ha az sincs."""
    p = _Lejatszok()
    p.feed(html)
    p.close()
    ki: list[str] = []
    for fajta, src in p.forrasok:
        cel = _video_link(src) if fajta == "iframe" else urljoin(oldal_url, src)
        if cel and cel.startswith(("http://", "https://")) and cel not in ki:
            ki.append(cel)
    if not ki:
        cel = _video_link(html)
        if cel:
            ki.append(cel)
    return ki


def oldal_cime(html: str) -> str:
    p = _Lejatszok()
    p.feed(html)
    p.close()
    cim = " ".join("".join(p.cim).split()) or " ".join("".join(p.h1).split())
    return _html.unescape(cim)[:CIM_MAX]


# ------------------------------------------------------------------ már megvan?

def _youtube_id(url: str) -> str | None:
    m = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m and "youtube.com/" in url else None


def megvan_fuggveny(mcfg) -> Callable[[str], bool]:
    """→ `f(video_url)`: a videó már a stagingben van-e (az archívum ismeri, és a forrásmappa teljes) — a letöltés is ezt nézi."""
    _, _, _, archivum = lanc.msp()
    arch = archivum.Archive(mcfg.archive_dir, enabled=mcfg.archive.enabled)

    def f(url: str) -> bool:
        try:
            jeloltek = [arch.find_by_url(url)]
            yid = _youtube_id(url)
            if yid:
                jeloltek += [e for e in arch if e.video_id == yid and "youtube" in (e.provider or e.extractor or "youtube").lower()]
            return any(e is not None and archivum.source_folder_is_complete(mcfg.output_root / e.path) for e in jeloltek)
        except Exception:  # noqa: BLE001 — a jelölés csak tájékoztató; a letöltés maga is kihagyja a meglévőt
            return False
    return f


# ------------------------------------------------------------------ felfedezés

class _NaploKezelo(logging.Handler):
    def __init__(self, log):
        super().__init__(logging.INFO)
        self._log = log

    def emit(self, record):
        try:
            self._log(f"[bejárás] {record.getMessage()}")
        except Exception:  # noqa: BLE001
            pass


def felfedez(cfg, start: str, *, fetch=None, sleep=time.sleep, log=print, stop_fajl: str | None = None, mcfg=None) -> dict:
    """A kezdőoldal alatti videóoldalak listája (csak olvas a hálózatról; letöltés nincs). → a mentendő eredmény."""
    konfig, _, _, _ = lanc.msp()
    import msp.crawl as bejaro
    mcfg = mcfg or lanc.msp_konfig(cfg)
    naplo = logging.getLogger(f"manifold.bejaras.{id(log)}")
    naplo.propagate = False
    naplo.setLevel(logging.INFO)
    kezelo = _NaploKezelo(log)
    naplo.addHandler(kezelo)
    tetelek: list[dict] = []
    latott: set[str] = set()
    kb = kozvetlen.beallitas(cfg)

    def oldal(url: str, page) -> None:
        videok = beagyazott_videok(page.text, page.url)
        beagyazott = videok[0] if videok else None
        kv = kozvetlen.valaszt(page.text, page.url, kb)
        fo = kv["video"] if kv else (beagyazott or url)
        if fo in latott or (beagyazott and beagyazott in latott):
            return
        latott.update(x for x in (fo, beagyazott) if x)
        t = {"oldal": url, "cim": oldal_cime(page.text) or url, "video": fo, "forras": KOZVETLEN if kv else BEAGYAZOTT,
             "beagyazott": beagyazott, "tovabbi": videok[1:]}
        if kv:
            t.update({"minoseg": kv["minoseg"], "nyelv": kv["nyelv"], "felirat": kv["felirat"], "diak": kv["diak"]})
        tetelek.append(t)
        log(f"[bejárás] videó #{len(tetelek)}: {t['cim']} → {fo} ({forras_leiras(t)})")

    megallitva = []

    def all_meg() -> bool:
        if stop_fajl and os.path.exists(stop_fajl):
            megallitva.append(True)
            return True
        return False

    try:
        r = bejaro.crawl(start, config=mcfg, fetch=fetch, sleep=sleep, logger=naplo, on_video_page=oldal,
                         max_items=mcfg.crawl.max_items, should_stop=all_meg)
    finally:
        naplo.removeHandler(kezelo)
    megvan = megvan_fuggveny(mcfg)
    for t in tetelek:
        t["megvan"] = tetel_megvan(t, megvan)
    return {"verzio": 1, "start": start.strip(), "kezdo": r.start_url, "ido": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "kesleltetes_s": r.delay_seconds, "oldalak": r.pages_fetched, "robots_tiltott": r.blocked_by_robots,
            "olvashatatlan": r.unreadable_pages, "megszakitva": bool(megallitva), "max_db": bejaras_max(cfg), "tetelek": tetelek}


def bejaras_max(cfg) -> int:
    """Ennél több videó letöltése kifejezett megerősítést kér (`[video] bejaras_max`, alap 50)."""
    return int(cfg.section("video").get("bejaras_max", 50))


def ment(cfg, eredmeny: dict) -> Path:
    from core import tartos
    from core.videolanc import bejaras_fajl
    p = bejaras_fajl(cfg, eredmeny["start"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tartos.atomi_ir(p, json.dumps(eredmeny, ensure_ascii=False, indent=1).encode("utf-8"))
    return p


def betolt(cfg, start: str, max_kor_s: float | None = None) -> dict | None:
    from core.videolanc import bejaras_fajl
    p = bejaras_fajl(cfg, start)
    try:
        if max_kor_s is not None and time.time() - p.stat().st_mtime > max_kor_s:
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def tetel_megvan(t: dict, megvan: Callable[[str], bool]) -> bool:
    """A tétel már a stagingben van-e: a választott videó, a beágyazott lejátszó videója (ugyanaz az előadás, ha korábban a lejátszón át
    töltődött le) vagy az oldal (a közvetlen fájl forrás-linkje az oldal) szerint."""
    return any(megvan(u) for u in (t.get("video"), t.get("beagyazott"), t.get("oldal")) if u)


def kozvetlen_tetelek(cfg) -> dict[str, dict]:
    """`{közvetlen videó-link: tétel}` a mentett bejárásokból (`{state}/video-bejaras/*.json`, a legfrissebb nyer): a letöltés lépése innen
    tudja, hogy a link egy oldal közvetlen fájlja (az oldal címe, linkje, felirata), akár a felületről, akár a parancssorból indult."""
    from core.videolanc import bejaras_fajl
    d = bejaras_fajl(cfg, "x").parent
    ki: dict[str, dict] = {}
    try:
        fajlok = sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime)
    except OSError:
        return ki
    for p in fajlok:
        try:
            adat = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for t in adat.get("tetelek") or []:
            if isinstance(t, dict) and t.get("forras") == KOZVETLEN and isinstance(t.get("video"), str):
                ki[t["video"]] = t
    return ki


def letoltendo(eredmeny: dict, megvan: Callable[[str], bool] | None = None, *, csak: list[str] | None = None) -> tuple[list[str], int]:
    """A letöltendő videó-linkek a felfedezés sorrendjében (a `csak` szűkít: videó- vagy oldal-link), és a már meglévők száma."""
    ki, meglevo = [], 0
    for t in eredmeny.get("tetelek") or []:
        if csak is not None and t.get("video") not in csak and t.get("oldal") not in csak:
            continue
        if (tetel_megvan(t, megvan) if megvan else t.get("megvan")):
            meglevo += 1
            continue
        if t["video"] not in ki:
            ki.append(t["video"])
    return ki, meglevo


def kiir(eredmeny: dict, log=print) -> None:
    tt = eredmeny.get("tetelek") or []
    log(f"Bejárás: {eredmeny.get('kezdo') or eredmeny.get('start')} — {len(tt)} videó, {eredmeny.get('oldalak', 0)} oldal olvasva"
        + (f", {eredmeny['robots_tiltott']} robots.txt-tiltott" if eredmeny.get("robots_tiltott") else "")
        + (f", {eredmeny['olvashatatlan']} olvashatatlan" if eredmeny.get("olvashatatlan") else "")
        + (" (MEGSZAKÍTVA)" if eredmeny.get("megszakitva") else ""))
    for i, t in enumerate(tt, 1):
        sorok = [f"{i:>3}. {'[megvan] ' if t.get('megvan') else ''}{t['cim']}", f"       oldal: {t['oldal']}",
                 f"       videó: {t['video']}", f"       forrás: {forras_leiras(t)}"]
        if t.get("diak"):
            sorok.append(f"       diák: {t['diak']} (csak metaadat, nem töltődik le)")
        log("\n".join(sorok))


def forras_leiras(t: dict) -> str:
    """„közvetlen fájl (1080p, en; felirat)” | „beágyazott lejátszó” — a lista (CLI) egy helyen számolt szövege."""
    if t.get("forras") != KOZVETLEN:
        return FORRAS_NEV[BEAGYAZOTT]
    reszek = [x for x in (t.get("minoseg"), t.get("nyelv")) if x]
    return (f"{FORRAS_NEV[KOZVETLEN]} ({', '.join(reszek)}" + ("; felirat" if t.get("felirat") else "; felirat nélkül") + ")")
