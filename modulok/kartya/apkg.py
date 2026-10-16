"""Anki-csomag (`.apkg`) export és import (`docs/C23-TERV.md` 4. fejezet) — csak a stdlib: `sqlite3`, `zipfile`,
`compression.zstd` (Python 3.14), és egy kis kézi protobuf-dekóder.

Referencia: az upstream Anki-repó `rslib/src/import_export/package/` és
`rslib/src/storage/schema11.sql` kódja.

**Export**: a „Support older Anki versions” alak (LEGACY_2) — a legszélesebben olvasható (Anki desktop, AnkiMobile,
AnkiDroid): `meta` (`\\x08\\x02`), `collection.anki21` (séma 11), egy üres séma-11 `collection.anki2`, JSON `media` és
a számozott médiafájlok. A jegyzet `guid`-ja `"mos" + azonosító`, így az újraexport az Ankiban frissít; az FSRS-állapot
a `cards.data` `s`/`d`/`dr`/`lrt` kulcsaiban.

**Import**: a `meta` szerint LATEST (`collection.anki21b`, zstd) vagy LEGACY_2/1. A saját kártya (`mos…` guid) az
eredeti azonosítóját kapja, a frissebb állapot nyer; az idegen kártya új azonosítót, `apkg_kulcs`-szal (az újraimport
nem duplikál). A cloze-jegyzet kimarad (megszámolva). A vaultba ez a modul nem ír (C23b): a médiát (`media_kicsomagol`, K308) csak
az importáló saját `{tmp}` mappájába bontja ki, a vaultba a core gépi írása (`behoz`) viszi.
"""
from __future__ import annotations

import hashlib
import html as _html
import json
import math
import os
import re
import sqlite3
import tempfile
import unicodedata
import zipfile
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, unquote

from core import tanulas_db

from . import formatum, html
from .szinkron import ido, iso, most_utc
from .utemezo import MEZOK, UJ, allapot_sorbol

# Az import korlátai (Javító 5): a csomag külső forrásból jön. Az Anki-gyűjtemény valós mérete (a médián kívül) nagyságrendekkel
# a korlát alatt marad; a korlát fölött a csomag hibával áll meg, nem memóriát eszik.
GY_MAX = 512 << 20            # a kicsomagolt gyűjtemény (SQLite) bájtjai: a zip-bejegyzés deklarált és a zstd-kimenet mérete
MEDIA_JEGYZEK_MAX = 64 << 20  # a `media` jegyzék kicsomagolt mérete
META_MAX = 64 << 10           # a `meta` mérete
ZIP_BEJEGYZES_MAX = 1_000_000  # a zip bejegyzéseinek száma (a média sok kis fájl)
ARANY_MAX = 1100              # deflate-tel > 1032:1 nem lehetséges: efölött a deklarált méret hazudik / bomba
KARTYA_MAX = 500_000
NAPLO_MAX = 2_000_000         # revlog sorok (a tracker és az FSRS-napló: az ennél nagyobb gyűjtemény szűrést igényel)
MEZO_MAX = 64 << 10           # egy jegyzet mezői együtt (bájt); a nagyobb (pl. beágyazott base64 kép) kimarad
ADAT_MAX = 4096               # a `cards.data` (FSRS-JSON) mérete
GUID_MAX = 128
MEDIA_NEV_MAX = 255
META_LEGACY2 = b"\x08\x02"
LEGACY1, LEGACY2, LATEST = 1, 2, 3
GUID_ELOTAG = "mos"
MODELL_NEV = "Manifold Basic"
PAKLI_ALAP = "Manifold"

SEMA11 = """
CREATE TABLE col (id integer PRIMARY KEY, crt integer NOT NULL, mod integer NOT NULL, scm integer NOT NULL,
  ver integer NOT NULL, dty integer NOT NULL, usn integer NOT NULL, ls integer NOT NULL, conf text NOT NULL,
  models text NOT NULL, decks text NOT NULL, dconf text NOT NULL, tags text NOT NULL);
CREATE TABLE notes (id integer PRIMARY KEY, guid text NOT NULL, mid integer NOT NULL, mod integer NOT NULL,
  usn integer NOT NULL, tags text NOT NULL, flds text NOT NULL, sfld integer NOT NULL, csum integer NOT NULL,
  flags integer NOT NULL, data text NOT NULL);
CREATE TABLE cards (id integer PRIMARY KEY, nid integer NOT NULL, did integer NOT NULL, ord integer NOT NULL,
  mod integer NOT NULL, usn integer NOT NULL, type integer NOT NULL, queue integer NOT NULL, due integer NOT NULL,
  ivl integer NOT NULL, factor integer NOT NULL, reps integer NOT NULL, lapses integer NOT NULL, left integer NOT NULL,
  odue integer NOT NULL, odid integer NOT NULL, flags integer NOT NULL, data text NOT NULL);
CREATE TABLE revlog (id integer PRIMARY KEY, cid integer NOT NULL, usn integer NOT NULL, ease integer NOT NULL,
  ivl integer NOT NULL, lastIvl integer NOT NULL, factor integer NOT NULL, time integer NOT NULL, type integer NOT NULL);
CREATE TABLE graves (usn integer NOT NULL, oid integer NOT NULL, type integer NOT NULL);
CREATE INDEX ix_notes_usn ON notes (usn);
CREATE INDEX ix_cards_usn ON cards (usn);
CREATE INDEX ix_revlog_usn ON revlog (usn);
CREATE INDEX ix_cards_nid ON cards (nid);
CREATE INDEX ix_cards_sched ON cards (did, queue, due);
CREATE INDEX ix_revlog_cid ON revlog (cid);
CREATE INDEX ix_notes_csum ON notes (csum);
"""


class ApkgHiba(ValueError):
    pass


# ------------------------------------------------------------------ közös

def _nap(d: datetime) -> datetime:
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def _napon_beluli(d: datetime | None) -> timedelta:
    return timedelta() if d is None else d - _nap(d)


def csum(mezo_html: str) -> int:
    return int(hashlib.sha1(html.csupasz(mezo_html).encode("utf-8")).hexdigest()[:8], 16)


def guid_azon(guid: str) -> str | None:
    """A saját exportunk jegyzetének guid-jából a kártya azonosítója, különben None."""
    if guid.startswith(GUID_ELOTAG) and formatum.AZON_RE.fullmatch(guid[len(GUID_ELOTAG):]):
        return guid[len(GUID_ELOTAG):]
    return None


# ------------------------------------------------------------------ export

