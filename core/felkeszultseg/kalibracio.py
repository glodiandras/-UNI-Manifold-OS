"""Önkalibráció: a felkészültségi képlet súlyainak illesztése a valódi dolgozat-eredményekre (C28b; `docs/C28-TERV.md` 7.).

**Kalibrációs pont** = egy lezárt dolgozat, amelyhez (1) van egyértelmű, számszerű eredmény a „Dolgozat kiértékelő” jegyzetben
(`eredmeny.py`), és (2) a `D−N`. nap végére (alap: `D−3`) **rekonstruált** becslésben (`rekonstrukcio.py`, `Adatok(rekonstrukcio=True)`)
van mért tudás (kártya vagy kvíz: legalább egy témára van szám). A becslés a **kilátás** (a dolgozat napjára, további tanulás
nélkül) — az a szám, amelyet a dolgozat előtt a felhasználó látott.

**Az illesztés** (szándékosan szerény, kis mintára): legfeljebb **3 szabad súly** — kártya, kvíz és a „proxi” (frissesség + idő,
a két induló súly arányában együtt mozog); az összeg az induló összeggel egyenlő (a képlet skála-invariáns, `min_bizonyitek`
viszont abszolút), és a proxik együttes súlya legfeljebb a mért összetevőké (a C28a korlátja: `wP ≤ wK + wQ`). A keresés **rács**
(1/40-es lépés, deterministikus, a `min_bizonyitek` küszöb szakadását is kezeli), a célfüggvény `MSE + λ·‖w − w₀‖²` (ridge az induló
súlyok felé, `kalibracio_ridge`). A hiba **leave-one-out** (minden pontot az összes többin illesztett súllyal becsül), és az
induló súlyok hibájához mérjük; **javítás csak akkor javasolt**, ha `n ≥ kalibracio_min` (8) **és** a LOO-RMSE legalább
`JAVULAS_MIN`-nel kisebb az induló súlyokénál. `n < 8` → a súlyok nem változnak (a mérés ettől még elvégezhető, és az induló
súlyok hibáját jelenti, kis mintára jelzéssel).

A modul tiszta számolás (adat be, eredmény ki); az egyetlen író függvénye a `config_ir` (az `os.toml` `[felkeszultseg]` szakasza, a
`bin/mos felkeszultseg kalibral --rogzit` hívja — a core és a felület soha).
"""
from __future__ import annotations

import json
import math
import os
import re
import tomllib
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from pathlib import Path

from . import keplet, osszesit
from .adat import Adatok, Hiany

OSZTO = 40                      # a rács lépése: ossz/40
JAVULAS_MIN = 0.005             # a LOO-RMSE ennyivel (0–1 skálán) legyen kisebb az induló súlyokénál
KIS_MINTA = 8                   # ennél kevesebb pontra a hiba csak tájékoztató
SULY_KULCSOK = ("suly_kartya", "suly_kviz", "suly_frissesseg", "suly_ido")


@dataclass(frozen=True)
class Pont:
    azon: str
    cim: str
    nap: str                                   # a dolgozat napja
    y: float                                   # a tényleges eredmény, 0–1
    eredmeny_forras: str
    jegyzet: str                               # a kiértékelő jegyzet
    becsles_ideje: str                         # a rekonstrukció időpontja (ISO)
    jelek: tuple[keplet.TemaJel, ...]          # a témák bemenete a becslés időpontjában (a kilátás időpontjára)


# ------------------------------------------------------------------ pontok gyűjtése

def becsles(jelek, b: keplet.Beallitas) -> float | None:
    """A dolgozat száma a témajelekből a `b` súlyaival (a kilátás számolásának szabálya: `keplet`)."""
    szam, _, _ = keplet.dolgozat_szam([keplet.tema_szam(j, b).szam for j in jelek])
    return szam


def _ekkor(d: dict, tz, elotte_nap: int) -> datetime:
    """A rekonstrukció időpontja: a dolgozat napja előtti `elotte_nap`. nap **vége** (a napi tracker-összeg nem bontható szét)."""
    nap = date.fromisoformat(d["nap"]) - timedelta(days=elotte_nap)
    return datetime.combine(nap, time(23, 59, 59), tzinfo=tz)


