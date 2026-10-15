"""A grafikon-műveletek belépési pontjai: a homokozó gyermeke ezeket hívja (`gyerek.MUVELETEK`: `grafikon.felismeres`,
`grafikon.elemzes`), a tesztek és a CLI folyamaton belül is. JSON-ható kulcsszavas argumentumok be, JSON-ható szótár ki.

A jegyzet sorai nem megbízható bemenet (CLAUDE.md 46. döntés): éles úton a SymPy-értelmezés csak a homokozó
gyermekében fut; a kivágás (`jegyzet.py`) és a blokk szövege (`formatum.py`) CAS-import nélküli, a szülőben is élhet.
"""
from __future__ import annotations

from . import formatum as F

MAX_KEPLET = 4000          # a felismerő bemenetének plafonja (a pgfplots-blokk hosszabb lehet egy képletnél)


def javaslat_szotar(j) -> dict:
    """A `felismeres.Javaslat` JSON-ható alakja (az ábra szerkezetesen és a kész blokk szövegként is)."""
    return {"fajta": j.fajta, "bizonyossag": j.bizonyossag, "ok": j.ok, "forras_keplet": j.forras_keplet,
            "kulcs": j.kulcs, "abra": F.abra_szotar(j.abra) if j.abra is not None else None, "blokk": j.blokk}


def felismeres(keplet: str) -> dict:
    """Egy képlet (vagy TikZ/pgfplots szövegrész) → javaslat. Mindig választ ad (`bizonyossag`: biztos | bizonytalan |
    nincs); érvénytelen típusú vagy túl hosszú bemenetre hibát dob (a homokozóban `hiba` állapot)."""
    if not isinstance(keplet, str):
        raise TypeError("a képlet szöveg legyen")
    if len(keplet) > MAX_KEPLET:
        raise ValueError(f"a képlet hosszabb {MAX_KEPLET} jelnél")
    from . import felismeres as R
    return javaslat_szotar(R.felismer(keplet))


def elemzes(kifejezes: str, ablak, lepes_idokorlat_s: float = 3.0) -> dict:
    """Egy függvény zérushelye, szélsőértéke, aszimptotái az `ablak` = [alsó, felső] zárt intervallumán (a kifejezés a
    ```plot blokk jelölése, egy `x` változóval). Mindig szótárat ad; a hibát az `allapot` jelzi (lásd `jellemzok.py`)."""
    from . import jellemzok as E
    return E.elemez(kifejezes, ablak, float(lepes_idokorlat_s))


def egyezes(vart: str, kapott: str) -> dict:
    """Két függvény-kifejezés (a ```plot jelölése, `x`-ben) azonossága (C35b-mag, modell-ág: a modell kifejezése a felismerő
    kifejezésével egyezik-e). `kozos.matek.kifejezes_egyezik`: szimbolikusan, majd mintapontokon. A homokozóban fut."""
    for nev, kif in (("vart", vart), ("kapott", kapott)):
        if not isinstance(kif, str) or not kif.strip() or len(kif) > MAX_KEPLET:
            raise ValueError(f"a `{nev}` kifejezés nem üres szöveg legyen (legfeljebb {MAX_KEPLET} jel)")
    from kozos import matek as M
    return {"egyezik": bool(M.kifejezes_egyezik(M.elemez(vart), M.elemez(kapott), 1e-6))}