def _modell(mid: int, did: int, mod: int) -> dict:
    mezo = lambda nev, ord_: {"name": nev, "ord": ord_, "sticky": False, "rtl": False, "font": "Arial",  # noqa: E731
                              "size": 20, "media": []}
    return {
        "id": mid, "name": MODELL_NEV, "type": 0, "mod": mod, "usn": 0, "sortf": 0, "did": did,
        "tmpls": [{"name": "Kártya", "ord": 0, "qfmt": "{{Front}}",
                   "afmt": "{{FrontSide}}<hr id=answer>{{Back}}{{#Forrás}}<div class=forras>{{Forrás}}</div>{{/Forrás}}",
                   "bqfmt": "", "bafmt": "", "did": None, "bfont": "", "bsize": 0}],
        "flds": [mezo("Front", 0), mezo("Back", 1), mezo("Forrás", 2)],
        "css": ".card { font-family: -apple-system, sans-serif; font-size: 20px; text-align: left; }\n"
               ".forras { margin-top: 1em; font-size: 14px; opacity: .6; }",
        "latexPre": "\\documentclass[12pt]{article}\n\\special{papersize=3in,5in}\n\\usepackage[utf8]{inputenc}\n"
                    "\\usepackage{amssymb,amsmath}\n\\pagestyle{empty}\n\\setlength{\\parindent}{0in}\n\\begin{document}\n",
        "latexPost": "\\end{document}", "latexsvg": False, "req": [[0, "any", [0]]], "tags": [], "vers": []}


def _pakli(did: int, nev: str, mod: int) -> dict:
    return {"id": did, "name": nev, "mod": mod, "usn": 0, "lrnToday": [0, 0], "revToday": [0, 0], "newToday": [0, 0],
            "timeToday": [0, 0], "collapsed": False, "browserCollapsed": False, "desc": "", "dyn": 0, "conf": 1,
            "extendNew": 0, "extendRev": 0}


def _dconf(mod: int, megtartas: float) -> dict:
    return {"id": 1, "mod": mod, "name": "Default", "usn": 0, "maxTaken": 60, "autoplay": True, "timer": 0,
            "replayq": True, "dyn": False, "desiredRetention": megtartas,
            "new": {"bury": False, "delays": [1.0, 10.0], "initialFactor": 2500, "ints": [1, 4, 0], "order": 1,
                    "perDay": 20},
            "rev": {"bury": False, "ease4": 1.3, "ivlFct": 1.0, "maxIvl": 36500, "perDay": 200, "hardFactor": 1.2},
            "lapse": {"delays": [10.0], "leechAction": 1, "leechFails": 8, "minInt": 1, "mult": 0.0}}


def _gyujtemeny(ut: Path, kartyak: list[dict], most: datetime, megtartas: float, lepesszam: tuple[int, int]) -> None:
    """Egy séma-11 gyűjtemény (`collection.anki21`/`.anki2`) a kártyákból; üres listával az üres, érvényes váz."""
    mod = int(most.timestamp())
    crt = _nap(most)
    alap_ms = int(most.timestamp()) * 1000
    mid, did_alap = alap_ms, 1
    paklik = {PAKLI_ALAP: did_alap + 1} if kartyak else {}
    for k in kartyak:
        paklik.setdefault(k.get("pakli") or PAKLI_ALAP, did_alap + 1 + len(paklik))
    decks = {"1": _pakli(1, "Default", mod)} | {str(d): _pakli(d, n, mod) for n, d in paklik.items()}
    conf = {"schedVer": 2, "sched2021": True, "activeDecks": [1], "curDeck": 1, "newSpread": 0, "collapseTime": 1200,
            "timeLim": 0, "estTimes": True, "dueCounts": True, "curModel": mid, "nextPos": len(kartyak) + 1,
            "sortType": "noteFld", "sortBackwards": False, "addToCur": True, "creationOffset": 0, "rollover": 4}
    c = sqlite3.connect(ut)
    try:
        c.executescript(SEMA11)
        c.execute("INSERT INTO col VALUES (1,?,?,?,11,0,0,0,?,?,?,?,'{}')",
                  (int(crt.timestamp()), mod * 1000, mod * 1000, json.dumps(conf),
                   json.dumps({str(mid): _modell(mid, did_alap + 1, mod)}), json.dumps(decks),
                   json.dumps({"1": _dconf(mod, megtartas)})))
        revlog_id: set[int] = set()
        for i, k in enumerate(kartyak):
            nid, cid = alap_ms + i + 1, alap_ms + i + 1
            mezok = [html.md_html(k["kerdes"]), html.md_html(k["valasz"]), _html.escape(k.get("forras") or "", quote=False)]
            c.execute("INSERT INTO notes VALUES (?,?,?,?,0,' manifold ',?,?,?,0,'')",
                      (nid, GUID_ELOTAG + k["azon"], mid, mod, "\x1f".join(mezok), html.csupasz(mezok[0]), csum(mezok[0])))
            c.execute("INSERT INTO cards VALUES (?,?,?,0,?,0,?,?,?,?,?,?,?,?,0,0,0,?)",
                      (cid, nid, paklik[k.get("pakli") or PAKLI_ALAP], mod, *_kartya_mezok(k, crt, i + 1, megtartas, lepesszam)))
            for v in k.get("naplo", []):
                rid = int(ido(v["mikor"]).timestamp()) * 1000
                while rid in revlog_id:
                    rid += 1
                revlog_id.add(rid)
                c.execute("INSERT INTO revlog VALUES (?,?,0,?,?,?,?,?,?)", (rid, cid, *_revlog_mezok(v)))
        c.commit()
    finally:
        c.close()


def _kartya_mezok(k: dict, crt: datetime, pozicio: int, megtartas: float, lepesszam: tuple[int, int]) -> tuple:
    """→ (type, queue, due, ivl, factor, reps, lapses, left, data) — a `docs/C23-TERV.md` 4.1 táblája szerint."""
    a = k["allapot"]
    naplo = k.get("naplo", [])
    reps = len(naplo)
    lapses = sum(1 for v in naplo if v["jegy"] == 1 and (v.get("elotte") or {}).get("allapot") == 2)
    if a["allapot"] == UJ:
        tipus, sor, due, ivl, factor, left, data = 0, 0, pozicio, 0, 0, 0, {}
    else:
        esed, utolso = ido(a["esedekes"]), ido(a["utolso"])
        data = {"s": a["stabilitas"], "d": a["nehezseg"], "dr": megtartas}
        if utolso is not None:
            data["lrt"] = int(utolso.timestamp())
        factor = 2500
        if a["allapot"] == 2:
            tipus, sor, due, left = 2, 2, (_nap(esed) - crt).days, 0
            ivl = max(1, round((esed - utolso).total_seconds() / 86400)) if utolso else 1
        else:
            n = lepesszam[0] if a["allapot"] == 1 else lepesszam[1]
            tipus, sor, due, ivl = a["allapot"], 1, int(esed.timestamp()), 0
            left = max(0, n - (a["lepes"] or 0))
    if k.get("felfuggesztve"):
        sor = -1
    return tipus, sor, due, ivl, factor, reps, lapses, left, json.dumps(data) if data else ""