def pontok_gyujt(most: Adatok) -> tuple[list[Pont], list[dict]]:
    """A kalibrációs pontok és a kihagyott lezárt dolgozatok (okkal). A `most` egy `visszamenoleg_nap`-os, olvasóval ellátott
    `Adatok`; minden pontnak külön, rekonstruált `Adatok` készül. Csak olvas."""
    m = most.m
    pontok: list[Pont] = []
    kihagyott: list[dict] = []

    def kihagy(d: dict, ok: str) -> None:
        kihagyott.append({"azon": d["azon"], "cim": d["cim"], "nap": d["nap"], "ok": ok})

    for d in most.dolgozatok():
        if not d["lezart"]:
            continue
        k = d["kotes"]
        if k is None:
            kihagy(d, "nincs felkészülési jegyzet")
            continue
        e = most.eredmenyek().get(k.jegyzet)
        if e is None:
            kihagy(d, "nincs eredmény a kiértékelő jegyzetekben")
            continue
        if not e["eredmeny"]:
            if e["ellentmondas"] and e.get("eredet") == "mezo":
                kihagy(d, "hibás „Eredmény::” mező a kiértékelőben: " + e["ellentmondas"]["ok"])
            else:
                kihagy(d, "ellentmondó eredmény a kiértékelőben" if e["ellentmondas"] else "nincs egyértelmű eredmény")
            continue
        ekkor = _ekkor(d, most.most.tzinfo, m.kalibracio_elotte_nap)
        if ekkor >= most.most:
            kihagy(d, "a rekonstrukció időpontja még nem telt el")
            continue
        rek = Adatok(most.cfg, most.index, ekkor, olvas=most.olvas, rekonstrukcio=True)
        try:
            dd = next((x for x in rek.dolgozatok() if x["azon"] == d["azon"]), None)
        except Hiany as ex:
            kihagy(d, str(ex))
            continue
        if dd is None or dd["kotes"] is None:
            kihagy(d, "a dolgozat a rekonstruált időpontban nem kötődött felkészülési jegyzethez")
            continue
        rek.forrasok_betolt()
        temak = rek.temak(dd["kotes"].jegyzet).temak
        if not temak:
            kihagy(d, "nincs téma")
            continue
        nap = date.fromisoformat(dd["nap"])
        tau = osszesit._tau(dd, rek.most)
        jelek = tuple(rek.tema_jel(ut, nap, tau)[0] for ut in temak)
        if becsles(jelek, rek.b) is None:
            kihagy(d, f"nincs mért tudás (kártya, kvíz) a D−{m.kalibracio_elotte_nap}. napon")
            continue
        r = e["eredmeny"]
        pontok.append(Pont(d["azon"], d["cim"], d["nap"], r["szazalek"] / 100.0, r["forras"], e["fajl"], ekkor.isoformat(), jelek))
    pontok.sort(key=lambda p: (p.nap, p.azon))
    return pontok, kihagyott


# ------------------------------------------------------------------ illesztés

def _suly_beallitas(b0: keplet.Beallitas, wk: float, wq: float, wp: float) -> keplet.Beallitas:
    resz = b0.suly_frissesseg / (b0.suly_frissesseg + b0.suly_ido) if (b0.suly_frissesseg + b0.suly_ido) > 0 else 0.5
    return replace(b0, suly_kartya=wk, suly_kviz=wq, suly_frissesseg=wp * resz, suly_ido=wp * (1 - resz))


def _racs(b0: keplet.Beallitas) -> list[tuple[float, float, float]]:
    ossz = b0.suly_kartya + b0.suly_kviz + b0.suly_frissesseg + b0.suly_ido
    w0 = (b0.suly_kartya, b0.suly_kviz, b0.suly_frissesseg + b0.suly_ido)
    ki = []
    for i in range(2, OSZTO):
        for j in range(2, OSZTO):
            k = OSZTO - i - j
            if 2 <= k <= OSZTO // 2:
                ki.append(tuple(round(ossz * x / OSZTO, 6) for x in (i, j, k)))
    if not any(all(abs(a - b) < 1e-9 for a, b in zip(g, w0)) for g in ki):
        ki.append(w0)
    return ki


