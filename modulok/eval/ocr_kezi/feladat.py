"""Aranyhalmaz: füzetfotó olvasása (router-feladat: `ocr_kezi`) — 97 kézzel olvasott fotó.

A modell átírja a lapot; az arany **kötési** címke (melyik jegyzethez tartozik a lap), elvárt szöveg nincs.
Ezért a pontozó egy determinisztikus lexikai bíró: az átirat szavaiból BM25-tel rangsorolja a vault
elméleti jegyzeteit (fagyasztott `katalogus.json`), és azt méri, hogy a helyes jegyzet az első öt között
van-e. A jó átiratból a helyes jegyzet kikereshető, a félreolvasottból nem (a legacy lánc pont ezen bukott).
A 20 képletes fotón külön mutató a kézzel átírt képletek megtalálási aránya az átiratban.

Mit nem lát: a szó szerinti olvasási pontosságot (ahhoz teljes kézi átirat kellene), és azt, ha a modell a
lap témáját jól, de a szövegét pontatlanul adja vissza. Ezt a C19 rétegzett mintája bírálja.
"""
from __future__ import annotations

import sys
from pathlib import Path

ITT = Path(__file__).resolve().parent
sys.path.insert(0, str(ITT.parent))
from kozos import arany as A  # noqa: E402
from kozos import bm25, kep, kimenet, latex, tavolsag  # noqa: E402

ARANY = A.betolt(ITT)
VERZIO = "ocr_kezi-" + A.verzio(ARANY)
ROUTER_FELADAT = "ocr_kezi"

PROMPT = (
    "A {n} képen egy magyar középiskolás diák kézzel írt iskolai füzetének oldalai láthatók. "
    "Írd át pontosan, magyarul, amit az oldalakon olvasol: a címeket, a szöveget és a feladatokat, sorról sorra. "
    "A képleteket LaTeX-ben írd, $…$ jelek között. Ne foglald össze, ne magyarázd és ne egészítsd ki: "
    "csak az olvasható szöveget add vissza.")
SZO_MAX = 1200          # az átiratból ennyi szó számít (a katalógus bemásolása nem ér többet)
TO_HOSSZ = 6
CIM_SULY, CIMSOR_SULY = 4, 2
KEPLET_KUSZOB = 0.8
TOP_K = 5

_biro = None


def tokenek(szoveg: str) -> list[str]:
    return [w[:TO_HOSSZ] for w in (tavolsag.hajt(x) for x in tavolsag.szavak(szoveg)) if len(w) >= 3 and not w.isdigit()]


def katalogus() -> dict:
    return A.betolt(ITT, "katalogus.json")


def biro() -> bm25.Bm25:
    """A lexikai bíró: jegyzetenként a tartalom szózsákja + a cím (×4) és a címsorok (×2)."""
    global _biro
    if _biro is None:
        b = bm25.Bm25()
        for j in katalogus()["jegyzetek"]:
            szavak = dict(j["szavak"])
            for t in tokenek(j["cim"]):
                szavak[t] = szavak.get(t, 0) + CIM_SULY
            for t in tokenek(" ".join(j["cimsorok"])):
                szavak[t] = szavak.get(t, 0) + CIMSOR_SULY
            b.hozzaad(j["ut"], szavak)
        _biro = b
    return _biro


def rangsor(atirat: str, k: int = TOP_K) -> list[str]:
    return [ut for ut, _ in biro().rangsor(tokenek(atirat)[:SZO_MAX], k)]


def kepletek_aranya() -> dict[str, list[str]]:
    """Fotónként a kézzel átírt képletek (az `ocr_keplet` aranyából), ha már megvan."""
    ut = ITT.parent / "ocr_keplet" / "arany.json"
    if not ut.exists():
        return {}
    ki: dict[str, list[str]] = {}
    for k in A.betolt(ut.parent)["kepletek"]:
        ki.setdefault(k["foto"], []).append(k["latex"])
    return ki