def _intervallum(a: dict | None, mikor: datetime) -> int:
    """A revlog `ivl`/`lastIvl` alakja: ismétlésnél nap, különben negatív másodperc."""
    if not a or a.get("allapot") in (None, UJ) or not a.get("esedekes"):
        return 0
    esed = ido(a["esedekes"])
    if a["allapot"] == 2:
        alap = ido(a.get("utolso")) or mikor
        return max(1, round((esed - alap).total_seconds() / 86400))
    return -max(0, int((esed - mikor).total_seconds()))


def _revlog_mezok(v: dict) -> tuple:
    """→ (ease, ivl, lastIvl, factor, time, type)."""
    elotte, utana = v.get("elotte") or {}, v.get("utana") or {}
    mikor = ido(v["mikor"])
    tipus = {UJ: 0, 1: 0, 2: 1, 3: 2}.get(elotte.get("allapot"), 0)
    factor = int(round(utana["nehezseg"] * 100)) if utana.get("nehezseg") is not None else 0
    return v["jegy"], _intervallum(utana, mikor), _intervallum(elotte, ido(elotte.get("utolso")) or mikor), factor, \
        int(v.get("ms") or 0), tipus


def export(cel: Path, kartyak: list[dict], *, most: datetime | None = None, megtartas: float = 0.9,
           lepesszam: tuple[int, int] = (2, 1), media: dict[str, Path] | None = None) -> dict:
    """A kártyák `.apkg`-ba (LEGACY_2), atomi cserével. `kartyak`: {azon, kerdes, valasz, forras, pakli,
    felfuggesztve, allapot: {allapot, lepes, stabilitas, nehezseg, esedekes, utolso}, naplo: [{mikor, jegy, ms,
    elotte, utana}]}; `media`: {fájlnév: forrásút} (a kártyák képei); `lepesszam`: (tanulási, újratanulási lépések
    száma, a `left` mezőhöz). → jelentés."""
    cel = Path(cel)
    t = most_utc(most)
    cel.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cel.parent, prefix=".apkg-") as tmp:
        fo, ures = Path(tmp) / "collection.anki21", Path(tmp) / "collection.anki2"
        _gyujtemeny(fo, kartyak, t, megtartas, lepesszam)
        _gyujtemeny(ures, [], t, megtartas, lepesszam)
        zip_tmp = Path(tmp) / "csomag.apkg"
        media = media or {}
        with zipfile.ZipFile(zip_tmp, "w") as z:
            z.writestr(zipfile.ZipInfo("meta"), META_LEGACY2, compress_type=zipfile.ZIP_STORED)
            z.write(fo, "collection.anki21", compress_type=zipfile.ZIP_DEFLATED)
            z.write(ures, "collection.anki2", compress_type=zipfile.ZIP_DEFLATED)
            terkep = {}
            for i, (nev, forras) in enumerate(sorted(media.items())):
                z.write(forras, str(i), compress_type=zipfile.ZIP_STORED)
                terkep[str(i)] = nev
            z.writestr("media", json.dumps(terkep, ensure_ascii=False), compress_type=zipfile.ZIP_DEFLATED)
        os.replace(zip_tmp, cel)
    return {"cel": str(cel), "kartyak": len(kartyak), "media": len(media),
            "naplo": sum(len(k.get("naplo", [])) for k in kartyak)}


def gyujt(cfg, elemzesek: dict[str, formatum.Elemzes] | None = None) -> list[dict]:
    """Az exportálandó kártyák: a szöveg a vaultból (a kártyamappa, csak olvasva), az állapot és a napló a
    `tanulas.sqlite`-ból (ami ott nincs: új). A törölt nem kerül bele; a pakli a kísérőjegyzet neve."""
    from .szinkron import beallitas, latott_kartyak, olvas_mappa
    elemzesek = olvas_mappa(cfg) if elemzesek is None else elemzesek
    latott, _ = latott_kartyak(elemzesek)
    utotag = beallitas(cfg).get("utotag", formatum.UTOTAG)
    ki = []
    with tanulas_db.olvaso(cfg) as c:
        for azon, (ut, k) in sorted(latott.items(), key=lambda x: (x[1][0], x[1][1].sor)):
            r = None if c is None else c.execute("SELECT * FROM kartya WHERE azon = ?", (azon,)).fetchone()
            if r is not None and r["torolve"] is not None:
                continue
            nev = os.path.splitext(os.path.basename(ut))[0]
            nev = nev[:-len(utotag)] if utotag and nev.endswith(utotag) else nev
            allapot = allapot_sorbol(r) if r is not None else {"allapot": UJ, "lepes": None, "stabilitas": None,
                                                                 "nehezseg": None, "esedekes": None, "utolso": None}
            naplo = [] if c is None else [
                {"mikor": v["mikor"], "jegy": v["jegy"], "ms": v["ms"],
                 "elotte": json.loads(v["elotte"]) if v["elotte"] else None,
                 "utana": json.loads(v["utana"]) if v["utana"] else None}
                for v in c.execute("SELECT * FROM valasz WHERE kartya = ? AND visszavonva IS NULL ORDER BY mikor, id",
                                   (azon,))]
            ki.append({"azon": azon, "kerdes": k.kerdes, "valasz": k.valasz, "forras": k.forras, "jegyzet": ut,
                       "pakli": f"{PAKLI_ALAP}::{nev.replace('::', ':')}", "felfuggesztve": bool(r and r["felfuggesztve"]),
                       "allapot": allapot, "naplo": naplo})
    return ki


# ------------------------------------------------------------------ import

def _varint(b: bytes, i: int) -> tuple[int, int]:
    x = s = 0
    while True:
        if i >= len(b):
            raise ApkgHiba("csonka protobuf")
        if s >= 70:
            raise ApkgHiba("érvénytelen protobuf: túl hosszú egész")
        c = b[i]
        i += 1
        x |= (c & 0x7F) << s
        s += 7
        if not c & 0x80:
            return x, i


def protobuf(b: bytes) -> list[tuple[int, int | bytes]]:
    """Egy protobuf-üzenet mezői: [(mezőszám, érték)] — varint egész, length-delimited bájt (a többi drót-típus
    átugorva)."""
    ki, i = [], 0
    while i < len(b):
        kulcs, i = _varint(b, i)
        szam, tipus = kulcs >> 3, kulcs & 7
        if tipus == 0:
            v, i = _varint(b, i)
        elif tipus == 2:
            n, i = _varint(b, i)
            if n > len(b) - i:
                raise ApkgHiba("csonka protobuf: a mező hossza túlnyúlik az üzeneten")
            v, i = b[i:i + n], i + n
        elif tipus in (1, 5):
            n = 8 if tipus == 1 else 4
            if n > len(b) - i:
                raise ApkgHiba("csonka protobuf")
            v, i = b[i:i + n], i + n
        else:
            raise ApkgHiba(f"ismeretlen protobuf drót-típus: {tipus}")
        ki.append((szam, v))
    return ki


