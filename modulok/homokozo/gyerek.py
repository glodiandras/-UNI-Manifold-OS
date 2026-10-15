"""A homokozó gyermekfolyamata (a `sandbox-exec` profil alatt, `python -I -B`).

Protokoll: induláskor egy `{"kesz": true}` sor; utána soronként egy JSON-feladat a stdin-en, és feladatonként
egy JSON-eredmény a protokoll-csatornán, a feladat `azonosito`-jával (a szülő csak a várt azonosítójú, szigorúan
ellenőrzött sort fogadja el; a `kod` után a szülő leállítja a gyermeket: Audit 3 A3-02). Az eredeti stdout a protokollé; az 1-es leíró a `/dev/null`-ra kerül,
hogy a futtatott kód kiírása ne keveredjen bele (a szülő a hibás sort amúgy is `homokozo_hiba`-nak veszi).

Műveletek:
  kod    nem megbízható SymPy-kód (`kod.py`), az eredmény JSON-alakban
  hivas  megbízható függvény a zárt `MUVELETEK` regiszterből (a `grafikon.*` a C35a-é)
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import time
from pathlib import Path

ITT = Path(__file__).resolve().parent
MODULOK = ITT.parent
for _ut in (MODULOK / "eval", MODULOK):                      # a `kozos` (eval) és a `homokozo`, `matek` csomag
    if str(_ut) not in sys.path:
        sys.path.insert(0, str(_ut))

# név → (modul, függvény); a függvény JSON-ható kulcsszavas argumentumokat kap, JSON-hatót ad vissza
MUVELETEK = {
    "matek.levezetes": ("matek.levezetes", "ellenoriz"),
    "matek.megoldashalmaz": ("matek.levezetes", "megoldashalmaz"),
    "matek.egyseg": ("matek.egyseg", "ellenoriz"),
    "matek.eredmeny": ("matek.eredmeny", "osszevet"),                 # C24b: a CAS-eredmény LaTeX-alakja és két eredmény egyezése
    "grafikon.felismeres": ("grafikon.muveletek", "felismeres"),      # C35a: képlet → plot-blokk javaslat
    "grafikon.elemzes": ("grafikon.muveletek", "elemzes"),            # C35a: zérushely, szélsőérték, aszimptota
    "grafikon.egyezes": ("grafikon.muveletek", "egyezes"),            # C35b-mag: két függvény-kifejezés azonossága (modell-ág)
    "homokozo.alvas": ("homokozo.gyerek", "_alvas"),          # a tesztek és a homokozo-proba időzítéséhez
}


def _alvas(mp: float = 0.0) -> str:
    time.sleep(mp)
    return "ok"


def vegrehajt(feladat: dict) -> dict:
    from homokozo import idozito, kod
    indul = time.monotonic()
    ki: dict = {"allapot": "ok", "ertek": None, "uzenet": ""}
    try:
        with idozito.korlatozva(float(feladat.get("idokorlat_s") or 10)):
            if feladat.get("muvelet") == "kod":
                ertek, kimenet = kod.futtat(str(feladat.get("kod") or ""), feladat.get("valtozo") or "EREDMENY")
                ki["ertek"] = kod.szerializal(ertek)
                ki["kimenet"] = kimenet
            elif feladat.get("muvelet") == "hivas":
                nev = feladat.get("nev")
                if nev not in MUVELETEK:
                    raise kod.Tiltott(f"ismeretlen művelet: {nev}")
                modul, fv = MUVELETEK[nev]
                ki["ertek"] = getattr(importlib.import_module(modul), fv)(**(feladat.get("args") or {}))
            else:
                raise kod.Tiltott(f"ismeretlen művelet-fajta: {feladat.get('muvelet')}")
    except idozito.Idotullepes:
        ki.update(allapot="idotullepes", uzenet="a feladat túllépte az időkorlátot")
    except kod.Tiltott as exc:
        ki.update(allapot="tiltott", uzenet=str(exc))
    except PermissionError as exc:
        ki.update(allapot="tiltott", uzenet=f"a homokozó megtagadta: {exc}"[:500])
    except MemoryError:
        ki.update(allapot="memoria", uzenet="elfogyott a memória")
    except SyntaxError as exc:
        ki.update(allapot="hiba", uzenet=f"szintaktikai hiba: {exc.msg} ({exc.lineno}. sor)")
    except RecursionError:
        ki.update(allapot="hiba", uzenet="túl mély rekurzió")
    except Exception as exc:                                    # a kód és a SymPy bármit dobhat; a hiba az eredmény
        ki.update(allapot="hiba", uzenet=f"{type(exc).__name__}: {exc}"[:500])
    ki["mp"] = round(time.monotonic() - indul, 4)
    return ki


def main() -> int:
    proto = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    nulla = os.open(os.devnull, os.O_WRONLY)
    os.dup2(nulla, 1)
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
    import sympy  # noqa: F401 — a betöltés a kézfogás előtt (a szülő időkorlátja feladatonként számol)
    from kozos import matek  # noqa: F401
    proto.write(json.dumps({"kesz": True, "verzio": 1}) + "\n")
    for sor in sys.stdin:
        sor = sor.strip()
        if not sor:
            continue
        try:
            feladat = json.loads(sor)
        except json.JSONDecodeError:
            feladat = None
        if not isinstance(feladat, dict):
            eredmeny = {"allapot": "hiba", "ertek": None, "uzenet": "hibás feladat-sor", "mp": 0.0}
            feladat = {}
        else:
            eredmeny = vegrehajt(feladat)
        azonosito = feladat.get("azonosito")
        try:
            proto.write(json.dumps(dict(eredmeny, azonosito=azonosito), ensure_ascii=False, default=str) + "\n")
        except (TypeError, ValueError) as exc:
            proto.write(json.dumps({"azonosito": azonosito, "allapot": "hiba", "ertek": None,
                                    "uzenet": f"nem JSON-ható eredmény: {exc}", "mp": eredmeny.get("mp", 0.0)}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
