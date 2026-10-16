"""A „Ma” oldal összesítője (C15): `GET /api/ma?datum=ÉÉÉÉ-HH-NN` — a nap egy helyen, **csak olvasva**.

Szakaszok (mindegyik külön hibakezelésű: egy elérhetetlen forrás — hiányzó `pos.sqlite`, még épülő index — a
szakasz `hiba` mezejét tölti, a többi szakasz él):

- `napi`        a napi jegyzet útja, léte és rövid kivonata (a létrehozás a `naplo.py`-é);
- `dolgozatok`  a naptár „határidő” kategóriájának következő eseményei (az első a nagy kártya) és a hozzájuk
                kötött felkészülési jegyzet (a `[naplo] dolgozat_mappa` alatt: `<hónap>/<dolgozat_mappa>/ÉÉÉÉ-HH-NN - Tantárgy.md`);
- `naptar`      a mai események (a „kizárt” kategória — ünnepnap, születésnap — kimarad) és az adat kora;
- `feladatok`   a mai és a lejárt nyitott feladatok az index feladat-tábláiból;
- `naptar_allapot` a szinkron állapota (C29): segéd, engedély, utolsó kör, hiba;
- `javaslatok`  a jóváhagyásra váró tanulásiblokk-javaslatok (C29; csak a hátralévők);
- `kartyak`     a kártyák (C23b): `{allapot: "kesz", esedekes, uj, holnap, osszes}` a `tanulas.sqlite`-ból (csak olvasva).

A személyes adat a `{szemelyes}/pos.sqlite` (L56), **csak olvasva** (`mode=ro`): a naptárat a C29 szinkronja tölti
(`naptar.py`; a legacy utolsó importja a kiindulás) — ezért a válasz az `utolso_szinkron` időpontot és a `regi`
jelzőt is hordozza, hogy az oldal ki tudja mondani az adat korát. A `naptar_allapot` szakasz a szinkron élő
állapota (engedély, hiba), a `javaslatok` a jóváhagyásra váró tanulási blokkok.
"""
from __future__ import annotations

import json
import sqlite3
import unicodedata
import urllib.parse
from contextlib import closing
from datetime import date, datetime, timedelta

from . import naplo, sablon, szoveg_tisztit
from .index import feladatok
from .vaultio import NotFound

POS_FAJL = "pos.sqlite"
DOLGOZAT_DB_LIMIT = 3                    # a nagy kártya + két kis sor (jóváhagyott elrendezés)
KIVONAT_HOSSZ = 280


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _pos(cfg) -> sqlite3.Connection:
    """A személyes adatbázis csak olvasható kapcsolata; hiányzó fájl: `FileNotFoundError`."""
    ut = cfg.path("szemelyes") / POS_FAJL
    if not ut.is_file():
        raise FileNotFoundError("még nincs naptáradat: a naptár-szinkron még nem futott (a naptár-engedély a vezérlőben, ⇧⌘M)")
    c = sqlite3.connect(f"file:{urllib.parse.quote(str(ut))}?mode=ro", uri=True, timeout=2)
    c.row_factory = sqlite3.Row
    return c


def _szakasz(fn, *args) -> dict:
    """Egy szakasz kiszámítása; a hibája a szakasz `hiba` mezejébe kerül, nem az egész válaszba."""
    try:
        return fn(*args)
    except Exception as e:            # noqa: BLE001 — független szakaszok: az egyik hibája nem viheti el a többit
        return {"hiba": str(e) or e.__class__.__name__}


# ------------------------------------------------------------------ napi jegyzet

def _kivonat(szoveg: str) -> str:
    """A jegyzet törzsének első sorai a frontmatter és a címsorok nélkül, egy sorba fűzve, a Markdown-jelölés nélkül (C32b:
    `szoveg_tisztit.egyszeru`; csak a megjelenített szöveg — a jegyzet nem változik)."""
    szoveg = szoveg_tisztit.egyszeru(sablon.torzs(szoveg))
    return szoveg if len(szoveg) <= KIVONAT_HOSSZ else szoveg[:KIVONAT_HOSSZ].rstrip() + "…"


def napi(app, nap: date) -> dict:
    vault = app.vault
    ut = naplo.napi_ut(vault.cfg, nap)
    try:
        olvasott = vault.read(ut)
    except NotFound:
        return {"ut": ut, "letezik": False, "kivonat": ""}
    return {"ut": ut, "letezik": True, "kivonat": _kivonat(olvasott["tartalom"])}


# ------------------------------------------------------------------ naptár

def _nap_resz(iso: str | None) -> str:
    return (iso or "")[:10]


def _ora(iso: str | None) -> str:
    return (iso or "")[11:16]