def _zstd(b: bytes, max_bajt: int | None = None) -> bytes:
    """zstd-dekompresszió **kimeneti plafonnal** (zstd-bomba ellen): a `max_bajt` fölött `ApkgHiba`; csonka vagy hibás adat is."""
    from compression import zstd
    max_bajt = GY_MAX if max_bajt is None else max_bajt
    d = zstd.ZstdDecompressor()
    try:
        ki = d.decompress(b, max_bajt + 1)
    except zstd.ZstdError as e:
        raise ApkgHiba(f"hibás zstd-adat: {e}") from None
    if len(ki) > max_bajt:
        raise ApkgHiba(f"a kicsomagolt adat túl nagy (több mint {max_bajt >> 20} MiB)")
    if not d.eof:
        raise ApkgHiba("csonka zstd-adat")
    return ki


def _zip_olvas(z: zipfile.ZipFile, nev: str, max_bajt: int) -> bytes:
    """Egy zip-bejegyzés bájtjai méretkorláttal (a deklarált kicsomagolt méret és a tömörítési arány szerint; a `zipfile`
    a deklarált méretnél többet nem olvas ki, ezért a deklaráció hitelesen korlátoz)."""
    try:
        info = z.getinfo(nev)
    except KeyError:
        raise ApkgHiba(f"a csomagban nincs {nev}") from None
    if info.file_size > max_bajt:
        raise ApkgHiba(f"a(z) {nev} túl nagy ({info.file_size >> 20} MiB; legfeljebb {max_bajt >> 20} MiB)")
    if info.file_size > (1 << 20) and info.file_size > max(info.compress_size, 1) * ARANY_MAX:
        raise ApkgHiba(f"a(z) {nev} tömörítési aránya hihetetlen (zip-bomba)")
    try:
        return z.read(info)
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, zlib.error, EOFError, OSError) as e:
        raise ApkgHiba(f"a(z) {nev} nem olvasható: {e}") from None


def media_nev(nev) -> str | None:
    """A csomag médiafájljának neve, ha biztonságos **sima fájlnév** (egy szegmens: nincs `/`, `\\`, `..`, NUL és
    vezérlőjel, páros helyettesítő kódpont, 255 bájtnál rövidebb); különben `None`. A C23b a vaultba csak ilyen nevet írhat."""
    if not isinstance(nev, str) or nev in ("", ".", ".."):
        return None
    if any(c in nev for c in "/\\") or any(ord(c) < 32 or ord(c) == 127 for c in nev):
        return None
    try:
        if len(nev.encode("utf-8")) > MEDIA_NEV_MAX:
            return None
    except UnicodeEncodeError:                       # egyedül álló helyettesítő kódpont
        return None
    return nev if nev == nev.strip() else None


def csomag_verzio(z: zipfile.ZipFile) -> int:
    """Az Anki `meta.rs` sorrendje: a `meta` verziója; nélküle `collection.anki21` → LEGACY_2, különben LEGACY_1."""
    nevek = set(z.namelist())
    if "meta" in nevek:
        v = dict(protobuf(_zip_olvas(z, "meta", META_MAX))).get(1, 0)
        if v not in (LEGACY1, LEGACY2, LATEST):
            raise ApkgHiba(f"ismeretlen vagy túl új csomagverzió: {v}")
        return v
    return LEGACY2 if "collection.anki21" in nevek else LEGACY1


def _media_terkep(z: zipfile.ZipFile, verzio: int) -> tuple[dict[str, str], int]:
    """({zip-bejegyzés: biztonságos fájlnév}, a kihagyott — nem biztonságos nevű vagy értelmezhetetlen — bejegyzések száma)."""
    bejegyzesek, kihagyott = _media_bejegyzesek(z, verzio)
    return {k: e["nev"] for k, e in bejegyzesek.items()}, kihagyott


