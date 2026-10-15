"""A ```plot automatikus módja (C35b-mag, C35b; CLAUDE.md 2., 3., 5., 59. döntés, D8): mikor és melyik jegyzet kap blokkot.

**A döntés a közös ütemezőé** (`core/automatika.py`, C23b/K309): a `grafikon` fogyasztó (`fogyaszto(cfg)`) a közös mértéket kapja
(10 perc csend, új / erősen módosult jegyzet, `mar_kesz`), két saját kampóval: `van_keplet` (a képlet nélküli jegyzet „nem kell”,
elbírált) és `uj_keplet` (az „új képlet” ok: egyetlen új `$$…$$` egy hosszú jegyzetben nem éri el a mondathalmaz-küszöböt; az
utoljára feldolgozott változat képletkulcsai a közös tár `adat` mezőjében). Másolat nincs: a mondathalmaz, a távolság, az ujjlenyomat
a `core/automatika.py`-é. Az ütemező a jelölt útjait `{"utak": […]}` paraméterrel küldi a `grafikon_automatikus` feladatnak.

**A futás** (`futas`) a megkapott jegyzeteket a `Beiro`-n, azaz a gépi-írás szolgáltatáson át dolgozza fel (28. döntés), a feladatsor
`TaskType(automatikus=True)` lépéseként (`core/grafikon_feladat.py`), a memóriaőr (`Kapu.admit`) alatt; tételhatáron áll meg
(stop-fájl). Feldolgozottnak (`Tar.kesz`) csak az számít, amit nem kell újrapróbálni: a nyitott dokumentum miatt elhalasztott, az
ütközött és a modellre váró (`fuggoben`) jegyzet nem; a próbamód (D9) a tárhoz nem nyúl. Kézzel (`utak` nélkül) a futás a vaultot
bejárja és ugyanazt a döntést hívja (`jeloltek`).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, fields
from pathlib import Path

from . import jegyzet as J
from . import tiltolista as T


def _kozos():
    """A közös ütemező (C23b: `core/automatika.py`; lusta import: a repo gyökere a `sys.path`-on kell legyen — a CLI és a
    feladatsor ezt adja)."""
    from core import automatika as OA
    return OA


FOGYASZTO = "grafikon"
FELADATTIPUS = "grafikon_automatikus"      # 80(a): a kézi `grafikon_beiras` nem automatikus; ez csak a `be = true` ütemezőé


@dataclass(frozen=True)
class Beallitas:
    """A `[grafikon.automatika]` szakasz."""
    be: bool = False              # 80(a): az automatikus fogyasztó regisztrálása (core/automatika.py); alapból hamis — a beírás csak gombra
    csend_perc: int = 10          # ennyi perce nem változhatott a jegyzet
    kuszob: float = 0.3           # „erősen módosult”: a közös hosszal súlyozott mondathalmaz-Jaccard-távolság
    min_hossz: int = 40           # a jegyzet tisztított mondatai legalább ennyi karakter (a képletes jegyzet rövid is lehet)
    uj_karakter: int = 600        # ennyi karakternyi új mondat már önmagában „erős” módosulás
    max_jegyzet: int = 5          # egy feladatban (köteg) legfeljebb ennyi jegyzet
    varakozas_mp: float = 5.0     # egy nyitott (mentetlen) jegyzetre ennyit vár a gépi írás, utána elhalasztja
    modell_ag: bool = False       # a modell-ág ÉLES írása (az éles blokk-író prompt mérése és a 0 téves blokk igazolása előtt: hamis)
    ujraproba_ora: float = 1.0    # a feldolgozatlanul maradt (pl. modellre váró) jegyzet ennyi óra után újra sorra kerül


_MEZOK = {f.name for f in fields(Beallitas)}


def beallitas(cfg) -> Beallitas:
    adat = dict(cfg.section("grafikon", "automatika"))
    ismeretlen = sorted(set(adat) - _MEZOK)
    if ismeretlen:
        raise ValueError(f"[grafikon.automatika]: ismeretlen kulcs: {', '.join(ismeretlen)}")
    return Beallitas(**adat)


def kepletkulcsok(md: str) -> frozenset[str]:
    """A jegyzet felismerendő képleteinek kulcsai (SymPy nélkül)."""
    return frozenset(T.kulcs_szoveg(k) for _, k in J.jeloltek(md or ""))


def van_keplet(md: str) -> bool:
    return bool(kepletkulcsok(md))


def uj_keplet(md: str, sor: dict) -> str | None:
    """A közös mérték kiegészítője: `"uj_keplet"`, ha a jegyzetben olyan képlet áll, amely az utoljára feldolgozott változatban nem
    (a feldolgozott változat képletkulcsai a tár `adat` mezőjében); különben `None`. Adat nélküli (átvett) sornál `None`."""
    try:
        adat = json.loads((sor or {}).get("adat") or "")
        regi = frozenset(adat["kepletek"])
    except (ValueError, KeyError, TypeError):
        return None
    return "uj_keplet" if kepletkulcsok(md) - regi else None


def adat(md: str) -> dict:
    """A `Tar.kesz` `adat` mezője a feldolgozott változatról."""
    return {"kepletek": sorted(kepletkulcsok(md))}


def fogyaszto(cfg, b: Beallitas | None = None):
    """A közös ütemező `grafikon` fogyasztója (a `core.automatika.alap_fogyasztok` hívja)."""
    OA, b = _kozos(), b or beallitas(cfg)
    return OA.Fogyaszto(FOGYASZTO, FELADATTIPUS, szuro=OA.tartalmi_ut, kuszob=b.kuszob, uj_karakter=b.uj_karakter,
                        csend_perc=b.csend_perc, min_hossz=b.min_hossz, koteg=b.max_jegyzet, ujraproba_ora=b.ujraproba_ora,
                        tartalom_szuro=van_keplet, kiegeszito=uj_keplet)


# ------------------------------------------------------------------ a futás (olvas; az írás a Beiro-n át)

KIZART_MAPPA = (".", "ATTCHMNTS - ")


def jegyzetek(vault: Path):
    """A vault tartalmi `.md` jegyzetei `(vault-relatív út, fájl)` — rejtett és `ATTCHMNTS - …` mappák nélkül; csak olvas."""
    OA = _kozos()
    for d, mappak, fajlok in os.walk(vault):
        mappak[:] = sorted(m for m in mappak if not m.startswith(KIZART_MAPPA))
        for f in sorted(fajlok):
            p = Path(d) / f
            rp = p.relative_to(vault).as_posix()
            if f.lower().endswith(".md") and OA.tartalmi_ut(rp):
                yield rp, p


def jeloltek(cfg, tar, ido=time.time, kapcsolo_be: bool = True, beall: Beallitas | None = None) -> dict:
    """Kézi mód (`utak` nélkül): a vault bejárása és a **közös** döntés (`core.automatika.dont`) a tár soraival. Csak olvas.
    → `{dontesek: [{ut, ok}], szamlalo: {állapot: darab}}` (a `dontesek` a feldolgozandók, régebben módosult elöl)."""
    OA, beall = _kozos(), beall or beallitas(cfg)
    ered = {"dontesek": [], "szamlalo": {}}
    if not kapcsolo_be:
        ered["szamlalo"]["kapcsolo_ki"] = 1
        return ered
    f, vault, most, sorok = fogyaszto(cfg, beall), Path(cfg.path("vault")), ido(), tar.sorok(FOGYASZTO)
    lista = []
    for rp, p in jegyzetek(vault):
        try:
            mt = p.stat().st_mtime
            hash_ = hashlib.sha1(p.read_bytes()).hexdigest()
        except OSError:
            ered["szamlalo"]["nem_olvashato"] = ered["szamlalo"].get("nem_olvashato", 0) + 1
            continue
        st, j = OA.dont(f, rp, hash_, mt, most, sorok.get(rp), lambda u: (vault / u).read_bytes().decode("utf-8"))
        ered["szamlalo"][st] = ered["szamlalo"].get(st, 0) + 1
        if j is not None:
            lista.append((mt, rp, j.ok))
    for _, rp, ok in sorted(lista):
        ered["dontesek"].append({"ut": rp, "ok": ok})
    return ered


def futas(cfg, beiro, tar, utak: list[str], szaraz: bool = False, proba: bool = False, stop_fajl: str | None = None,
          max_jegyzet: int | None = None, log=lambda s: None) -> dict:
    """A megadott jegyzetek feldolgozása: `beiro.jegyzet(ut)` jegyzetenként (legfeljebb `max_jegyzet`). Feldolgozottnak a tárban
    (`Tar.kesz`) csak az számít, aminek az állapota `kesz` / `nincs_teendo` / `nincs_jegyzet` / `elutasitva`, és nem marad
    modellre váró (`fuggoben`) képlete; `proba` és `szaraz` mellett a tárhoz nem nyúl. → összesítés (`jegyzetek`, `megallt`)."""
    beall = beallitas(cfg)
    max_jegyzet = beall.max_jegyzet if max_jegyzet is None else max_jegyzet
    ered = {"jegyzetek": [], "megallt": None}
    if szaraz:
        return ered
    for rp in utak[:max_jegyzet]:
        if stop_fajl and os.path.exists(stop_fajl):
            ered["megallt"] = "stop"
            break
        r = beiro.jegyzet(rp)
        ered["jegyzetek"].append({"ut": rp, "allapot": r["allapot"], "beirt": len(r.get("beirt", [])),
                                  "fuggoben": r.get("fuggoben", 0), "ok": r.get("ok", "")})
        log(f"{rp}: {r['allapot']} ({len(r.get('beirt', []))} blokk" + (f", {r['fuggoben']} modellre vár" if r.get("fuggoben") else "") + ")")
        if r["allapot"] == "nem_ellenorizheto":
            ered["megallt"] = "homokozo"                 # a CAS-homokozó nem érhető el: nem próbálkozunk tovább
            break
        if proba or r["allapot"] not in ("kesz", "nincs_teendo", "nincs_jegyzet", "elutasitva") or r.get("fuggoben"):
            continue
        if r.get("tartalom") is not None:
            tar.kesz(FOGYASZTO, rp, r["tartalom"], hash_=r.get("hash_utan"), adat=adat(r["tartalom"]))
    return ered