def _veg_nap(r) -> str:
    """Az esemény utolsó napja; a csupa éjféli, egész napos vég (iCal: kizáró) az előző napot jelenti."""
    veg = r["veg"] or r["kezd"]
    if json.loads(r["payload"]).get("egesznap") and (veg or "")[11:19] == "00:00:00" and _nap_resz(veg) > _nap_resz(r["kezd"]):
        return (date.fromisoformat(_nap_resz(veg)) - timedelta(days=1)).isoformat()
    return _nap_resz(veg)


def _utolso_szinkron(c: sqlite3.Connection) -> str | None:
    sor = c.execute("SELECT max(vege) FROM import_futas WHERE forras = 'naptar' AND vege IS NOT NULL "
                    "AND allapot = 'engedelyezve'").fetchone()
    return sor[0] if sor and sor[0] else None


def _regi(utolso: str | None, most: datetime, ora: float) -> bool:
    if not utolso:
        return True
    try:
        t = datetime.fromisoformat(utolso)
    except ValueError:
        return True
    if t.tzinfo is None:
        t = t.astimezone()
    return most - t > timedelta(hours=ora)


def naptar(app, nap: date, most: datetime) -> dict:
    cfg = app.vault.cfg
    mai = nap.isoformat()
    with closing(_pos(cfg)) as c:
        esemenyek = []
        for r in c.execute(
                "SELECT r.forras_id, r.kezd, r.veg, r.payload, n.kategoria, n.szin, n.nev AS naptar_nev "
                "FROM forras_rekord r LEFT JOIN naptar n ON n.azon = json_extract(r.payload, '$.naptar') "
                "WHERE r.forras = 'naptar' AND r.tipus = 'esemeny' AND r.torolve IS NULL "
                "AND substr(r.kezd, 1, 10) <= ? AND substr(coalesce(r.veg, r.kezd), 1, 10) >= ? "
                "AND coalesce(n.kategoria, '') != 'kizart' AND coalesce(n.eltunt, '') = ''",
                (mai, mai)):
            if _veg_nap(r) < mai:
                continue
            p = json.loads(r["payload"])
            egesz = bool(p.get("egesznap"))
            esemenyek.append({
                "azon": r["forras_id"], "cim": p.get("cim") or "(cím nélkül)", "egesznap": egesz,
                "kezd": r["kezd"], "veg": r["veg"], "kezd_ora": "" if egesz else _ora(r["kezd"]),
                "veg_ora": "" if egesz else _ora(r["veg"]), "hely": p.get("hely") or "",
                "szin": r["szin"] or "", "kategoria": r["kategoria"] or "", "naptar": r["naptar_nev"] or ""})
        esemenyek.sort(key=lambda e: (not e["egesznap"], e["kezd"] or "", e["cim"]))
        utolso = _utolso_szinkron(c)
    return {"esemenyek": esemenyek, "utolso_szinkron": utolso,
            "regi": _regi(utolso, most, naplo.beallitasok(cfg)["naptar_regi_ora"])}


# ------------------------------------------------------------------ dolgozatok

def _kotesek(c, cfg, utak: list[str], mappa: str, napok: list[str]) -> dict:
    """A naptáresemények felkészülési jegyzete (L59) a C28 **közös kötésével** (`felkeszultseg.kotes`: biztos, valószínű, áthelyezve?;
    a tantárgyat a `naptar.targy()` adja, az órarend szerinti tantárgy-pótlással) — az esemény azonosítója → `Kotes`. C28b: a Ma oldal és
    a dolgozat-oldal ugyanazt a kötést használja (korábban a Ma saját, szó szerinti címegyezéses szabálya volt)."""
    if not utak or not napok:
        return {}
    from . import naptar as naptar_
    from .felkeszultseg import kotes
    tz = datetime.now().astimezone().tzinfo
    elso = date.fromisoformat(min(napok)) - timedelta(days=kotes.ATHELYEZES_MAX_NAP + 1)
    utolso = date.fromisoformat(max(napok)) + timedelta(days=kotes.ATHELYEZES_MAX_NAP + 2)
    esemenyek = naptar_.esemenyek(c, datetime.combine(elso, datetime.min.time(), tzinfo=tz),
                                  datetime.combine(utolso, datetime.min.time(), tzinfo=tz), cfg)
    return kotes.kot(kotes.jegyzetek(utak, mappa, naptar_.targyak_cfg(cfg)), esemenyek).esemenyek