def _media_bejegyzesek(z: zipfile.ZipFile, verzio: int) -> tuple[dict[str, dict], int]:
    """({zip-bejegyzés: {nev, sha1 (LATEST: a `MediaEntry` 20 bájtja, különben None), meret (LATEST: a deklarált méret)}},
    a kihagyott bejegyzések száma). A név csak `media_nev`-en átment sima fájlnév; a zip-bejegyzés nevét soha nem használjuk útként."""
    if "media" not in z.namelist():
        return {}, 0
    b = _zip_olvas(z, "media", MEDIA_JEGYZEK_MAX)
    ki, kihagyott = {}, 0
    if verzio == LATEST:
        for i, (_, bejegyzes) in enumerate(x for x in protobuf(_zstd(b, MEDIA_JEGYZEK_MAX)) if x[0] == 1):
            mezok = dict(protobuf(bejegyzes)) if isinstance(bejegyzes, bytes) else {}
            nev = mezok.get(1, b"")
            try:
                nev = nev.decode("utf-8") if isinstance(nev, bytes) else str(nev)
            except UnicodeDecodeError:
                kihagyott += 1
                continue
            if media_nev(nev) is None:
                kihagyott += 1
                continue
            sha1 = mezok.get(3)
            meret = mezok.get(2)
            kulcs = mezok.get(255)                       # `legacy_zip_filename`: ha van, a zip-bejegyzés ezen a számon áll
            ki[str(kulcs if isinstance(kulcs, int) else i)] = {
                "nev": nev, "sha1": sha1 if isinstance(sha1, bytes) else None, "meret": meret if isinstance(meret, int) else None}
        return ki, kihagyott
    try:
        m = json.loads(b.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as e:
        raise ApkgHiba(f"a média-jegyzék nem érvényes JSON: {e}") from None
    if not isinstance(m, dict):
        raise ApkgHiba("a média-jegyzék nem JSON-objektum")
    for k, nev in m.items():
        if media_nev(nev) is None:
            kihagyott += 1
        else:
            ki[str(k)] = {"nev": nev, "sha1": None, "meret": None}
    return ki, kihagyott


def _unicase(a: str, b: str) -> int:
    a, b = a.casefold(), b.casefold()
    return (a > b) - (a < b)


_AZON_VEGE = re.compile(r"(?:(?<=[ \t])|(?<![^\n]))\^(?=[A-Za-z0-9-]+[ \t]*$)", re.M)
_CARD_SOR = re.compile(r"^([ \t]*)\[!card\]", re.I | re.M)
_FORRAS_SOR = re.compile(r"^(.*?—[ \t]+)\[\[(?=[^\]\n]+\]\][ \t]*$)", re.M)


def semlegesit(szoveg: str) -> str:
    """Az idegen kártya szövege a kísérőjegyzet nyelvtanát (`formatum`) nem forgathatja ki: a sor végi `^azonosító` (egy másik
    kártya azonosítóját venné át), a `[!card]` kezdetű sor (új kártya), a `— [[cél]]` záró sor (idegen forrás-horgony) a
    `\\` jellel el van zárva — olvashatóan, a szöveg tartalma marad. A saját (felhasználói) szöveg ilyet nem tartalmaz."""
    szoveg = _AZON_VEGE.sub("\\^", szoveg)
    szoveg = _CARD_SOR.sub(lambda m: m.group(1) + "\\[!card]", szoveg)
    return _FORRAS_SOR.sub(lambda m: m.group(1) + "\\[[", szoveg)


def _egesz(x) -> int:
    """SQLite oszlopai típustalanok: csak valódi egész (nem bool, nem szöveg, nem float) fogadható el."""
    if isinstance(x, bool) or not isinstance(x, int):
        raise ValueError(f"nem egész: {x!r}")
    return x


def _jsonbol(szoveg):
    try:
        return json.loads(szoveg) if isinstance(szoveg, str) and szoveg else {}
    except (ValueError, RecursionError):
        return {}


def _modellek(c: sqlite3.Connection) -> dict[int, dict]:
    """{notetype-id: {nev, mezok: [név], cloze: bool}} — séma 11 (`col.models`) vagy 18 (`notetypes`, `fields`). A
    rosszindulatú alakú JSON/oszlop nem dob: az érintett modell hiányzik (alapértelmezett: nem cloze, nincs mezőnév)."""
    sor = c.execute("SELECT models FROM col").fetchone()
    m = _jsonbol(sor[0] if sor else None)
    if isinstance(m, dict) and m:
        ki = {}
        for k, v in m.items():
            try:
                if not isinstance(v, dict):
                    continue
                flds = [f for f in v.get("flds", []) if isinstance(f, dict)]
                flds.sort(key=lambda f: f["ord"] if isinstance(f.get("ord"), int) else 0)
                ki[int(k)] = {"nev": str(v.get("name", "")), "mezok": [str(f["name"]) for f in flds],
                              "cloze": v.get("type") == 1}
            except (TypeError, ValueError, KeyError):
                continue
        return ki
    ki = {}
    try:
        for r in c.execute("SELECT id, name, config FROM notetypes"):
            try:
                cfg = dict(protobuf(r[2] if isinstance(r[2], bytes) else b""))
                ki[_egesz(r[0])] = {"nev": str(r[1]), "mezok": [], "cloze": cfg.get(1, 0) == 1}
            except (ApkgHiba, ValueError):
                continue
        for r in c.execute("SELECT ntid, ord, name FROM fields ORDER BY ntid, ord"):
            if r[0] in ki:
                ki[r[0]]["mezok"].append(str(r[2]))
    except sqlite3.Error:
        return ki
    return ki


def _paklik(c: sqlite3.Connection) -> dict[int, str]:
    sor = c.execute("SELECT decks FROM col").fetchone()
    d = _jsonbol(sor[0] if sor else None)
    if isinstance(d, dict) and d:
        ki = {}
        for k, v in d.items():
            try:
                if isinstance(v, dict):
                    ki[int(k)] = str(v.get("name", ""))
            except (TypeError, ValueError):
                continue
        return ki
    try:
        return {r[0]: str(r[1]).replace("\x1f", "::") for r in c.execute("SELECT id, name FROM decks")}
    except sqlite3.Error:
        return {}


def _vegesz(x, felso: float) -> float | None:
    """Véges, pozitív, `felso`-nál nem nagyobb szám (nem bool), különben None (FSRS-adat: az `s`, `d`)."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    x = float(x)
    return x if math.isfinite(x) and 0 < x <= felso else None


def _allapot_ankibol(r, crt: datetime, lepesszam: tuple[int, int], naplo: list[dict]) -> tuple[dict, bool]:
    """Egy `cards` sor → (az FSRS-állapot, felfüggesztett-e). FSRS-adat (`s`, `d`) nélkül az ismételt kártya is új
    (az SM-2 pakli állapota nem FSRS; a napló átjön). Érvénytelen típus vagy tartomány: `ValueError`/`OverflowError` (a hívó
    az egész sort kihagyja); az értelmetlen `s`/`d` (NaN, végtelen, nem pozitív) csak az ütemezést dobja el (új kártya)."""
    tipus, sor = _egesz(r["type"]), _egesz(r["queue"])
    uj = {"allapot": UJ, "lepes": None, "stabilitas": None, "nehezseg": None, "esedekes": None, "utolso": None}
    if tipus == 0:
        return uj, sor == -1
    adat = r["data"]
    data = _jsonbol(adat) if isinstance(adat, str) and len(adat) <= ADAT_MAX else {}
    if not isinstance(data, dict):
        data = {}
    s, d = _vegesz(data.get("s"), 1e6), _vegesz(data.get("d"), 100)
    if s is None or d is None:
        return uj, sor == -1
    due, left = _egesz(r["due"]), _egesz(r["left"])
    lrt = data.get("lrt")
    utolso = None
    if isinstance(lrt, (int, float)) and not isinstance(lrt, bool) and lrt and math.isfinite(lrt):
        try:
            utolso = datetime.fromtimestamp(lrt, timezone.utc)
        except (OverflowError, OSError, ValueError):
            utolso = None
    if utolso is None and naplo:
        utolso = ido(naplo[-1]["mikor"])
    if tipus == 2 or sor == 3:      # napszám a `crt`-től; a napon belüli idő az utolsó ismétlésé (py-fsrs: due = review + n nap)
        esed = crt + timedelta(days=due) + _napon_beluli(utolso)
    else:
        esed = datetime.fromtimestamp(due, timezone.utc)
    allapot = {1: 1, 2: 2, 3: 3}.get(tipus, 2)
    lepes = None
    if allapot in (1, 3):
        n = lepesszam[0] if allapot == 1 else lepesszam[1]
        lepes = max(0, min(n - 1, n - (left % 1000))) if n else 0
    return {"allapot": allapot, "lepes": lepes, "stabilitas": s, "nehezseg": d,
            "esedekes": iso(esed), "utolso": iso(utolso)}, sor == -1


def _engedely(muvelet, *_):
    """Az idegen gyűjteményen csak olvasás: SELECT, oszlop-olvasás, függvényhívás; minden más (írás, PRAGMA, ATTACH) tiltva."""
    ok = (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE)
    return sqlite3.SQLITE_OK if muvelet in ok else sqlite3.SQLITE_DENY


def beolvas(fajl: Path, lepesszam: tuple[int, int] = (2, 1)) -> dict:
    """Egy `.apkg` (vagy `.colpkg`) beolvasása → pakli: {verzio, kartyak: [{guid, ord, azon (saját) | None, kerdes,
    valasz, forras, pakli, felfuggesztve, allapot, naplo: [{mikor, jegy, ms}]}], kihagyva: {ok: db}, media: [név]}.
    Semmit nem ír: a gyűjtemény ideiglenes másolatát csak olvasva nyitja (`mode=ro&immutable=1`, `trusted_schema=OFF`, csak
    SELECT-et engedő hitelesítővel). A csomag külső forrásból jön, ezért minden olvasott bejegyzés méret- és
    arány-korlátos, a médianevek csak sima fájlnevek (`media_nev`), a hibás csomag `ApkgHiba`. A médiafájlokat nem
    csomagolja ki (azt a `media_kicsomagol` teszi, K308)."""
    try:
        zf = zipfile.ZipFile(fajl)
    except zipfile.BadZipFile as e:
        raise ApkgHiba(f"nem érvényes zip-csomag: {e}") from None
    with zf as z:
        if len(z.infolist()) > ZIP_BEJEGYZES_MAX:
            raise ApkgHiba("a csomag túl sok bejegyzést tartalmaz")
        verzio = csomag_verzio(z)
        if verzio == LATEST:
            gy = _zstd(_zip_olvas(z, "collection.anki21b", GY_MAX), GY_MAX)
        else:
            gy = _zip_olvas(z, "collection.anki21" if verzio == LEGACY2 else "collection.anki2", GY_MAX)
        media, media_kihagyott = _media_terkep(z, verzio)
    with tempfile.TemporaryDirectory(prefix="mos-apkg-") as tmp:
        p = Path(tmp) / "gy.sqlite"
        p.write_bytes(gy)
        try:
            c = sqlite3.connect(f"file:{quote(str(p))}?mode=ro&immutable=1", uri=True)
        except sqlite3.Error as e:
            raise ApkgHiba(f"a gyűjtemény nem nyitható: {e}") from None
        try:
            c.text_factory = lambda b: b.decode("utf-8", "replace")      # az érvénytelen UTF-8 nem dobhat az iterálás közben
            c.create_collation("unicase", _unicase)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA trusted_schema = OFF")
            c.execute("PRAGMA query_only = ON")
            c.set_authorizer(_engedely)
            pakli = _olvas_gyujtemeny(c, verzio, sorted(set(media.values())), lepesszam)
        except sqlite3.Error as e:
            raise ApkgHiba(f"a gyűjtemény nem olvasható (sérült vagy idegen SQLite): {e}") from None
        finally:
            c.close()
    if media_kihagyott:
        pakli["kihagyva"]["media_nev"] = media_kihagyott
    return pakli


def _olvas_gyujtemeny(c: sqlite3.Connection, verzio: int, media: list[str], lepesszam: tuple[int, int]) -> dict:
    if c.execute("SELECT COUNT(*) FROM cards").fetchone()[0] > KARTYA_MAX:
        raise ApkgHiba(f"a csomag túl sok kártyát tartalmaz (legfeljebb {KARTYA_MAX})")
    if c.execute("SELECT COUNT(*) FROM revlog").fetchone()[0] > NAPLO_MAX:
        raise ApkgHiba(f"a csomag túl sok ismétlési naplót tartalmaz (legfeljebb {NAPLO_MAX})")
    sor = c.execute("SELECT crt FROM col").fetchone()
    try:
        crt = datetime.fromtimestamp(_egesz(sor[0]), timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        raise ApkgHiba("a gyűjtemény létrehozási ideje hiányzik vagy érvénytelen") from None
    modellek, paklik = _modellek(c), _paklik(c)
    jegyzetek = {r["id"]: r for r in c.execute(
        "SELECT id, guid, mid, CASE WHEN length(CAST(flds AS BLOB)) > ? THEN NULL ELSE flds END AS flds, "
        "coalesce(length(CAST(flds AS BLOB)) > ?, 0) AS nagy FROM notes", (MEZO_MAX, MEZO_MAX))}
    naplok: dict[int, list[dict]] = {}
    for r in c.execute("SELECT id, cid, ease, time FROM revlog ORDER BY id"):
        try:
            ease, mikor = _egesz(r["ease"]), _egesz(r["id"])
            if 1 <= ease <= 4:
                naplok.setdefault(_egesz(r["cid"]), []).append(
                    {"mikor": iso(datetime.fromtimestamp(mikor // 1000, timezone.utc)), "jegy": ease,
                     "ms": (r["time"] if isinstance(r["time"], int) and not isinstance(r["time"], bool) else 0) or None})
        except (ValueError, OverflowError, OSError):
            continue
    kartyak, kihagyva = [], {}

    def kihagy(ok: str) -> None:
        kihagyva[ok] = kihagyva.get(ok, 0) + 1

    for r in c.execute("SELECT id, nid, did, ord, type, queue, due, \"left\", "
                       "CASE WHEN length(data) > ? THEN NULL ELSE data END AS data FROM cards ORDER BY nid, ord", (ADAT_MAX,)):
        try:
            j = jegyzetek.get(r["nid"])
            if j is None:
                kihagy("jegyzet_nelkul")
                continue
            guid = j["guid"]
            if not isinstance(guid, str) or not guid or len(guid) > GUID_MAX:
                raise ValueError("érvénytelen guid")
            if j["nagy"]:
                kihagy("tul_nagy_mezo")
                continue
            m = modellek.get(j["mid"], {"nev": "", "mezok": [], "cloze": False})
            mezok = j["flds"].split("\x1f")
            if m["cloze"] or re.search(r"\{\{c\d+::", j["flds"]):
                kihagy("cloze")
                continue
            ord_ = _egesz(r["ord"])
            if len(mezok) < 2 or ord_ > 1 or ord_ < 0:
                kihagy("nem_ketoldalu")
                continue
            k, v = (mezok[0], mezok[1]) if ord_ == 0 else (mezok[1], mezok[0])
            azon = guid_azon(guid)
            forras = None
            if azon and len(mezok) > 2 and m["mezok"][2:3] == ["Forrás"]:
                forras = html.csupasz(mezok[2]) or None
            naplo = naplok.get(r["id"], [])
            allapot, felf = _allapot_ankibol(r, crt, lepesszam, naplo)
            kartyak.append({"guid": guid, "ord": ord_, "azon": azon, "kerdes": semlegesit(html.html_md(k)),
                            "valasz": semlegesit(html.html_md(v)), "forras": forras, "pakli": paklik.get(r["did"], ""),
                            "felfuggesztve": felf, "allapot": allapot, "naplo": naplo})
        except (TypeError, ValueError, OverflowError, OSError, KeyError, AttributeError, IndexError):
            kihagy("hibas_sor")
    return {"verzio": verzio, "kartyak": kartyak, "kihagyva": kihagyva, "media": media}


def azonositok_kioszt(cfg, pakli: dict) -> int:
    """Az idegen kártyák azonosítója a kísérőjegyzet megírása ELŐTT (C23b): a korábbi import leképezése (`apkg_kulcs`), különben új,
    ütközésmentes azonosító, és a leképezés rögzül (az újraimport így nem duplikál, akkor sem, ha a vault-írás elmarad). A pakli
    elemeibe írja (`azon`). → az új leképezések száma."""
    from .szinkron import foglalt_azonositok
    foglalt = foglalt_azonositok(cfg)
    uj = 0
    with tanulas_db.iro(cfg) as c:
        for k in pakli["kartyak"]:
            if k.get("azon"):
                continue
            r = c.execute("SELECT kartya FROM apkg_kulcs WHERE guid = ? AND ord = ?", (k["guid"], k["ord"])).fetchone()
            if r is not None:
                k["azon"] = r[0]
                continue
            azon = formatum.uj_azon(foglalt)
            foglalt.add(azon)
            c.execute("INSERT INTO apkg_kulcs (guid, ord, kartya) VALUES (?,?,?)", (k["guid"], k["ord"], azon))
            k["azon"] = azon
            uj += 1
    return uj


def importal(cfg, pakli: dict, most: datetime | None = None) -> dict:
    """A pakli állapota és naplója a `tanulas.sqlite`-ba. A saját kártya (guid → azonosító) és a korábban már
    importált idegen kártya (`apkg_kulcs`) frissül, ha a csomag állapota frissebb (az utolsó ismétlés szerint); az
    új idegen kártya új azonosítót kap — ezt a pakli elemeibe is beírja (`azon`), hogy a hívó a kísérőjegyzetet
    megírhassa. A napló `(kartya, mikor)` szerint duplikációmentes. **Élesben a kísérőjegyzet vaultba írása után
    hívandó** (C23b), különben a következő teljes szinkron töröltnek látná a kártyákat. → jelentés."""
    from .szinkron import foglalt_azonositok
    t = iso(most_utc(most))
    jel = {"uj": 0, "frissult": 0, "valtozatlan": 0, "naplo_uj": 0}
    foglalt = foglalt_azonositok(cfg)
    with tanulas_db.iro(cfg) as c:
        for k in pakli["kartyak"]:
            azon = k.get("azon")
            if azon is None:
                r = c.execute("SELECT kartya FROM apkg_kulcs WHERE guid = ? AND ord = ?", (k["guid"], k["ord"])).fetchone()
                if r is not None:
                    azon = r[0]
                else:
                    azon = formatum.uj_azon(foglalt)
                    c.execute("INSERT INTO apkg_kulcs (guid, ord, kartya) VALUES (?,?,?)", (k["guid"], k["ord"], azon))
                foglalt.add(azon)
                k["azon"] = azon
            a = k["allapot"]
            # a core szinkronja a frissen írt kísérőjegyzet kártyáját (üres `Modell`) `kezi`-ként láthatta előbb (C23b)
            c.execute("UPDATE kartya SET eredet = 'apkg' WHERE azon = ? AND eredet = 'kezi' AND utolso IS NULL", (azon,))
            r = c.execute("SELECT * FROM kartya WHERE azon = ?", (azon,)).fetchone()
            if r is None:
                c.execute("INSERT INTO kartya (azon, forras, kerdes, valasz, szoveg_hash, eredet, letrehozva, felfuggesztve, "
                          "allapot, lepes, stabilitas, nehezseg, esedekes, utolso) VALUES (?,?,?,?,?,'apkg',?,?,?,?,?,?,?,?)",
                          (azon, k.get("forras"), k["kerdes"], k["valasz"], formatum.szoveg_hash(k["kerdes"], k["valasz"]),
                           t, int(bool(k.get("felfuggesztve"))), a["allapot"], a["lepes"], a["stabilitas"],
                           a["nehezseg"], a["esedekes"] or t, a["utolso"]))
                jel["uj"] += 1
            elif (ido(a["utolso"]) or datetime.min.replace(tzinfo=timezone.utc)) > \
                    (ido(r["utolso"]) or datetime.min.replace(tzinfo=timezone.utc)):
                c.execute("UPDATE kartya SET " + ", ".join(f"{m} = ?" for m in MEZOK) + ", felfuggesztve = ? WHERE azon = ?",
                          (*(a[m] for m in MEZOK), int(bool(k.get("felfuggesztve"))), azon))
                jel["frissult"] += 1
            else:
                jel["valtozatlan"] += 1
            for v in k.get("naplo", []):
                if c.execute("SELECT 1 FROM valasz WHERE kartya = ? AND mikor = ?", (azon, v["mikor"])).fetchone():
                    continue
                c.execute("INSERT INTO valasz (kartya, mikor, jegy, ms, forras) VALUES (?,?,?,?,'apkg')",
                          (azon, v["mikor"], v["jegy"], v.get("ms")))
                jel["naplo_uj"] += 1
    return jel


# ------------------------------------------------------------------ média (K308; 55(b), 83. döntés javaslata)

MEDIA_FAJL_MAX = 256 << 20     # egy kicsomagolt médiafájl (55(b))
MEDIA_OSSZ_MAX = 4 << 30       # egy import összes kicsomagolt médiája (55(b))
_KEP_REF = re.compile(r"!\[\[([^\]|\n]+)((?:\|[^\]\n]*)?)\]\]")
_VAULT_TILTOTT = re.compile(r'[\\/:*?"<>|#^\[\]\x00-\x1f\x7f]')     # a `vaultio._TILTOTT_NEV` + DEL
NEV_MAX = 200                  # a vault-név bájtjai (a ` 12` utótagnak és a gépi írás 240 bájtos korlátjának hely marad)


class _Tul(Exception):
    pass


def hivatkozas_kulcs(nev: str) -> str:
    """A csomag médianevének alakja a kártya szövegében: a `html_md` a `<img src>`-ből `![[html.fajlnev(src)]]`-t ír (NFC)."""
    return unicodedata.normalize("NFC", html.fajlnev(_html.escape(nev)))


def hivatkozasok(szoveg: str) -> list[str]:
    """A szöveg `![[…]]` beágyazásainak céljai (sorrendben, ismétlés nélkül)."""
    ki: list[str] = []
    for m in _KEP_REF.finditer(szoveg):
        c = m.group(1).strip()
        if c not in ki:
            ki.append(c)
    return ki


def hivatkozas_csere(szoveg: str, terkep: dict[str, str]) -> str:
    """A `![[régi]]` (és `![[régi|…]]`) beágyazások célja a `terkep` szerint (NFC-kulcs; az URL-kódolt alak is). A nem szereplő
    cél marad."""
    def csere(m: re.Match) -> str:
        c = m.group(1).strip()
        uj = terkep.get(unicodedata.normalize("NFC", c)) or terkep.get(unicodedata.normalize("NFC", unquote(c)))
        return f"![[{uj}{m.group(2)}]]" if uj else m.group(0)
    return _KEP_REF.sub(csere, szoveg)


def vault_nev(nev: str) -> str | None:
    """A csomag (`media_nev`-en átment) médianevéből a vault-beli név: az Obsidian-linket törő és a vaultban tiltott jelek nélkül,
    `NEV_MAX` bájtra rövidítve (a kiterjesztés marad); a rejtett (ponttal kezdődő) vagy törzs nélküli név `None`."""
    n = unicodedata.normalize("NFC", nev)
    if n.startswith("."):
        return None
    torzs, kit = os.path.splitext(n)
    torzs = re.sub(r"\s+", " ", _VAULT_TILTOTT.sub("", torzs)).strip()
    kit = _VAULT_TILTOTT.sub("", kit)
    if not torzs or not kit:
        return None
    while torzs and len((torzs + kit).encode("utf-8")) > NEV_MAX:
        torzs = torzs[:-1].rstrip()
    return torzs + kit if torzs else None


def _kicsomagol_egy(z: zipfile.ZipFile, info: zipfile.ZipInfo, zstd_e: bool, cel: Path, max_bajt: int) -> tuple[str, str, int]:
    """Egy bejegyzés streamelve a `cel`-ba (`xb`: meglévőt nem ír felül), kimeneti plafonnal → (sha1, sha256, méret)."""
    from compression import zstd
    h1, h256, n = hashlib.sha1(), hashlib.sha256(), 0
    with z.open(info) as be:
        forras = zstd.ZstdFile(be) if zstd_e else be
        try:
            with open(cel, "xb") as ki:
                while True:
                    blokk = forras.read(1 << 20)
                    if not blokk:
                        break
                    n += len(blokk)
                    if n > max_bajt:
                        raise _Tul()
                    ki.write(blokk)
                    h1.update(blokk)
                    h256.update(blokk)
        finally:
            if zstd_e:
                forras.close()
    return h1.hexdigest(), h256.hexdigest(), n


def media_kicsomagol(fajl: Path, cel: Path, nevek: set[str] | None = None) -> dict:
    """A csomag médiafájljai a `cel` (az importáló saját, üres `{tmp}` mappája) alá — **soha `extractall`** (55(b)): bejegyzésenként,
    a kicsomagolt fájl neve sorszám (`<i>.bin`), sosem a csomag szövege (a zip-slip így kizárt); a név csak a jegyzékből, és csak
    `media_nev`-en átmenve. A `nevek`: a kártyák által hivatkozott médianevek (`None`: mind). Korlátok: fájlonként `MEDIA_FAJL_MAX`
    (256 MiB), összesen `MEDIA_OSSZ_MAX` (4 GiB), a deklarált méret és a kimeneti plafon szerint; LATEST csomagnál a `MediaEntry`
    sha1-e (kötelező) és mérete egyezik; a kiterjesztés a `core/mediatipus.APKG_MEDIA` fehérlistáján áll. A hibás fájl kimarad,
    megnevezve; a részben kiírt fájl (a saját `{tmp}` fájlunk) törlődik.

    → `{"verzio", "fajlok": [{nev, fajl, sha256, meret}], "kihagyva": [{nev, ok}], "csomagban": db}`. Az `ok`: `tiltott_kiterjesztes`,
    `duplikalt_nev`, `hianyzik_a_csomagbol`, `tul_nagy`, `zip_bomba`, `osszmeret`, `sha1_hianyzik`, `sha1_elter`, `meret_elter`,
    `serult`, `nem_biztonsagos_nev`."""
    from core import mediatipus
    cel.mkdir(parents=True, exist_ok=True)
    ki: dict = {"fajlok": [], "kihagyva": [], "csomagban": 0}
    try:
        zf = zipfile.ZipFile(fajl)
    except zipfile.BadZipFile as e:
        raise ApkgHiba(f"nem érvényes zip-csomag: {e}") from None
    with zf as z:
        if len(z.infolist()) > ZIP_BEJEGYZES_MAX:
            raise ApkgHiba("a csomag túl sok bejegyzést tartalmaz")
        verzio = csomag_verzio(z)
        ki["verzio"] = verzio
        bejegyzesek, rossz_nev = _media_bejegyzesek(z, verzio)
        ki["csomagban"] = len(bejegyzesek) + rossz_nev
        if rossz_nev:
            ki["kihagyva"].append({"nev": f"({rossz_nev} bejegyzés)", "ok": "nem_biztonsagos_nev"})
        latott: set[str] = set()
        ossz = 0
        for i, (kulcs, e) in enumerate(sorted(bejegyzesek.items(), key=lambda x: (len(x[0]), x[0]))):
            nev = e["nev"]
            if nevek is not None and nev not in nevek:
                continue
            ok = None
            info = None
            azonos = unicodedata.normalize("NFC", nev).casefold()
            deklaralt = 0
            if mediatipus.kiterjesztes(nev) not in mediatipus.APKG_MEDIA:
                ok = "tiltott_kiterjesztes"
            elif azonos in latott:
                ok = "duplikalt_nev"
            else:
                latott.add(azonos)
                try:
                    info = z.getinfo(kulcs)
                except KeyError:
                    ok = "hianyzik_a_csomagbol"
            if ok is None and verzio == LATEST and not (isinstance(e["sha1"], bytes) and len(e["sha1"]) == 20):
                ok = "sha1_hianyzik"
            if ok is None:
                deklaralt = e["meret"] if verzio == LATEST and e["meret"] is not None else info.file_size
                if deklaralt > MEDIA_FAJL_MAX or (verzio != LATEST and info.file_size > MEDIA_FAJL_MAX):
                    ok = "tul_nagy"
                elif verzio != LATEST and info.file_size > (1 << 20) and \
                        info.file_size > max(info.compress_size, 1) * ARANY_MAX:
                    ok = "zip_bomba"
                elif ossz + deklaralt > MEDIA_OSSZ_MAX:
                    ok = "osszmeret"
            if ok is not None:
                ki["kihagyva"].append({"nev": nev, "ok": ok})
                continue
            p = cel / f"{i}.bin"
            hatar = min(MEDIA_FAJL_MAX, MEDIA_OSSZ_MAX - ossz)
            try:
                sha1, sha256, n = _kicsomagol_egy(z, info, verzio == LATEST, p, hatar)
            except _Tul:
                ok = "tul_nagy" if hatar == MEDIA_FAJL_MAX else "osszmeret"
            except Exception:  # noqa: BLE001 — sérült/titkosított bejegyzés, hibás zstd, CRC-hiba: a fájl kimarad, a többi megy
                ok = "serult"
            else:
                if verzio == LATEST and e["meret"] is not None and e["meret"] != n:
                    ok = "meret_elter"
                elif verzio == LATEST and sha1 != e["sha1"].hex():
                    ok = "sha1_elter"
            if ok is not None:
                p.unlink(missing_ok=True)
                ki["kihagyva"].append({"nev": nev, "ok": ok})
                continue
            ossz += n
            ki["fajlok"].append({"nev": nev, "fajl": p, "sha256": sha256, "meret": n})
    return ki
