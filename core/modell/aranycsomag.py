"""Aranyhalmazok a termékben (F6): a szállított csomag (`modulok/eval/csomag.toml`) és a felhasználó saját halmaza.

**Szállított halmaz**: a csomagban felsorolt eval-mappák (`kod`, `kiegeszites`, `matek*`), amelyek tételei a mappában élnek
(a mérés nem olvas `{vault}`-ot). A `lista(cfg)` a feladatmodulból számolja a verziót, a tételszámot, az állapotot.

**Saját halmaz** (a varázsló háttere; az audit §2.3): `{install}/eval-sajat/<feladat>/arany.json`, a kódfán kívül.
  1. `letrehoz(cfg, feladat, tetelek)`: a tételek validálva; a kijelölés-alapú feladatoknál (`kifejtes`, `osszefoglal_kijeloles`)
     a jegyzet szövege a vaultból **csak olvasva** fagyasztódik (`kijeloles_keszit.fagyaszt_tetel`). Állapot: `vazlat`.
  2. `jovahagy(cfg, feladat, tartott)`: tételenként „rendben / kiveszem” → `jovahagyott` (legalább `min_tetel` tétel kell).
  3. `valaszt(cfg, feladat, "sajat" | "szallitott")`: melyik halmaz számít a router aktuális verziójának (`halmaz.Verziok`).
A saját halmaz verziója `<feladat>-sajat-<lenyomat>` (a szállított modul `VERZIO`-ja — benne a prompt lenyomata — és a fájl
tartalma): a rajta mért sor „saját mérés”, csak helyben él, és a prompt vagy a halmaz változása után nem routol.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import importlib.util
import json
import os
import re
import sys
import tomllib
from pathlib import Path

from . import kuszob as K

SAJAT_FELADATOK = {
    # feladat → kötelező tétel-mezők (a `vart` és a kérés ezekből épül; a szállított feladat.py pontozója olvassa)
    "kiegeszites": ("elotte", "utana", "elfogadhato"),
    "kifejtes": ("ut", "kezd", "veg", "kulcs", "tema"),
    "osszefoglal_kijeloles": ("ut", "kezd", "veg", "kulcs"),
}
VAULTBOL = {"kifejtes", "osszefoglal_kijeloles"}
MAX_TETEL = 200
MAX_SZOVEG = 4000
AZON = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


class HalmazHiba(ValueError):
    def __init__(self, kod: str, uzenet: str, **param):
        super().__init__(uzenet)
        self.kod, self.param = kod, param


def _most() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _atomi(ut: Path, adat: dict) -> None:
    ut.parent.mkdir(parents=True, exist_ok=True)
    tmp = ut.with_name(f".{ut.name}.manifold-tmp")
    tmp.write_text(json.dumps(adat, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, ut)


# ---------------------------------------------------------------------- szállított csomag

def csomag(cfg) -> dict:
    p = Path(cfg.path("modulok")) / "eval" / "csomag.toml"
    try:
        with open(p, "rb") as f:
            return dict(tomllib.load(f).get("halmaz") or {})
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _modul(cfg, mappa: str, nev: str):
    ut = Path(cfg.path("modulok")) / "eval" / mappa / "feladat.py"
    if not ut.is_file():
        raise HalmazHiba("modell.halmaz_nincs", f"nincs ilyen aranyhalmaz-feladat: {mappa}", feladat=mappa)
    spec = importlib.util.spec_from_file_location(nev, ut)
    mod = importlib.util.module_from_spec(spec)
    elotte = list(sys.path)
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path[:] = elotte
    return mod


def _allapot(verzio: str) -> str:
    if verzio.endswith("-hianyzik"):
        return "hianyzik"
    return "vazlat" if verzio.endswith("-vazlat") else "jovahagyott"


def lista(cfg) -> list[dict]:
    """A szállított halmazok: `{feladat, router_feladat, verzio, allapot, tetelszam, nyelv, licenc, forras, min_tetel,
    kalibralhato, ellenorizni}`; a hibás modul `allapot: "hibas"`-t kap (a lista nem bukik el)."""
    ki = []
    for nev, h in sorted(csomag(cfg).items()):
        mappa = str(h.get("mappa") or nev)
        sor = {"feladat": mappa, "nyelv": h.get("nyelv"), "licenc": h.get("licenc"), "forras": h.get("forras"),
               "ellenorizni": h.get("ellenorizni") or None}
        try:
            mod = _modul(cfg, mappa, f"mos_csomag_{mappa}")
            router = str(getattr(mod, "ROUTER_FELADAT", mappa))
            n = sum(1 for _ in mod.tetelek(cfg))
            k = K.hatalyos(router)
            allapot = _allapot(str(mod.VERZIO))
            sor.update(router_feladat=router, verzio=str(mod.VERZIO), allapot=allapot, tetelszam=n,
                       min_tetel=k.min_tetel if k else None,
                       kalibralhato=bool(k and k.kuszob is not None and allapot == "jovahagyott" and n >= k.min_tetel))
        except Exception as e:  # noqa: BLE001 — a csomag egy hibás eleme ne vigye el a listát
            sor.update(router_feladat=mappa, verzio=None, allapot="hibas", tetelszam=0, min_tetel=None, kalibralhato=False,
                       hiba=f"{type(e).__name__}: {e}"[:300])
        ki.append(sor)
    return ki


# ---------------------------------------------------------------------- saját halmaz

def sajat_gyoker(cfg) -> Path:
    return Path(cfg.path("install")) / "eval-sajat"


def _sajat_ut(cfg, feladat: str) -> Path:
    if feladat not in SAJAT_FELADATOK:
        raise HalmazHiba("modell.sajat_nem_tamogatott", f"ehhez a feladathoz nincs saját halmaz: {feladat}", feladat=str(feladat)[:64])
    return sajat_gyoker(cfg) / feladat / "arany.json"


def sajat(cfg, feladat: str) -> dict | None:
    try:
        d = json.loads(_sajat_ut(cfg, feladat).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def _szoveg(x, mezo: str, i: int) -> str:
    if not isinstance(x, str) or len(x) > MAX_SZOVEG or "\x00" in x:
        raise HalmazHiba("modell.sajat_hibas_tetel", f"{i}. tétel: a(z) `{mezo}` szöveg (legfeljebb {MAX_SZOVEG} karakter)",
                         sor=i, mezo=mezo)
    return x


def _lista(x, mezo: str, i: int, csoport: bool) -> list:
    if not isinstance(x, list) or not x or len(x) > 50:
        raise HalmazHiba("modell.sajat_hibas_tetel", f"{i}. tétel: a(z) `{mezo}` nem üres lista", sor=i, mezo=mezo)
    if csoport:
        return [[_szoveg(s, mezo, i) for s in (c if isinstance(c, list) else [c])] for c in x]
    return [_szoveg(s, mezo, i) for s in x]


def _vault_ut(vault: Path, rel, i: int) -> str:
    if not isinstance(rel, str) or not rel.endswith(".md") or rel.startswith("/") or "\x00" in rel or \
            any(r in ("", ".", "..") for r in rel.split("/")):
        raise HalmazHiba("modell.sajat_hibas_tetel", f"{i}. tétel: az `ut` egy jegyzet munkatér-relatív útja", sor=i, mezo="ut")
    p = (vault / rel).resolve()
    try:
        p.relative_to(vault.resolve())
    except ValueError:
        raise HalmazHiba("modell.sajat_hibas_tetel", f"{i}. tétel: az út a munkatéren kívülre mutat", sor=i, mezo="ut") from None
    if not p.is_file():
        raise HalmazHiba("modell.sajat_hibas_tetel", f"{i}. tétel: a jegyzet nem található", sor=i, mezo="ut")
    return rel


def letrehoz(cfg, feladat: str, tetelek: list, nyelv: str = "hu") -> dict:
    """Új saját halmaz (vázlat). A meglévő vázlatot/halmazt felülírja (a régi `.elozo.json` néven megmarad)."""
    ut = _sajat_ut(cfg, feladat)
    if not isinstance(tetelek, list) or not tetelek or len(tetelek) > MAX_TETEL:
        raise HalmazHiba("modell.sajat_hibas_tetel", f"1–{MAX_TETEL} tétel kell", sor=0, mezo="tetelek")
    if not isinstance(nyelv, str) or not re.match(r"^[a-z]{2}$", nyelv):
        raise HalmazHiba("modell.sajat_hibas_tetel", "a nyelv kétbetűs kód", sor=0, mezo="nyelv")
    kell = SAJAT_FELADATOK[feladat]
    vault = Path(cfg.path("vault")) if feladat in VAULTBOL else None
    ki, idk = [], set()
    for i, t in enumerate(tetelek, 1):
        if not isinstance(t, dict):
            raise HalmazHiba("modell.sajat_hibas_tetel", f"{i}. tétel: objektum kell", sor=i, mezo="")
        hiany = [m for m in kell if m not in t]
        if hiany:
            raise HalmazHiba("modell.sajat_hibas_tetel", f"{i}. tétel: hiányzik: {', '.join(hiany)}", sor=i, mezo=hiany[0])
        tid = str(t.get("id") or f"s{i:03d}")
        if not AZON.match(tid) or tid in idk:
            raise HalmazHiba("modell.sajat_hibas_tetel", f"{i}. tétel: hibás vagy ismételt azonosító", sor=i, mezo="id")
        idk.add(tid)
        uj: dict = {"id": tid}
        if feladat == "kiegeszites":
            uj.update(elotte=_szoveg(t["elotte"], "elotte", i), utana=_szoveg(t["utana"], "utana", i),
                      elfogadhato=_lista(t["elfogadhato"], "elfogadhato", i, False))
        else:
            uj.update(ut=_vault_ut(vault, t["ut"], i), kezd=_szoveg(t["kezd"], "kezd", i), veg=_szoveg(t["veg"], "veg", i),
                      kulcs=_lista(t["kulcs"], "kulcs", i, True))
            if feladat == "kifejtes":
                uj["tema"] = _lista(t["tema"], "tema", i, True)
                if t.get("tiltott"):
                    uj["tiltott"] = _lista(t["tiltott"], "tiltott", i, False)
            uj = _fagyaszt(cfg, vault, uj, feladat == "kifejtes", i)
        ki.append(uj)
    regi = sajat(cfg, feladat)
    if regi is not None:
        _atomi(ut.with_name("arany.elozo.json"), regi)
    adat = {"verzio": "sajat", "allapot": "vazlat", "nyelv": nyelv, "keszult": _most(), "jovahagyva": None,
            "mero": "sajat", "tetel": ki}
    _atomi(ut, adat)
    return osszegzes(cfg, feladat)


def _fagyaszt(cfg, vault: Path, t: dict, kifejtes: bool, i: int) -> dict:
    """A jegyzet szövegéből a kijelölés és az előtte álló szöveg (csak olvas; `kijeloles_keszit` szabálya)."""
    elotte = list(sys.path)
    try:
        for p in (str(Path(cfg.path("modulok")) / "eval"), str(Path(cfg.path("modulok")).parent)):
            if p not in sys.path:
                sys.path.insert(0, p)
        spec = importlib.util.spec_from_file_location("mos_kijeloles_keszit",
                                                      Path(cfg.path("modulok")) / "eval" / "kijeloles_keszit.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        try:
            return mod.fagyaszt_tetel(vault, t, kifejtes)
        except (ValueError, UnicodeDecodeError) as e:
            raise HalmazHiba("modell.sajat_hibas_tetel", f"{i}. tétel: a kijelölés nem található a jegyzetben ({e})",
                             sor=i, mezo="kezd") from None
    finally:
        sys.path[:] = elotte


def jovahagy(cfg, feladat: str, tartott: list) -> dict:
    """Tételenkénti jóváhagyás: csak a `tartott` azonosítók maradnak; legalább `min_tetel` kell."""
    d = sajat(cfg, feladat)
    if d is None:
        raise HalmazHiba("modell.halmaz_nincs", "nincs saját halmaz ehhez a feladathoz", feladat=feladat)
    if not isinstance(tartott, list) or not all(isinstance(x, str) for x in tartott):
        raise HalmazHiba("modell.sajat_hibas_tetel", "a `tartott` azonosítók listája", sor=0, mezo="tartott")
    marad = [t for t in d["tetel"] if t["id"] in set(tartott)]
    k = K.hatalyos(feladat)
    if k is None or len(marad) < k.min_tetel:
        raise HalmazHiba("modell.keves_tetel", f"legalább {k.min_tetel if k else '?'} tétel kell",
                         feladat=feladat, n=len(marad), min_tetel=k.min_tetel if k else None)
    _atomi(_sajat_ut(cfg, feladat), {**d, "tetel": marad, "allapot": "jovahagyott", "jovahagyva": _most()})
    return osszegzes(cfg, feladat)


def torol(cfg, feladat: str) -> dict:
    """A saját halmaz nem törlődik véglegesen: `eval-sajat/.torolt/<feladat>-<idő>/` alá kerül; a választás visszaáll."""
    ut = _sajat_ut(cfg, feladat)
    if not ut.parent.is_dir():
        raise HalmazHiba("modell.halmaz_nincs", "nincs saját halmaz ehhez a feladathoz", feladat=feladat)
    cel = sajat_gyoker(cfg) / ".torolt" / f"{feladat}-{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    cel.parent.mkdir(parents=True, exist_ok=True)
    os.replace(ut.parent, cel)
    v = valasztasok(cfg)
    if v.pop(feladat, None) is not None:
        _atomi(sajat_gyoker(cfg) / "valasztas.json", v)
    return {"feladat": feladat, "torolve": True}


def valasztasok(cfg) -> dict:
    return valasztasok_gyokerbol(sajat_gyoker(cfg))


def valasztasok_gyokerbol(gyoker: Path) -> dict:
    try:
        d = json.loads((Path(gyoker) / "valasztas.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in d.items() if isinstance(k, str) and v == "sajat"} if isinstance(d, dict) else {}


def valaszt(cfg, feladat: str, mi: str) -> dict:
    if mi not in ("sajat", "szallitott"):
        raise HalmazHiba("modell.sajat_hibas_tetel", "a választás: sajat | szallitott", sor=0, mezo="halmaz")
    _sajat_ut(cfg, feladat)
    v = valasztasok(cfg)
    if mi == "sajat":
        d = sajat(cfg, feladat)
        if not d or d.get("allapot") != "jovahagyott":
            raise HalmazHiba("modell.halmaz_vazlat", "előbb hagyd jóvá a saját halmazt", feladat=feladat)
        v[feladat] = "sajat"
    else:
        v.pop(feladat, None)
    _atomi(sajat_gyoker(cfg) / "valasztas.json", v)
    return osszegzes(cfg, feladat)


def sajat_verzio(alap_verzio: str, feladat: str, fajl: Path) -> str | None:
    """`<feladat>-sajat-<lenyomat>[-vazlat]` (a szállított modul verziója + a fájl tartalma); nincs fájl: None."""
    try:
        nyers = Path(fajl).read_bytes()
        d = json.loads(nyers)
    except (OSError, ValueError):
        return None
    ny = hashlib.sha256(alap_verzio.encode("utf-8") + b"\0" + nyers).hexdigest()[:10]
    return f"{feladat}-sajat-{ny}" + ("" if d.get("allapot") == "jovahagyott" else "-vazlat")


def sajat_modul(cfg, feladat: str):
    """A szállított feladatmodul a saját tételekkel: `ARANY` és `VERZIO` cserélve, `MERO = "sajat"`."""
    d = sajat(cfg, feladat)
    if d is None:
        raise HalmazHiba("modell.halmaz_nincs", "nincs saját halmaz ehhez a feladathoz", feladat=feladat)
    mod = _modul(cfg, feladat, f"mos_eval_sajat_{feladat}")
    mod.ARANY = d
    mod.VERZIO = sajat_verzio(str(mod.VERZIO), feladat, _sajat_ut(cfg, feladat))
    mod.MERO = "sajat"
    return mod


def osszegzes(cfg, feladat: str) -> dict:
    d = sajat(cfg, feladat)
    k = K.hatalyos(feladat)
    return {"feladat": feladat, "van": d is not None, "allapot": d.get("allapot") if d else None,
            "tetelszam": len(d.get("tetel") or []) if d else 0, "nyelv": d.get("nyelv") if d else None,
            "min_tetel": k.min_tetel if k else None, "valasztva": valasztasok(cfg).get(feladat) == "sajat",
            "tetelek": [{"id": t["id"], **({"ut": t["ut"]} if "ut" in t else {})} for t in (d.get("tetel") or [])] if d else []}