def dolgozatok(app, nap: date, most: datetime) -> dict:
    cfg = app.vault.cfg
    mai = nap.isoformat()
    try:
        utak = app.index.fajl_halmaz()
    except Exception:                                  # az index még épül: a kártya jegyzet nélkül is él
        utak = []
    mappa = naplo.beallitasok(cfg)["dolgozat_mappa"]
    lista = []
    with closing(_pos(cfg)) as c:
        sorok = c.execute(
            "SELECT r.forras_id, r.kezd, r.veg, r.payload, n.szin FROM forras_rekord r "
            "JOIN naptar n ON n.azon = json_extract(r.payload, '$.naptar') "
            "WHERE r.forras = 'naptar' AND r.tipus = 'esemeny' AND r.torolve IS NULL AND n.kategoria = 'hatarido' "
            "AND coalesce(n.eltunt, '') = '' AND substr(r.kezd, 1, 10) >= ? ORDER BY r.kezd LIMIT ?", (mai, DOLGOZAT_DB_LIMIT)).fetchall()
        try:
            kotesek = _kotesek(c, cfg, utak, mappa, [_nap_resz(r["kezd"]) for r in sorok])
        except Exception:                              # noqa: BLE001 — a kötés hibája a dolgozat-kártyát nem viheti el
            kotesek = {}
        for r in sorok:
            p = json.loads(r["payload"])
            esemeny_nap = _nap_resz(r["kezd"])
            cim = p.get("cim") or "(cím nélkül)"
            k = kotesek.get(p.get("azon") or r["forras_id"])
            ut, fok = (k.jegyzet, k.fok) if k else (None, None)
            egesz = bool(p.get("egesznap"))
            lista.append({"azon": r["forras_id"], "cim": cim, "nap": esemeny_nap, "egesznap": egesz,
                          "ora": "" if egesz else _ora(r["kezd"]), "hely": p.get("hely") or "", "szin": r["szin"] or "",
                          "napok": (date.fromisoformat(esemeny_nap) - nap).days, "jegyzet": ut, "kotes": fok})
        utolso = _utolso_szinkron(c)
    return {"lista": lista, "utolso_szinkron": utolso,
            "regi": _regi(utolso, most, naplo.beallitasok(cfg)["naptar_regi_ora"])}


# ------------------------------------------------------------------ a szinkron állapota és a javaslatok (C29)

def naptar_allapot(app) -> dict:
    sz = getattr(app, "naptar", None)
    if sz is None:
        return {"seged": None}
    d = sz.allapot()
    return {"seged": d.get("seged"), "esemeny_engedely": d.get("esemeny_engedely"),
            "emlekezteto_engedely": d.get("emlekezteto_engedely"), "hiba": d.get("hiba"), "utolso": d.get("utolso"),
            "automatikus": d.get("automatikus")}


def javaslatok(app, nap: date) -> dict:
    sz = getattr(app, "naptar", None)
    if sz is None:
        return {"lista": []}
    return {"lista": [j for j in sz.javaslatok.lista() if j["nap"] >= nap.isoformat()]}


def asszisztens_szakasz(app) -> dict:
    """Az Asszisztens (C30a): a kapcsoló és a higiénia-riport új tételeinek száma — csak olvas, nem számol."""
    a = getattr(app, "asszisztens", None)
    return {"kapcsolo": False, "higienia": None} if a is None else a.ma_szakasz()


# ------------------------------------------------------------------ összesítés

def osszesit(app, szoveg_datum=None) -> dict:
    nap = naplo.datum_ertek(szoveg_datum)
    most = datetime.now().astimezone()
    dt = datetime(nap.year, nap.month, nap.day, 12, 0)
    nyelv = sablon.beallitasok(app.vault.cfg)["nyelv"]
    return {
        "datum": nap.isoformat(),
        "felirat": sablon.datum_formatum(dt, "YYYY. MMMM D., dddd", nyelv),
        "ma": nap == date.today(),
        "napi": _szakasz(napi, app, nap),
        "dolgozatok": _szakasz(dolgozatok, app, nap, most),
        "naptar": _szakasz(naptar, app, nap, most),
        "feladatok": _szakasz(lambda: feladatok.esedekes(app.index, nap.isoformat())),
        "naptar_allapot": _szakasz(naptar_allapot, app),
        "javaslatok": _szakasz(javaslatok, app, nap),
        "asszisztens": _szakasz(asszisztens_szakasz, app),
        "kartyak": _szakasz(kartyak, app),
    }


def kartyak(app) -> dict:
    """A kártyák (C23b): `{allapot: "kesz", esedekes, uj, holnap, osszes}` — csak olvas (a `tanulas.sqlite` olvasó kapcsolatán)."""
    from . import kartya_api
    return kartya_api.osszegzes(app.vault.cfg)


def utvonalak(r) -> None:
    r.get("/api/ma", lambda k: osszesit(k.app, k.q.get("datum")))
