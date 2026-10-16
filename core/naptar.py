"""A naptár (C29, 32. döntés): a macOS Naptár eseményei a személyes adatbázisba, kategóriákkal — a legacy
`src/mos/szemelyes/naptar.py` portja (D12, L56–L59), az EventKit-segéd a Manifold.app csomagjában (`naptar_seged.py`).

A naptárak — *Me-time és programok*, *Tanulás*, *Órarend*, *Edzés*, *Határidők és dolgozatok* — táplálják a Ma
oldalt, a tanulásiblokk-javaslatot és (C28) a kiértékelőt. A naptár szerepe (kategória) a naptár **azonosítójához**
kötődik, nem a nevéhez: az átnevezés nem bontja a kötést (a változás naplózva és jelezve); ha egy azonosító eltűnik,
és új jelenik meg ugyanazzal a névvel (pl. újra bejelentkeztetett fiók), a kategória átöröklődik. Az új naptárnak a
neve alapján javaslat készül; amit a felhasználó kiválaszt, az végleges (`kategoria_forras = gazda`).

A szinkron az ablak ([ma − mult_nap, ma + jovo_nap]) minden eseményét a `forras_rekord` táblába írja (új, változott,
változatlan; ami az ablakból eltűnt, `torolve` jelet kap — nem törlődik). A naptárba **semmi nem ír** ebből a
modulból: az esemény írása csak a jóváhagyott javaslaté (`naptar_javaslat.py`, D12).

A tracker kapcsolója alatt (10. döntés) a `tr_naptar_blokk` is épül: a tanulás kategóriájú, nem egész napos blokkok
tantárggyal — a tracker a tervezett időt innen számolja.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sqlite3
import unicodedata

from . import szemelyes_db
from .naptar_seged import Seged

FORRAS = "naptar"

# ------------------------------------------------------------------ kategóriák
# A kulcsszavas szótárak (a kategóriák `szavak`-ja, a dolgozat- és határidő-szavak, a tantárgyak és gyűjtőneveik) a
# `[naptar.szotar]` szakaszból jönnek (`szotar(cfg)`); az alábbi beépített értékek csak a hiányzó kulcsot pótolják.

KATEGORIAK = [
    {"id": "szabadido", "nev": "Me-time és programok", "szin": "#e68aa8",
     "szavak": ["me-time", "me time", "metime", "program", "programok", "szabadido", "szabad ido", "szemelyes", "personal",
                "fun", "social", "barat", "baratok", "hobbi", "hobby", "csalad"]},
    {"id": "tanulas", "nev": "Tanulás", "szin": "#a08cf6",
     "szavak": ["tanulas", "tanul", "study", "studying", "learning", "felkeszules", "gyakorlas", "hazi", "homework"]},
    {"id": "orarend", "nev": "Órarend", "szin": "#78a6e6",
     "szavak": ["orarend", "iskola", "suli", "tanora", "timetable", "school", "classes", "lessons"]},
    {"id": "edzes", "nev": "Edzés", "szin": "#62c48f",
     "szavak": ["edzes", "gym", "workout", "workouts", "training", "sport", "futas", "fitness", "konditerem", "kondi", "run", "running"]},
    {"id": "hatarido", "nev": "Határidők és dolgozatok", "szin": "#ec7c61",
     "szavak": ["hatarido", "hataridok", "deadline", "deadlines", "dolgozat", "dolgozatok", "exam", "exams", "vizsga", "vizsgak",
                "zh", "temazaro", "beadando", "teszt", "felmeres", "szamonkeres"]},
    {"id": "egyeb", "nev": "Egyéb", "szin": "#bdb6aa", "szavak": []},
    {"id": "kizart", "nev": "Kizárva", "szin": "#6c6962",
     "szavak": ["unnep", "unnepnap", "unnepek", "holiday", "holidays", "szuletesnap", "birthday", "birthdays", "nevnap",
                "siri", "suggestions", "javaslatok", "scheduled reminders"]},
]
KATEGORIA_ID = {k["id"] for k in KATEGORIAK}
TERV_KATEGORIAK = ("tanulas",)       # a tr_naptar_blokk-ba kerülő kategóriák (a tervezett tanulási idő)

# az esemény címe alapján (bármely naptárban): dolgozat vagy határidő
DOLGOZAT_SZAVAK = ["dolgozat", "dolgozatot", "dolgozatir", "temazaro", "tz", "zh", "vizsga", "exam", "test", "teszt",
                   "felmeres", "szamonkeres", "kisdolgozat", "felelés", "feleles", "quiz"]
HATARIDO_SZAVAK = ["hatarido", "deadline", "beadando", "beadas", "leadas", "leadni", "beadni", "due"]
# ezekben a naptárakban az esemény idő (tanulás, edzés, program) — a „dolgozat” szó itt készülést jelent, nem számonkérést
NEM_SZAMONKERES = ("tanulas", "edzes", "szabadido", "kizart")

# tantárgyak: a kanonikus név (ahogy a dolgozat-jegyzetek fájlneve írja) → rokon szavak (ékezet nélkül, kisbetűvel).
# Forrás: `[naptar.szotar.targyak]`; az os.toml [naptar.targyak] szakasza kiegészítheti (név = ["szó", …]). Beépített szótár nincs:
# a tantárgyak a munkatér sajátjai (a fejlesztő szótára a `config/presets/v2-kompat.toml`-ban van).
TARGYAK: dict[str, list[str]] = {}
# gyűjtőnév: ha a naptár csak ennyit ír, mindegyik tagja jöhet (gyengébb egyezés); forrás: `[naptar.szotar.csoportok]`
CSOPORTOK: dict[str, list[str]] = {}


def norm(s: str | None) -> str:
    """Ékezet nélkül, kisbetűvel, egyszerű szóközökkel (a kulcsszavas egyezéshez)."""
    s = unicodedata.normalize("NFD", str(s or "")).lower()
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[\s_]+", " ", s).strip()


def _szo_benne(szoveg: str, szo: str) -> bool:
    """Szóhatáron kezdődő egyezés: a hosszabb szó előtagként is (a „tanul” a „tanulás”-ban, a „matek” a „matekból”-ban),
    a legfeljebb 4 betűs csak egész szóként (a „mat” ne a „materiál”-ban, a „test” ne a „testnevelés”-ben)."""
    szo = norm(szo)
    return re.search(r"(?<![a-z0-9])" + re.escape(szo) + (r"(?![a-z0-9])" if len(szo) <= 4 else ""), szoveg) is not None


class Targyak(dict):
    """A tantárgy-térkép (kanonikus név → rokon szavak) a gyűjtőnevekkel (`csoportok`) együtt."""

    def __init__(self, targyak: dict, csoportok: dict | None = None):
        super().__init__(targyak)
        self.csoportok = dict(CSOPORTOK if csoportok is None else csoportok)


def _szolista(v, alap: list[str]) -> list[str]:
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else list(alap)


def _szoterkep(v, alap: dict) -> dict[str, list[str]]:
    if not isinstance(v, dict):
        return {k: list(x) for k, x in alap.items()}
    return {str(k): [x for x in s if isinstance(x, str)] for k, s in v.items() if isinstance(s, list)}


def szotar(cfg) -> dict:
    """A naptár kulcsszavas szótára a `[naptar.szotar]` szakaszból: `kategoriak` (kategória-azonosító → szavak), `dolgozat`,
    `hatarido` (szólisták), `targyak` (kanonikus név → szavak), `csoportok` (gyűjtőnév → kanonikus nevek). A hiányzó vagy
    hibás típusú kulcs a beépített alapot adja; a kategóriák azonosítója, neve és színe a kódé."""
    s = (cfg.section("naptar", "szotar") if cfg is not None else {}) or {}
    kat = s.get("kategoriak") if isinstance(s.get("kategoriak"), dict) else {}
    return {"kategoriak": {k["id"]: _szolista(kat.get(k["id"]), k["szavak"]) for k in KATEGORIAK},
            "dolgozat": _szolista(s.get("dolgozat"), DOLGOZAT_SZAVAK),
            "hatarido": _szolista(s.get("hatarido"), HATARIDO_SZAVAK),
            "targyak": _szoterkep(s.get("targyak"), TARGYAK),
            "csoportok": _szoterkep(s.get("csoportok"), CSOPORTOK)}


def javasol(nev: str, tipus: str = "", kategoriak: dict[str, list[str]] | None = None) -> tuple[str, bool]:
    """(kategória, biztos) a naptár neve és típusa alapján. Biztos, ha pontosan egy kategória szavai illenek.
    `kategoriak`: kategória-azonosító → szavak (`szotar(cfg)["kategoriak"]`; alap: a beépített)."""
    if tipus in ("szuletesnap",):
        return "kizart", True
    n = norm(nev)
    szavak = kategoriak if kategoriak is not None else {k["id"]: k["szavak"] for k in KATEGORIAK}
    talalt = [kid for kid, sz in szavak.items() if any(_szo_benne(n, norm(s)) for s in sz)]
    if len(talalt) == 1:
        return talalt[0], True
    if len(talalt) > 1:
        return talalt[0], False
    return "egyeb", False


def targyak_cfg(cfg) -> Targyak:
    """A tantárgy-térkép: a `[naptar.szotar.targyak]` (alap: `TARGYAK`), a `[naptar.targyak]` kiegészítéseivel, és a
    `[naptar.szotar.csoportok]` gyűjtőnevei."""
    sz = szotar(cfg)
    t = {k: list(v) for k, v in sz["targyak"].items()}
    for k, v in ((cfg.section("naptar", "targyak") if cfg else {}) or {}).items():
        if isinstance(v, list):
            t.setdefault(k, [])
            t[k] += [norm(x) for x in v if isinstance(x, str)]
    return Targyak(t, sz["csoportok"])


def targy(szoveg: str, targyak: dict[str, list[str]] | None = None) -> list[str]:
    """A szövegben (esemény címe, jegyzet neve) említett tantárgyak kanonikus neve. Üres, ha egyik sem."""
    n = norm(szoveg)
    targyak = targyak or TARGYAK
    out = []
    for kanon, szavak in targyak.items():
        if any(_szo_benne(n, s) for s in [kanon] + szavak):
            out.append(kanon)
    if not out:
        for gyujto, tagok in getattr(targyak, "csoportok", CSOPORTOK).items():
            if _szo_benne(n, gyujto):
                out.extend(tagok)
    return out


def esemeny_fajta(cim: str, kategoria: str, targyak: dict[str, list[str]] | None = None,
                  szotar_: dict | None = None) -> str | None:
    """„dolgozat”, „hatarido” vagy None. A határidő-naptárban minden esemény vagy dolgozat, vagy határidő: ha a
    címben tantárgy áll, és nincs határidő-szó, dolgozat. A tanulás-, edzés- és programnaptár eseménye egyik sem.
    `szotar_`: a `szotar(cfg)` (a `dolgozat` és a `hatarido` szólista; alap: a beépített)."""
    if kategoria in NEM_SZAMONKERES:
        return None
    n = norm(cim)
    hat = any(_szo_benne(n, s) for s in (szotar_ or {}).get("hatarido", HATARIDO_SZAVAK))
    dol = any(_szo_benne(n, s) for s in (szotar_ or {}).get("dolgozat", DOLGOZAT_SZAVAK)) or any(x in n for x in ("dolgozat", "temazaro", "vizsga"))  # összetett szóban is
    if dol and not hat:
        return "dolgozat"
    if kategoria == "hatarido":
        if hat:
            return "hatarido"
        return "dolgozat" if targy(cim, targyak) else "hatarido"
    if hat:
        return "hatarido"
    return None


# ------------------------------------------------------------------ szinkron

def _most() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def beallitasok(cfg) -> dict:
    s = cfg.section("naptar")
    return {"automatikus": bool(s.get("automatikus", True)), "szinkron_perc": float(s.get("szinkron_perc", 15)),
            "indulasi_kesleltetes_mp": float(s.get("indulasi_kesleltetes_mp", 60)),
            "mult_nap": int(s.get("mult_nap", 120)), "jovo_nap": int(s.get("jovo_nap", 180)),
            "tanulas_naptar": str(s.get("tanulas_naptar", "") or "")}


def ablak(cfg, most: dt.datetime | None = None) -> tuple[dt.datetime, dt.datetime]:
    sec = beallitasok(cfg)
    most = (most or dt.datetime.now().astimezone()).replace(hour=0, minute=0, second=0, microsecond=0)
    return most - dt.timedelta(days=sec["mult_nap"]), most + dt.timedelta(days=sec["jovo_nap"])


def _naptarak_frissit(c, bejott: list[dict], most: str, kategoriak: dict[str, list[str]] | None = None) -> list[dict]:
    """A naptárlista összevetése az ismerttel: új, átnevezett, eltűnt, újra összekötött naptárak. A változások a
    `naptar_valtozas` táblába kerülnek, és a függvény vissza is adja őket."""
    ismert = {r["azon"]: dict(r) for r in c.execute("SELECT * FROM naptar")}
    bejott_azon = {n["azon"] for n in bejott}
    valtozas = []

    def naplo(azon, fajta, regi=None, uj=None):
        c.execute("INSERT INTO naptar_valtozas VALUES (?,?,?,?,?)", (most, azon, fajta, regi, uj))
        valtozas.append({"azon": azon, "fajta": fajta, "regi": regi, "uj": uj})

    # ami eltűnt (és még nem jelöltük): az újra-összekötés jelöltjei
    eltunt = {a: r for a, r in ismert.items() if a not in bejott_azon and not r["utod"]}
    for a, r in eltunt.items():
        if not r["eltunt"]:
            c.execute("UPDATE naptar SET eltunt=? WHERE azon=?", (most, a))
            naplo(a, "eltunt", r["nev"], None)
    for n in bejott:
        a, nev = n["azon"], n.get("nev") or "?"
        r = ismert.get(a)
        if r:
            if r["nev"] != nev:
                naplo(a, "atnevezve", r["nev"], nev)
            if r["szin"] and n.get("szin") and r["szin"] != n.get("szin"):
                naplo(a, "szin", r["szin"], n.get("szin"))
            if r["eltunt"]:
                naplo(a, "visszajott", None, nev)
            c.execute("UPDATE naptar SET nev=?, forras=?, forras_tipus=?, tipus=?, szin=?, utoljara_latva=?, eltunt=NULL WHERE azon=?",
                      (nev, n.get("forras"), n.get("forras_tipus"), n.get("tipus"), n.get("szin"), most, a))
            continue
        # új azonosító: egy eltűnt naptár utódja-e? (ugyanaz a név ugyanabban a fiókban, vagy egyedül ugyanaz a név)
        jeloltek = [x for x in eltunt.values() if norm(x["nev"]) == norm(nev) and not x["utod"]]
        ugyanott = [x for x in jeloltek if (x["forras"] or "") == (n.get("forras") or "")]
        elod = ugyanott[0] if len(ugyanott) == 1 else jeloltek[0] if len(jeloltek) == 1 else None
        if elod:
            kat, kforras = elod["kategoria"], elod["kategoria_forras"]
            c.execute("UPDATE naptar SET utod=? WHERE azon=?", (a, elod["azon"]))
            naplo(a, "osszekotve", elod["azon"], nev)
        else:
            kat, biztos = javasol(nev, n.get("tipus") or "", kategoriak)
            kforras = "auto" if biztos else "javaslat"
            naplo(a, "uj", None, nev)
        c.execute("INSERT INTO naptar (azon, nev, forras, forras_tipus, tipus, szin, kategoria, kategoria_forras, elso_latva, utoljara_latva) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (a, nev, n.get("forras"), n.get("forras_tipus"), n.get("tipus"), n.get("szin"), kat, kforras, most, most))
    return valtozas


def _blokkok_frissit(c, cfg, tol: dt.datetime, ig: dt.datetime) -> int:
    """A `tr_naptar_blokk` újraépítése az ablakra: a tanulás kategóriájú, nem egész napos, nem törölt, nem kizárt
    események tantárggyal (a cím alapján). Ami az ablakból eltűnt, kikerül; a tábla származtatott gyorsítótár."""
    t = targyak_cfg(cfg)
    uj: dict[str, tuple] = {}
    for r in c.execute(
            "SELECT r.forras_id, r.kezd, r.veg, r.payload, n.kategoria FROM forras_rekord r "
            "JOIN naptar n ON n.azon = json_extract(r.payload, '$.naptar') "
            "WHERE r.forras = ? AND r.tipus = 'esemeny' AND r.torolve IS NULL AND coalesce(n.eltunt, '') = '' "
            "AND n.kategoria IN (%s) AND r.kezd >= ? AND r.kezd < ?" % ",".join("?" * len(TERV_KATEGORIAK)),
            (FORRAS, *TERV_KATEGORIAK, tol.isoformat(timespec="seconds"), ig.isoformat(timespec="seconds"))):
        p = json.loads(r["payload"])
        if p.get("egesznap") or not r["veg"] or p.get("allapot") == 3:
            continue
        tantargyak = targy(p.get("cim", ""), t)
        uj[r["forras_id"]] = (r["forras_id"], (r["kezd"] or "")[:10], r["kezd"], r["veg"], r["kategoria"],
                              tantargyak[0] if tantargyak else None, FORRAS)
    c.execute("DELETE FROM tr_naptar_blokk WHERE forras = ? AND kezd >= ? AND kezd < ?",
              (FORRAS, tol.isoformat(timespec="seconds"), ig.isoformat(timespec="seconds")))
    c.executemany("INSERT OR REPLACE INTO tr_naptar_blokk (azon, nap, kezd, veg, kategoria, tantargy, forras) VALUES (?,?,?,?,?,?,?)",
                  list(uj.values()))
    return len(uj)


def szinkron(cfg, seged: Seged | None = None, most: dt.datetime | None = None, tracker_be: bool = False) -> dict:
    """A naptár beolvasása a segéddel. → `{allapot, uj, valtozott, torolt, osszes, valtozasok, blokkok}`; ha nincs
    engedély, az állapot (`nincs_dontes`, `megtagadva`, …) jön, adat nélkül. Segéd-hiba: `SegedHiba`."""
    seged = seged or Seged(cfg)
    tol, ig = ablak(cfg, most)
    kezdes = _most()
    adat = seged.olvas(tol.isoformat(timespec="seconds"), ig.isoformat(timespec="seconds"))
    allapot = adat.get("allapot") or "ismeretlen"
    if allapot != "engedelyezve":
        # engedély nélkül nincs író kapcsolat (T007): nem hoz létre fájlt, nem migrál (a pos.sqlite 3-asra lépése a
        # régebbi kódot kizárná), nem ír `import_futas` sort — az engedély-állapot a szolgáltatás memóriájában él
        return {"allapot": allapot, "uj": 0, "valtozott": 0, "torolt": 0, "osszes": 0, "valtozasok": [], "blokkok": None}
    with szemelyes_db.iro(cfg) as c:
        fid = c.execute("INSERT INTO import_futas (forras, kezdes, allapot) VALUES (?,?,?)", (FORRAS, kezdes, allapot)).lastrowid
        valtozasok = _naptarak_frissit(c, adat.get("naptarak") or [], kezdes, szotar(cfg)["kategoriak"])
        regi = {r["forras_id"]: (r["hash"], r["torolve"]) for r in c.execute(
            "SELECT forras_id, hash, torolve FROM forras_rekord WHERE forras=?", (FORRAS,))}
        uj = valtozott = 0
        latott = set()
        for e in adat.get("esemenyek") or []:
            fid_e = str(e.get("azon") or "")
            if not fid_e or fid_e in latott:
                continue
            latott.add(fid_e)
            payload = json.dumps(e, ensure_ascii=False, sort_keys=True)
            h = hashlib.sha1(payload.encode()).hexdigest()
            r = regi.get(fid_e)
            if r and r[0] == h and not r[1]:
                continue
            c.execute("INSERT INTO forras_rekord (forras, forras_id, kezd, veg, tipus, payload, hash, importalva, import_futas, torolve) "
                      "VALUES (?,?,?,?,?,?,?,?,?,NULL) ON CONFLICT (forras, forras_id) DO UPDATE SET kezd=excluded.kezd, veg=excluded.veg, "
                      "payload=excluded.payload, hash=excluded.hash, importalva=excluded.importalva, import_futas=excluded.import_futas, torolve=NULL",
                      (FORRAS, fid_e, e.get("kezd"), e.get("veg"), "esemeny", payload, h, kezdes, fid))
            if r:
                valtozott += 1
            else:
                uj += 1
        # az ablakban volt, most nincs: törölték vagy áthelyezték — jelölés, nem törlés (a provenancia megmarad)
        torolt = 0
        for (fid_r,) in c.execute("SELECT forras_id FROM forras_rekord WHERE forras=? AND torolve IS NULL AND kezd >= ? AND kezd < ?",
                                  (FORRAS, tol.isoformat(timespec="seconds"), ig.isoformat(timespec="seconds"))).fetchall():
            if fid_r not in latott:
                c.execute("UPDATE forras_rekord SET torolve=? WHERE forras=? AND forras_id=?", (kezdes, FORRAS, fid_r))
                torolt += 1
        blokkok = _blokkok_frissit(c, cfg, tol, ig) if tracker_be else None
        c.execute("UPDATE import_futas SET vege=?, uj=?, valtozott=?, torolt=?, osszes=? WHERE id=?",
                  (_most(), uj, valtozott, torolt, len(latott), fid))
    return {"allapot": allapot, "uj": uj, "valtozott": valtozott, "torolt": torolt, "osszes": len(latott),
            "valtozasok": valtozasok, "blokkok": blokkok}


def hiba_rogzit(cfg, uzenet: str) -> None:
    """Egy sikertelen szinkron-kísérlet nyoma (`import_futas`), hogy a „kor” jelzése ne a régi sikeres futásra álljon."""
    try:
        with szemelyes_db.iro(cfg) as c:
            c.execute("INSERT INTO import_futas (forras, kezdes, vege, allapot, uzenet) VALUES (?,?,?,?,?)",
                      (FORRAS, _most(), _most(), "hiba", uzenet[:500]))
    except (sqlite3.Error, OSError):
        pass


def kategoria_allit(cfg, azon: str, kategoria: str) -> dict:
    if kategoria not in KATEGORIA_ID:
        raise ValueError(f"ismeretlen kategória: {kategoria}")
    with szemelyes_db.iro(cfg) as c:
        if not c.execute("SELECT 1 FROM naptar WHERE azon=?", (azon,)).fetchone():
            raise KeyError("ismeretlen naptár")
        c.execute("UPDATE naptar SET kategoria=?, kategoria_forras='gazda' WHERE azon=?", (kategoria, azon))
    return {"ok": True, "azon": azon, "kategoria": kategoria}


# ------------------------------------------------------------------ olvasás (csak olvas, megnyitáskor is szabad)

def naptarak(c) -> list[dict]:
    return [dict(r) for r in c.execute("SELECT * FROM naptar WHERE utod IS NULL ORDER BY eltunt IS NOT NULL, nev")]


def _ido(s: str | None) -> dt.datetime | None:
    try:
        d = dt.datetime.fromisoformat(s) if s else None
    except ValueError:
        return None
    return d.astimezone() if d else None


def esemenyek(c, tol: dt.datetime, ig: dt.datetime, cfg=None) -> list[dict]:
    """Az események a [tol, ig) időablakban, a naptár kategóriájával, a fajtájukkal (dolgozat / határidő) és a
    címükben említett tantárgyakkal. Ha egy dolgozatnak vagy határidőnek a címében nincs tantárgy („Témazáró”),
    az aznap vele egy időben tartott óra tantárgyát kapja (`targy_forras: orarend`); a dolgozat órája `ora`.
    A kizárt naptárak és a lemondott események nélkül."""
    kat = {r["azon"]: r for r in c.execute("SELECT azon, nev, kategoria, szin FROM naptar")}
    t = targyak_cfg(cfg)
    sz = szotar(cfg)
    out = []
    a0 = (tol - dt.timedelta(days=1)).isoformat(timespec="seconds")
    a1 = (ig + dt.timedelta(days=1)).isoformat(timespec="seconds")
    for r in c.execute("SELECT payload FROM forras_rekord WHERE forras=? AND torolve IS NULL AND kezd < ? AND veg > ? ORDER BY kezd",
                       (FORRAS, a1, a0)):
        e = json.loads(r["payload"])
        k0, k1 = _ido(e.get("kezd")), _ido(e.get("veg"))
        if not k0 or not k1 or not (k0 < ig and k1 > tol):
            continue
        n = kat.get(e.get("naptar"))
        k = n["kategoria"] if n else "egyeb"
        if k == "kizart" or e.get("allapot") == 3:             # EKEventStatus.canceled
            continue
        e.update(kategoria=k, naptar_nev=n["nev"] if n else "?", naptar_szin=n["szin"] if n else None,
                 fajta=esemeny_fajta(e.get("cim", ""), k, t, sz), targyak=targy(e.get("cim", ""), t), targy_forras="cim",
                 _k0=k0, _k1=k1)
        out.append(e)
    # a dolgozat órája: az órarend vele átfedő órája; tantárgy nélküli dolgozatnál a tantárgyat is ez adja
    orak = [e for e in out if e["kategoria"] == "orarend" and not e.get("egesznap")]
    for e in out:
        if not e["fajta"] or e.get("egesznap"):
            continue
        ora = [o for o in orak if o is not e and o["_k0"] < e["_k1"] and o["_k1"] > e["_k0"]]
        if e["targyak"]:
            ora = [o for o in ora if set(o["targyak"]) & set(e["targyak"])] or ora
        if ora:
            e["ora"] = {"cim": ora[0]["cim"], "kezd": ora[0]["kezd"], "veg": ora[0]["veg"]}
            if not e["targyak"] and ora[0]["targyak"]:
                e["targyak"], e["targy_forras"] = list(ora[0]["targyak"]), "orarend"
                if e["kategoria"] == "hatarido" and e["fajta"] == "hatarido" and not any(
                        _szo_benne(norm(e.get("cim", "")), s) for s in sz["hatarido"]):
                    e["fajta"] = "dolgozat"                   # órán, határidő-szó nélkül: számonkérés
    for e in out:
        e.pop("_k0", None)
        e.pop("_k1", None)
    return out


def utolso_szinkron(c) -> dict | None:
    r = c.execute("SELECT * FROM import_futas WHERE forras=? ORDER BY id DESC LIMIT 1", (FORRAS,)).fetchone()
    if not r:
        return None
    d = dict(r)
    ok = c.execute("SELECT vege FROM import_futas WHERE forras=? AND allapot='engedelyezve' AND vege IS NOT NULL ORDER BY id DESC LIMIT 1",
                   (FORRAS,)).fetchone()
    d["utolso_sikeres"] = ok["vege"] if ok else None
    return d


def valtozasok(c, napok: int = 21) -> list[dict]:
    hatar = (dt.datetime.now().astimezone() - dt.timedelta(days=napok)).isoformat(timespec="seconds")
    return [dict(r) for r in c.execute("SELECT * FROM naptar_valtozas WHERE mikor >= ? AND fajta != 'uj' ORDER BY mikor DESC LIMIT 30", (hatar,))]