def _tavolsag2(g, w0) -> float:
    return sum((a - b) ** 2 for a, b in zip(g, w0))


def _rmse(hibak: list[float]) -> float | None:
    return math.sqrt(sum(h * h for h in hibak) / len(hibak)) if hibak else None


def _mae(hibak: list[float]) -> float | None:
    return sum(abs(h) for h in hibak) / len(hibak) if hibak else None


def _stat(hibak: list[float]) -> dict:
    n = len(hibak)
    return {"n": n, "rmse": None if not n else round(_rmse(hibak), 4), "mae": None if not n else round(_mae(hibak), 4),
            "torzitas": None if not n else round(sum(hibak) / n, 4)}


def illeszt(pontok: list[Pont], b0: keplet.Beallitas, ridge: float, minimum: int) -> dict:
    """A súlyillesztés a pontokra → a kalibráció jelentése (`allapot`, hibák, javasolt súlyok). Tiszta függvény."""
    n = len(pontok)
    ossz = b0.suly_kartya + b0.suly_kviz + b0.suly_frissesseg + b0.suly_ido
    w0 = (b0.suly_kartya, b0.suly_kviz, b0.suly_frissesseg + b0.suly_ido)
    ki: dict = {"pontok": n, "kell": minimum, "kis_minta": n < KIS_MINTA,
                "alap": {"suly": {k: getattr(b0, k) for k in SULY_KULCSOK}}}
    if n == 0:
        ki.update(allapot="nem_teljesitheto", alap={**ki["alap"], **_stat([])}, loo=_stat([]), pontok_reszlet=[])
        return ki
    racs = _racs(b0)
    y = [p.y for p in pontok]
    bg = [_suly_beallitas(b0, *g) for g in racs]
    # P[g][p]: a becslés; hiányzó szám → a legnagyobb hiba (1,0) — az a súlyozás nem használható
    P = [[becsles(p.jelek, b) for p in pontok] for b in bg]
    E = [[(1.0 if P[g][i] is None else P[g][i] - y[i]) for i in range(n)] for g in range(len(racs))]
    E2 = [[x * x for x in sor] for sor in E]
    d2 = [_tavolsag2(g, w0) for g in racs]
    # az induló súlyok hibája: közvetlenül a `b0`-val (hiányzó szám → 1,0 hiba, mint a rácson)
    alap_becsles = [becsles(p.jelek, b0) for p in pontok]
    alap_hibak = [1.0 if v is None else v - p.y for v, p in zip(alap_becsles, pontok)]

    def legjobb(kihagy: int | None) -> int:
        db = n - (1 if kihagy is not None else 0)
        def j(g: int) -> tuple[float, float, int]:
            s = sum(E2[g]) - (E2[g][kihagy] if kihagy is not None else 0.0)
            return (s / db + ridge * d2[g], d2[g], g)
        return min(range(len(racs)), key=j)

    gall = legjobb(None)
    loo_hibak = []
    reszlet = []
    for i, p in enumerate(pontok):
        g = legjobb(i) if n > 1 else None             # egyetlen pontnál nincs mire illeszteni: a LOO az induló súly
        loo_becsles = alap_becsles[i] if g is None else P[g][i]
        loo_hibak.append(alap_hibak[i] if g is None else E[g][i])
        reszlet.append({"azon": p.azon, "cim": p.cim, "nap": p.nap, "eredmeny": round(p.y, 4), "forras": p.eredmeny_forras,
                        "becsles": None if alap_becsles[i] is None else round(alap_becsles[i], 4),
                        "hiba": round(alap_hibak[i], 4), "loo_becsles": None if loo_becsles is None else round(loo_becsles, 4),
                        "becsles_ideje": p.becsles_ideje})
    illesztett_suly = {k: round(getattr(bg[gall], k), 4) for k in SULY_KULCSOK}
    ki.update(alap={**ki["alap"], **_stat(alap_hibak)}, loo=_stat(loo_hibak), pontok_reszlet=reszlet, osszeg=round(ossz, 4))
    if n >= minimum:                       # kevés pontra illesztett súlyt nem adunk ki: a súlyok nem változnak (kalibracio_min)
        ki["illesztett"] = {"suly": illesztett_suly, **_stat(E[gall])}
    alap_r, loo_r = _rmse(alap_hibak), _rmse(loo_hibak)
    ki["javulas"] = None if alap_r is None or loo_r is None else round(alap_r - loo_r, 4)
    if n < minimum:
        ki["allapot"] = "nem_teljesitheto"
    elif ki["javulas"] is not None and ki["javulas"] >= JAVULAS_MIN:
        ki["allapot"] = "javasolt"
    else:
        ki["allapot"] = "nincs_javulas"
    return ki


