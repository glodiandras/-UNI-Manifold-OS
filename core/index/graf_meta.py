"""A gráfnézet kiegészítő adatai (C13): jegyzetenkénti címke és tulajdonság, valamint az Obsidian gráf-beállításai.

Csak olvas. A `/api/vault/graf` változatlan marad (csúcs- és élhalmaz = a core gráfja); ez a modul a szűréshez és a
színezéshez hoz mellé adatot. Az SQL-olvasáshoz az `IndexOlvaso.olvaso()` nyilvános kontextust használja (a nehéz olvasók zára alatt).
"""
from __future__ import annotations

import json
import os

from . import kizaras
from .feloldas import nfc

MAX_ERTEK_HOSSZ = 200      # egy tulajdonság-érték szövege ennél hosszabb nem megy a szűrőbe
MAX_ERTEK_DB = 20          # egy kulcs értékei közül ennyi kerül ki
MAX_FELOLDATLAN_EL = 60000  # a feloldatlan link-élek felső korlátja (nagy vaultnál a válasz és a gráf mérete; túlfutás: `feloldatlan_csonkolt`)
MAX_CIMKE_HOSSZ = 200      # egy címke-csúcs neve ennél hosszabb nem kerül a gráfba


def _ertekek(nyers: str) -> list[str]:
    """Egy `tulajdonsag.ertek` (JSON) szűrhető szövegei: skalár → 1, lista → elemenként, más → a JSON-szöveg."""
    try:
        v = json.loads(nyers)
    except (TypeError, ValueError):
        return []
    elemek = v if isinstance(v, list) else [v]
    ki: list[str] = []
    for e in elemek:
        if e is None or isinstance(e, (dict, list)):
            continue
        s = ("igaz" if e else "hamis") if isinstance(e, bool) else str(e)
        s = s.strip()
        if s:
            ki.append(s[:MAX_ERTEK_HOSSZ])
        if len(ki) >= MAX_ERTEK_DB:
            break
    return ki


def graf_meta(index) -> dict:
    """`{cimkek: {ut: [cimke, …]}, tulajdonsagok: {ut: {kulcs: [ertek, …]}}, cimke_csucsok: {kulcs: {nev, db}},
    feloldatlan_elek: [[forras_ut, cel], …], feloldatlan_csonkolt: bool}` — csak az élő, nem üres jegyzetekre.

    A `cimke_csucsok` és a `feloldatlan_elek` a gráf „címkék” és „csak létező fájlok” kapcsolójának adata (11-graph-02/03): a címke
    a core `cimke` táblájából jön (egy jegyzet egyszer), a feloldatlan él a `link` tábla feloldatlan céljai forrásonként
    egyszer (a cél kulcsa ugyanaz az NFC-s, vágott szöveg, mint a `/api/vault/graf` `feloldatlan` számlálójáé). A felület egyiket
    sem találja ki; a `/api/vault/graf` alakja változatlan."""
    cimkek: dict[str, list[str]] = {}
    tul: dict[str, dict[str, list[str]]] = {}
    felold: list[list[str]] = []
    csonkolt = False
    kiz = kizaras.betolt(getattr(index, "cfg", None))          # a kizárt jegyzet nem szerepel a gráf kiegészítő adataiban
    with index.olvaso(nehez=True) as c:
        for ut, cimke in c.execute(
                "SELECT f.ut, c.cimke FROM cimke c JOIN fajl f ON f.id = c.fajl_id "
                "WHERE f.torolve IS NULL ORDER BY f.id, c.rowid"):
            if kiz.kizart(ut):
                continue
            lista = cimkek.setdefault(ut, [])
            if cimke not in lista:
                lista.append(cimke)
        for ut, kulcs, ertek in c.execute(
                "SELECT f.ut, t.kulcs, t.ertek FROM tulajdonsag t JOIN fajl f ON f.id = t.fajl_id "
                "WHERE f.torolve IS NULL ORDER BY f.id, t.sorrend"):
            if kiz.kizart(ut):
                continue
            e = _ertekek(ertek)
            if e:
                tul.setdefault(ut, {})[kulcs] = e
        latott: set[tuple[str, str]] = set()
        for ut, nyers in c.execute(
                "SELECT f.ut, l.cel_nyers FROM link l JOIN fajl f ON f.id = l.forras_id "
                "WHERE f.torolve IS NULL AND l.cel IS NULL AND l.cel_nyers IS NOT NULL ORDER BY f.id, l.sorrend"):
            cel = nfc((nyers or "").strip())
            if not cel or (ut, cel) in latott or kiz.kizart(ut):
                continue
            if len(felold) >= MAX_FELOLDATLAN_EL:
                csonkolt = True
                break
            latott.add((ut, cel))
            felold.append([ut, cel])
    # a címke kis-nagybetűtől függetlenül egy csúcs (mint az Obsidianban): kulcs = kisbetűs, név = az első előfordulás írásmódja
    csucsok: dict[str, dict] = {}
    for lista in cimkek.values():
        for cimke in lista:
            nev = nfc(str(cimke)).strip().lstrip("#")
            if not nev or len(nev) > MAX_CIMKE_HOSSZ:
                continue
            e = csucsok.setdefault(nev.lower(), {"nev": nev, "db": 0})
            e["db"] += 1
    return {"cimkek": cimkek, "tulajdonsagok": tul, "cimke_csucsok": dict(sorted(csucsok.items())),
            "feloldatlan_elek": felold, "feloldatlan_csonkolt": csonkolt}


