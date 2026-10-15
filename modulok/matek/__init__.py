"""A matek-motor modell nélküli magja (C24a; TERV 5.6). A számítás a CAS-homokozóban fut (`modulok/homokozo`).

    levezetes_ellenorzese(sorok, vegeredmeny=False, kikotesek=(), mod="auto")   → az első hibás átmenet
    egyseg_ellenorzese(sor, jelolesek=None)                                    → mértékegység/dimenzió
    megoldashalmaz(sor)                                                        → egy sor valós megoldáshalmaza

A fájlba semmi nem ír; a végeredmény csak `vegeredmeny=True`-ra szerepel. Ha a homokozó nem fut, az eredmény
`nem_ellenorizheto` a homokozó üzenetével (csupasz, elzáratlan számítás nincs).

A modell-alapú megoldás, a második vélemény és a felület a C24b-é (docs/C24-TERV.md).
"""
from __future__ import annotations


def _homokozo(homokozo):
    if homokozo is not None:
        return homokozo
    from homokozo import Homokozo
    return Homokozo()


def _hiv(nev: str, args: dict, homokozo, idokorlat_s: float | None = None) -> dict:
    hk = _homokozo(homokozo)
    e = hk.egy({"muvelet": "hivas", "nev": nev, "args": args}, idokorlat_s=idokorlat_s)
    if e["allapot"] == "ok":
        return e["ertek"]
    return {"allapot": "nem_ellenorizheto", "ok": f"homokozó: {e['allapot']} — {e['uzenet']}"}


def levezetes_ellenorzese(sorok: list[str], *, vegeredmeny: bool = False, kikotesek: list[str] | tuple = (),
                          mod: str = "auto", homokozo=None) -> dict:
    hk = _homokozo(homokozo)
    lepes = float(hk.beall["lepes_idokorlat_s"])
    idokorlat = min(float(hk.beall["idokorlat_s"]) * 6, lepes * (2 * len(sorok) + 4))
    return _hiv("matek.levezetes", {"sorok": list(sorok), "vegeredmeny": bool(vegeredmeny),
                                    "kikotesek": list(kikotesek), "mod": mod, "lepes_idokorlat_s": lepes},
                hk, idokorlat)


def egyseg_ellenorzese(sor: str, *, jelolesek: dict | None = None, homokozo=None) -> dict:
    return _hiv("matek.egyseg", {"sor": sor, "jelolesek": jelolesek or {}}, homokozo)


def megoldashalmaz(sor: str, *, homokozo=None) -> dict:
    return _hiv("matek.megoldashalmaz", {"sor": sor}, homokozo)


def levezetes_sor(sor: str) -> str | None:
    """Egy jegyzetsor → levezetés-sor: a `$`/`$$` burok, az idézet- és callout-jel, a listajel, az `aligned`-környezet `&` és
    `\\\\` jelei nélkül; az üres és a környezet-nyitó/záró sor: None."""
    import re
    s = sor.strip()
    s = re.sub(r"^(?:>\s*)+", "", s)                                 # idézet / callout
    s = re.sub(r"^(?:[-*+]|\d+[.)])\s+", "", s)                     # listajel
    s = s.strip().strip("$").strip()
    if re.fullmatch(r"\\(?:begin|end)\{[a-z*]+\}(?:\{[^}]*\})?", s) or not s:
        return None
    s = re.sub(r"\\\\\s*$", "", s).replace("&", " ").strip()
    return s or None


def jegyzet_sorai(szoveg: str, tol: int, ig: int) -> list[str]:
    """A jegyzet `tol`–`ig` sorai (1-től, zárt) levezetés-sorként (`levezetes_sor`); az üres és a környezet-nyitó/záró
    sorok kimaradnak."""
    return [s for s, _ in sorszammal(list(enumerate(szoveg.splitlines()[max(tol, 1) - 1:ig], max(tol, 1))))]


def sorszammal(sorok: list[tuple[int, str]]) -> list[tuple[str, int]]:
    """(jegyzet-sorszám, nyers sor) párok → (levezetés-sor, jegyzet-sorszám) párok, a kimaradó sorok nélkül (C24b: a margójel a
    jegyzet sorára kerül)."""
    ki = []
    for n, sor in sorok:
        s = levezetes_sor(sor)
        if s:
            ki.append((s, n))
    return ki