# ------------------------------------------------------------------ a jelentés

def _ok(allapot: str, n: int, minimum: int, lezart: int, eredmennyel: int, kihagyott: list[dict], elotte: int) -> str:
    if allapot == "nem_teljesitheto":
        if lezart == 0:
            return ("Még nincs lezárt dolgozat a naptárban az ablakon belül, így nincs mit mérni. A kalibrációhoz legalább "
                    f"{minimum} lezárt dolgozat kell, amelyhez van számszerű eredmény a „Dolgozat kiértékelő” jegyzetben, és a "
                    f"D−{elotte}. napon volt mért tudás (kártya vagy kvíz).")
        mert_hiany = sum(1 for k in kihagyott if k["ok"].startswith("nincs mért tudás"))
        return (f"A kalibráció még nem teljesíthető: {n} / {minimum} dolgozatra van egyszerre számszerű eredmény és mért tudás "
                f"(kártya vagy kvíz) a D−{elotte}. napon. {lezart} lezárt dolgozatból {eredmennyel}-nek van eredménye, ebből "
                f"{mert_hiany} dolgozatnál hiányzott a mért tudás — a becslés csak a kártyák és a kvíz használatától számol, a "
                "régi dolgozatokra visszamenőleg nem pótolható. A súlyok addig az induló értékek.")
    if allapot == "nincs_javulas":
        return (f"{n} dolgozaton mérve az illesztett súlyok nem becsülnek jobban az induló súlyoknál (leave-one-out hiba), "
                "ezért a súlyok nem változnak.")
    return f"{n} dolgozaton mérve az illesztett súlyok jobban becsülnek az induló súlyoknál (leave-one-out hiba): a súlyok alkalmazhatók."


def jelentes(most: Adatok) -> dict:
    """A kalibráció teljes jelentése (a `GET /api/felkeszultseg/kalibracio` és a CLI válasza): állapot, ok magyarul, pontok, hibák,
    javasolt súlyok. Csak olvas; a súlyokat **nem** írja (az a `config_ir`, a CLI `--rogzit`)."""
    m = most.m
    ki: dict = {"kalibralt": most.b.kalibralt, "elotte_nap": m.kalibracio_elotte_nap, "kell": m.kalibracio_min,
                "suly": {k: getattr(most.b, k) for k in SULY_KULCSOK}}
    try:
        pontok, kihagyott = pontok_gyujt(most)
    except Hiany as e:
        ki.update(allapot="nem_teljesitheto", pontok=0, lezart=0, eredmennyel=0, kihagyott=[], ok=str(e), hiba=str(e),
                  kis_minta=True, alap=_stat([]), loo=_stat([]), pontok_reszlet=[])
        return ki
    lezart = sum(1 for d in most.dolgozatok() if d["lezart"])
    eredmennyel = len(pontok) + sum(1 for k in kihagyott if k["ok"].startswith("nincs mért tudás"))
    ill = illeszt(pontok, most.b, m.kalibracio_ridge, m.kalibracio_min)
    ki.update(ill)
    ki.update(lezart=lezart, eredmennyel=eredmennyel, kihagyott=kihagyott,
              ok=_ok(ill["allapot"], len(pontok), m.kalibracio_min, lezart, eredmennyel, kihagyott, m.kalibracio_elotte_nap))
    ki["figyelmeztetesek"] = most.figyelmeztetesek
    return ki