def graf_meta_valasz(index) -> tuple[bytes, str]:
    """A `/api/vault/graf-meta` válasza bájtokként és ETag-gel, a szerkezeti generáció szerint gyorsítótárazva (C33, T070)."""
    return index._gyorsitott("graf-meta", lambda: graf_meta(index))


def _hex(rgb) -> str | None:
    if isinstance(rgb, bool) or not isinstance(rgb, int) or not 0 <= rgb <= 0xFFFFFF:
        return None
    return f"#{rgb:06x}"


def _szam(v, alap=None):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else alap


def _logikai(v, alap):
    return v if isinstance(v, bool) else alap


def graf_beallitasok(vault) -> dict:
    """A vault `.obsidian/graph.json` fájljának olvasható kivonata. Ha nincs vagy hibás: `{"van": False}`.

    Csak olvas (a vaultio a rejtett szegmenseket nem adja ki, ezért a `tipusok_olvas` mintájára közvetlen az olvasás);
    a hibás vagy ismeretlen kulcsot kihagyja."""
    try:
        with open(os.path.join(os.fspath(vault), ".obsidian", "graph.json"), encoding="utf-8") as fh:
            j = json.load(fh)
    except (OSError, ValueError):
        return {"van": False}
    if not isinstance(j, dict):
        return {"van": False}
    csoportok = []
    for g in j.get("colorGroups") or []:
        if not isinstance(g, dict) or not isinstance(g.get("query"), str):
            continue
        szin = g.get("color") if isinstance(g.get("color"), dict) else {}
        h = _hex(szin.get("rgb"))
        if h is None:
            continue
        alfa = _szam(szin.get("a"), 1.0)
        csoportok.append({"lekerdezes": g["query"], "szin": h, "alfa": min(1.0, max(0.0, alfa))})
    erok = {}
    for kulcs, jkulcs in (("kozep", "centerStrength"), ("taszitas", "repelStrength"), ("rugo", "linkStrength"),
                          ("tavolsag", "linkDistance")):
        v = _szam(j.get(jkulcs))
        if v is not None:
            erok[kulcs] = v
    return {
        "van": True,
        "kereses": j["search"] if isinstance(j.get("search"), str) else "",
        "mutat_mellekletek": _logikai(j.get("showAttachments"), True),
        "mutat_arvak": _logikai(j.get("showOrphans"), True),
        "nyil": _logikai(j.get("showArrow"), False),
        "meret_szorzo": _szam(j.get("nodeSizeMultiplier"), 1.0),
        "vonal_szorzo": _szam(j.get("lineSizeMultiplier"), 1.0),
        "szoveg_halvanyitas": _szam(j.get("textFadeMultiplier"), 0.0),
        "mutat_cimkek": _logikai(j.get("showTags"), False),
        "csak_letezo": _logikai(j.get("hideUnresolved"), True),
        "erok": erok,
        "szincsoportok": csoportok,
    }