def fotok(cfg) -> list[tuple[dict, Path]]:
    mappa = cfg.path("vault") / ARANY["fotomappa"]
    ki = [(f, mappa / f["foto"]) for f in ARANY["fotok"]]
    hianyzik = [f["foto"] for f, p in ki if not p.is_file()]
    if hianyzik:
        raise FileNotFoundError(f"hiányzó füzetfotó a vaultban ({len(hianyzik)}): {', '.join(hianyzik[:5])}")
    return ki


def vart(f: dict, kepletek: dict[str, list[str]]) -> dict:
    v = {"foto": f["foto"], "helyes": f["helyes"],
         "elfogadhato": [e["jegyzet"] for e in f.get("elfogadhato_utolag", [])]}
    if f["foto"] in kepletek:
        v["kepletek"] = kepletek[f["foto"]]
    return v


def tetelek(cfg):
    kepl = kepletek_aranya()
    tmp = cfg.path("tmp") / "eval-fuzet"
    for f, forras in fotok(cfg):
        lapok = kep.oldalak(forras, tmp, int(ARANY["kep_px"]))
        yield {"id": f["foto"],
               "keres": {"messages": [{"role": "user", "content": PROMPT.format(n=len(lapok))}],
                         "images": [str(p) for p in lapok], "max_tokens": int(ARANY["max_token"])},
               "vart": vart(f, kepl)}


def keplet_talalat(atirat: str, kepletek: list[str]) -> float:
    """A kézi képletek hányada található meg az átiratban (a jelölt képletek között vagy a nyers szövegben)."""
    jeloltek = latex.kepletek(atirat) + [s for s in atirat.splitlines() if s.strip()]
    return A.atlag(latex.legjobb(k, jeloltek)[0] >= KEPLET_KUSZOB for k in kepletek)


def pontoz(rekordok) -> dict:
    n = len(rekordok)
    szam = {"jegyzet5": 0, "jegyzet5_szigoru": 0, "jegyzet1": 0, "fejezet1": 0, "targy1": 0, "ures": 0}
    kepletes, rossz = [], []
    for r in rekordok:
        v = r["vart"]
        atirat = kimenet.tisztit(r.get("valasz"))
        if not atirat:
            szam["ures"] += 1
        top = rangsor(atirat) if atirat else []
        helyes = set(v["helyes"])
        jo = helyes | set(v.get("elfogadhato", []))
        szam["jegyzet5"] += bool(jo & set(top))
        szam["jegyzet5_szigoru"] += bool(helyes & set(top))
        szam["jegyzet1"] += bool(top and top[0] in jo)
        szam["fejezet1"] += bool(top and top[0][:3] in {h[:3] for h in jo})
        szam["targy1"] += bool(top and top[0][0] == v["helyes"][0][0])
        if not jo & set(top):
            rossz.append({"id": r["id"], "elso": top[0] if top else None, "helyes": v["helyes"][0]})
        if v.get("kepletek"):
            kepletes.append(keplet_talalat(atirat, v["kepletek"]))
    arany_ = {k: round(x / n, 4) if n else 0.0 for k, x in szam.items()}
    return {"pontszam": arany_["jegyzet5"], **arany_, "szam": szam,
            "keplet_talalat": round(A.atlag(kepletes), 4) if kepletes else None, "kepletes_fotok": len(kepletes),
            "rossz": rossz}


def ellenoriz(cfg) -> dict:
    """Épség: minden fotó megvan-e, és a hash egyezik-e az arannyal (a mérés előtt egyszer érdemes futtatni)."""
    elter = [f["foto"] for f, p in fotok(cfg) if A.sha256(p) != f["sha256"]]
    return {"fotok": len(ARANY["fotok"]), "hash_elter": elter}


def plafon() -> dict:
    """A bíró plafonja: a kézi `leiras` mint átirat (ennél a modell csak a lap több szövegével lehet jobb)."""
    return pontoz([{"id": f["foto"], "vart": vart(f, {}), "valasz": f["leiras"]} for f in ARANY["fotok"]])


if __name__ == "__main__":
    import json
    from core import config
    print(json.dumps({"epseg": ellenoriz(config.load()), "plafon": {k: v for k, v in plafon().items() if k != "rossz"}},
                     ensure_ascii=False, indent=1))