def jelentes_adatbol(cfg, index, olvas, most: datetime | None = None) -> dict:
    """A jelentés egy kéréshez: a visszamenőleges, olvasóval ellátott `Adatok` felépítése és a `jelentes`."""
    alap = Adatok(cfg, index, most, olvas=olvas)
    a = Adatok(cfg, index, most, olvas=olvas, visszamenoleg_nap=alap.m.kalibracio_vissza_nap)
    return jelentes(a)


# ------------------------------------------------------------------ az os.toml írása (csak a CLI hívja)

def toml_felulir(szoveg: str, szakasz: str, ertekek: dict[str, object]) -> str:
    """A `[szakasz]` megadott kulcsainak értéke a TOML-szövegben: a meglévő sor értéke cserélődik (a sorvégi megjegyzés marad),
    a hiányzó kulcs a szakasz végére kerül. A többi bájt változatlan."""
    sorok = szoveg.split("\n")
    kezd = next((i for i, s in enumerate(sorok) if s.strip() == f"[{szakasz}]"), None)
    if kezd is None:
        raise ValueError(f"nincs [{szakasz}] szakasz")
    veg = next((i for i in range(kezd + 1, len(sorok)) if re.match(r"^\s*\[", sorok[i])), len(sorok))

    def ertek_szoveg(v: object) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, float):
            return repr(round(v, 4))
        return json.dumps(v, ensure_ascii=False)

    for kulcs, v in ertekek.items():
        minta = re.compile(rf"^(\s*{re.escape(kulcs)}\s*=\s*)([^#\n]*?)(\s*(?:#.*)?)$")
        for i in range(kezd + 1, veg):
            m = minta.match(sorok[i])
            if m:
                sorok[i] = f"{m.group(1)}{ertek_szoveg(v)}{m.group(3) if m.group(3).strip() else ''}"
                break
        else:
            hely = veg
            while hely > kezd + 1 and not sorok[hely - 1].strip():
                hely -= 1
            sorok.insert(hely, f"{kulcs} = {ertek_szoveg(v)}")
            veg += 1
    return "\n".join(sorok)


def config_ir(cfg, jelentes_: dict, mikor: datetime | None = None) -> dict:
    """A javasolt súlyok és a `kalibralt = true` az `os.toml` `[felkeszultseg]` szakaszába, atomi cserével (a TOML újraolvasása
    ellenőrzi), és egy sor a `{state}/felkeszultseg-kalibracio.jsonl` naplóba (mi, mikor, mekkora hibával). Csak `javasolt`
    állapotra; a futó core a következő indulásakor olvassa újra a konfigurációt."""
    if jelentes_.get("allapot") != "javasolt":
        raise ValueError(f"a súlyok nem alkalmazhatók ({jelentes_.get('allapot')}): {jelentes_.get('ok')}")
    forras = getattr(cfg, "source", None)
    if not forras or not Path(forras).is_file():
        raise ValueError("a konfigurációs fájl helye ismeretlen")
    forras = Path(forras)
    regi = forras.read_text(encoding="utf-8")
    suly = jelentes_["illesztett"]["suly"]
    uj = toml_felulir(regi, "felkeszultseg", {**suly, "kalibralt": True, "kalibracio_n": int(jelentes_["pontok"])})
    tomllib.loads(uj)                                           # érvényes TOML marad
    tmp = forras.with_name(f".{forras.name}.{os.getpid()}.manifold-tmp")
    tmp.write_text(uj, encoding="utf-8")
    os.replace(tmp, forras)
    mikor = mikor or datetime.now().astimezone()
    napl = Path(cfg.path("state")) / "felkeszultseg-kalibracio.jsonl"
    napl.parent.mkdir(parents=True, exist_ok=True)
    with napl.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"mikor": mikor.isoformat(timespec="seconds"), "pontok": jelentes_["pontok"], "regi": jelentes_["alap"]["suly"],
                            "uj": suly, "alap_rmse": jelentes_["alap"]["rmse"], "loo_rmse": jelentes_["loo"]["rmse"],
                            "javulas": jelentes_["javulas"]}, ensure_ascii=False) + "\n")
    return {"fajl": str(forras), "naplo": str(napl), "suly": suly}
