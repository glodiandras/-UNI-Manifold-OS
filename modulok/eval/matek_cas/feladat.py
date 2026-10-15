"""Aranyhalmaz: matek-megoldás a CAS-úton (C24a váz; 2. audit T060) — a `matek` 40 feladata.

A modell rövid tervet ír, utána egy ```` ```python ```` blokkot SymPy-kóddal, amely a végeredményt az `EREDMENY`
változóba teszi. A pontozó az utolsó kódblokkot a **CAS-homokozóban** futtatja (`modulok/homokozo`: sandbox-exec,
idő- és memóriakorlát), az eredmény JSON-alakjából a megbízható folyamatban szöveges választ épít, és a `matek`
pontozójával (`kozos.matek.ekvivalens`, fehérlistás elemzés) veti össze. A modell kódja a pontozó folyamatában
soha nem fut.

Mit nem lát: a terv minőségét, és ha a kód jó eredményt rossz úton ad. A tiltott importot, az időtúllépést és a
homokozó-hibát rossz válasznak veszi (a jelentésben külön számolva).

Router: `ROUTER_FELADAT = "matek_cas"` — a C24b óta router-feladat (`[router] feladatok`, a `parancslista.py` sorrendje);
a „Megoldás” parancs (C24b) ezt routolja. A kérés a `modulok/matek/megoldas.py`-é (egy prompt a mérésre és az éles útra).
A kalibrált jelet a 63(a) döntés szerint a koordinátor/felhasználó adja; addig minden futás `proba` (D9).
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

ITT = Path(__file__).resolve().parent
for _ut in (ITT.parent, ITT.parent.parent):                    # a `kozos` (eval) és a `homokozo` (modulok)
    if str(_ut) not in sys.path:
        sys.path.insert(0, str(_ut))
from kozos import arany as A  # noqa: E402
from kozos import matek  # noqa: E402

ARANY = A.betolt(ITT.parent / "matek")
VERZIO = "matek_cas-" + A.verzio(ARANY)
ROUTER_FELADAT = "matek_cas"
VALTOZO = "EREDMENY"

# A kérés (prompt + keret) a matek-motor éles útjáé (C24b, `modulok/matek/megoldas.py`): a mérés pontosan azt méri, amit a
# „Megoldás” parancs a modelltől kér (a C24a-váz típusfüggő alak-utasítását az általános alak-leírás váltotta).
from matek import megoldas as MEGOLDAS  # noqa: E402

def tetelek(cfg):
    for f in ARANY["feladatok"]:
        yield {"id": f["id"], "keres": MEGOLDAS.keres(f["szoveg"]), "vart": {**f["vart"], "tema": f["tema"]}}


def kodblokk(valasz) -> str | None:
    """A válasz utolsó Python-kódblokkja (a `<think>` rész nélkül); None, ha nincs."""
    return MEGOLDAS.kodblokk(valasz)


def formatum_ok(valasz, vart) -> bool:
    """C18.1 (csak jelentés): van-e kódblokk, és beállítja-e az `EREDMENY`-t."""
    k = kodblokk(valasz)
    return bool(k and re.search(rf"^\s*{VALTOZO}\s*=", k, re.M))


def _tiszta(s: str) -> str:
    return re.sub(r"\bE\b", "e", s)


def valasz_szoveg(ertek: dict | None, tipus: str) -> str | None:
    """A homokozó JSON-eredménye → a `matek` pontozójának szöveges válasza (vagy None, ha nem alakítható)."""
    if not isinstance(ertek, dict):
        return None
    t = ertek.get("tipus")
    if t == "halmaz":
        elemek = [_tiszta(e) for e in ertek.get("elemek", [])]
        if tipus in ("szam", "kifejezes"):
            return elemek[0] if len(elemek) == 1 else None
        if tipus == "halmaz":
            return "; ".join(f"x = {e}" for e in elemek) if elemek else "nincs megoldás"
        if tipus == "intervallum":
            return " U ".join(f"[{e}; {e}]" for e in elemek) if elemek else None
        return None
    if t == "kifejezes":
        v = _tiszta(ertek.get("ertek", ""))
        return f"x = {v}" if tipus == "halmaz" else v
    if t == "intervallum" and tipus == "intervallum":
        return " U ".join(f"{'(' if d['bal_nyitott'] else '['}{_tiszta(d['a'])}; {_tiszta(d['b'])}"
                          f"{')' if d['jobb_nyitott'] else ']'}" for d in ertek.get("darabok", [])) or None
    if t == "par" and tipus == "par":
        return "; ".join(f"{k} = {_tiszta(v)}" for k, v in ertek.get("ertekek", {}).items())
    return None


def pontoz(rekordok, homokozo=None) -> dict:
    kodok = [kodblokk(r.get("valasz")) for r in rekordok]
    futas: dict[int, dict] = {}
    if any(kodok):
        if homokozo is None:
            from homokozo import Homokozo
            homokozo = Homokozo()
        indexek = [i for i, k in enumerate(kodok) if k]
        for i, e in zip(indexek, homokozo.futtat([{"muvelet": "kod", "kod": kodok[i], "valtozo": VALTOZO}
                                                  for i in indexek])):
            futas[i] = e
    jo, tema, rossz = 0, defaultdict(lambda: [0, 0]), []
    allapotok: dict[str, int] = defaultdict(int)
    for i, r in enumerate(rekordok):
        vart = r["vart"]
        if not kodok[i]:
            allapot, ok, indok = "nincs_kod", False, "nincs kódblokk"
        else:
            e = futas[i]
            allapot = e["allapot"]
            if allapot != "ok":
                ok, indok = False, f"{allapot}: {e['uzenet']}"[:200]
            else:
                szoveg = valasz_szoveg(e["ertek"], vart["tipus"])
                ok, indok = matek.ekvivalens(vart, szoveg) if szoveg else (False, f"nem alakítható: {e['ertek']}")
        allapotok[allapot] += 1
        jo += ok
        t = tema[vart.get("tema", "egyeb")]
        t[0] += ok
        t[1] += 1
        if not ok:
            rossz.append({"id": r["id"], "allapot": allapot, "indok": str(indok)[:200]})
    n = len(rekordok)
    return {"pontszam": round(jo / n, 4) if n else 0.0, "helyes": jo, "allapotok": dict(sorted(allapotok.items())),
            "temak": {k: f"{a}/{b}" for k, (a, b) in sorted(tema.items())}, "rossz": rossz}
