"""A füzetlánc módszere egy helyen (C21): a promptok, a válaszok szétszedése, a jelöltlista és a választás.

A lánc (`lanc.py`) és a mérés (`modulok/eval/fuzet_fejezet`, `fuzet_valaszto`, `fuzet_forgatas`) ugyanezt hívja, így a kalibrált
beállítás és az éles kérés nem térhet el. A promptok szövege a legacy `calibration.json → fuzet.eros` (`fejezet_prompt`,
`jegyzet_prompt.szam`, `forgatas_prompt`, prompt-verzió 2026-09-26.1 / .4) változatlanul; az átirat promptja az `ocr_kezi`
eval-feladaté (onnan töltjük: a kalibráció arra a szövegre szól).

1. lépés (`fuzet_fejezet`, képes): a fotó oldalai + a fejezetek zárt listája → `TANTÁRGY`, `CÍMEK`, `TARTALOM`, `FEJEZET`.
2. lépés (`fuzet_valaszto`, szöveges): a választott fejezet(ek) elméleti jegyzetei + a tantárgy(ak)on belüli szóalapú rangsor első
   öt jegyzete, „tantárgy › fejezet › cím” soronként → egy sorszám; nincs értelmezhető sorszám → a szóalapú rangsor első jelöltje.
"""
from __future__ import annotations

import importlib.util
import re
import sys
import unicodedata
from pathlib import Path

MODULOK = Path(__file__).resolve().parent.parent
if str(MODULOK / "eval") not in sys.path:
    sys.path.insert(0, str(MODULOK / "eval"))
from kozos import kimenet  # noqa: E402

FEJEZET_MAX = 2
BM25_KIEGESZITES = 5
MAX_TOKEN_FEJEZET = 360
MAX_TOKEN_VALASZTO = 24
MAX_TOKEN_FORGATAS = 60
TANTARGYAK = {"M": "Matematika", "F": "Fizika", "T": "Történelem", "I": "Irodalom", "N": "Magyar nyelvtan",
              "D": "Digitális kultúra", "E": "Angol nyelv"}

FEJEZET_PROMPT = (
    "A {n} képen egy magyar középiskolás diák kézzel írt iskolai füzetének oldalai láthatók (egy fotó két oldala). "
    "Olvasd el figyelmesen a címeket és a szöveget, és döntsd el, melyik tantárgy melyik fejezetének tananyaga ez."
    "\n\nA tantárgyak és fejezeteik (kód – cím):\n{fejezetek}\n\nPontosan ebben a formában válaszolj, magyarul:\n"
    "TANTÁRGY: <a fenti tantárgyak egyike>\n"
    "CÍMEK: <az oldalakon olvasható címek és alcímek, vesszővel elválasztva>\n"
    "TARTALOM: <2-3 mondat: milyen tananyag van az oldalakon, a kulcsfogalmakkal, a szereplő nevekkel, művekkel, "
    "képletekkel>\n"
    "FEJEZET: <a legjobban illő fejezet kódja (pl. M10); ha a két oldal két fejezetet tárgyal, két kód vesszővel, "
    "a nagyobb rész elöl>")

VALASZTO_PROMPT = (
    "Egy diák kézzel írt füzetoldalának leírása (egy gépi olvasó készítette a fotóról):\nTANTÁRGY: {tantargy}\n"
    "CÍMEK: {cimek}\nTARTALOM: {tartalom}\n\nAz alábbi tankönyvi jegyzetek közül melyiknek a témáját dolgozza fel ez a "
    "füzetoldal a legjobban?\n{jegyzetek}\n\nCsak a legjobban illő jegyzet sorszámát írd le, semmi mást.")

FORGATAS_PROMPT = "Olvasd el ennek a kézzel írt füzetoldalnak az első néhány sorát, pontosan, magyarul."

_eval_modulok: dict = {}


def _eval_modul(nev: str):
    if nev not in _eval_modulok:
        spec = importlib.util.spec_from_file_location(f"mos_fuzet_eval_{nev}", MODULOK / "eval" / nev / "feladat.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _eval_modulok[nev] = mod
    return _eval_modulok[nev]


def atirat_prompt(n: int) -> str:
    """Az `ocr_kezi` (kalibrált átirat) promptja `n` oldalképre."""
    return _eval_modul("ocr_kezi").PROMPT.format(n=n)


ALAP_ATIRAT_MAX_TOKEN = 1500       # az átirat válaszkerete, ha a mérés aranyhalmaza (amelyből a kalibrált érték jön) nincs a telepítésben


def atirat_max_token() -> int:
    """Az átirat válaszkerete: a kalibrált (mért) érték az `ocr_kezi` aranyhalmazból; ha az nincs, az alap — az éles lánc nem függhet a
    mérőhalmaz meglététől."""
    return int(_eval_modul("ocr_kezi").ARANY.get("max_token") or ALAP_ATIRAT_MAX_TOKEN)


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


# ---------------------------------------------------------------- 1. lépés

def fejezet_prompt(n: int, kat) -> str:
    return FEJEZET_PROMPT.format(n=n, fejezetek=kat.fejezetlista())


def szetszed(valasz, kodok: dict[str, str]) -> dict:
    """Az 1. válasz → tantárgy és fejezetkódok (csak a listában létezők, legfeljebb kettő)."""
    szoveg = kimenet.tisztit(valasz)
    targy = kimenet.mezo(szoveg, "TANTÁRGY") or ""
    mezo = kimenet.mezo(szoveg, "FEJEZET") or ""
    fej = []
    for b, n in re.findall(r"\b([A-Z])\s?(\d{2})\b", mezo):
        if b + n in kodok and b + n not in fej:
            fej.append(b + n)
    if not fej:                                                # a modell kód helyett nevet írt
        fej = [k for k, nev in kodok.items() if nev.lower() in mezo.lower()]
    return {"tantargy": targy, "fejezetek": fej[:FEJEZET_MAX]}


def olvasat(valasz, kat) -> dict:
    """Az 1. lépés válasza → tantárgy, címek, tartalom, fejezetkódok."""
    d = szetszed(valasz, {k: f["nev"] for k, f in kat.fej.items()})
    szoveg = kimenet.tisztit(valasz)
    return {**d, "cimek": kimenet.mezo(szoveg, "CÍMEK") or "", "tartalom": kimenet.mezo(szoveg, "TARTALOM") or ""}


# ---------------------------------------------------------------- 2. lépés

def targy_betu(tantargy: str, cimkek: dict | None = None) -> str | None:
    """A tantárgy betűje a modell válaszából. A `cimkek` (`[pdf.tags]`: betű → címke) címkéi előbb számítanak; ami nem illik rájuk, azt az
    alap-lista (`TANTARGYAK`) nevei döntik el — így a konfigurálatlan és a hiányos táblázat mellett is a meglévő nevek érvényesek."""
    t = nfc(tantargy).lower()
    for b, nev in (cimkek or {}).items():
        if isinstance(nev, str) and nev.strip() and nev.strip().lower() in t:
            return str(b)
    for b, nev in TANTARGYAK.items():
        if nev.lower() in t:
            return b
    return None


def jeloltek(olv: dict, kat, cimkek: dict | None = None) -> list[str]:
    """A legacy `jeloltek()`-je: a választott fejezetek jegyzetei; ha nincs fejezet, a tantárgy két szóalapú legjobb fejezete;
    utána a tantárgy(ak)on belüli szóalapú rangsor első `BM25_KIEGESZITES` még nem szereplő jegyzete."""
    betuk = {k[0] for k in olv["fejezetek"]} | ({targy_betu(olv["tantargy"], cimkek)} - {None})
    lekerdezes = f"{olv['cimek']} {olv['tartalom']}"
    kodok = [k for k in olv["fejezetek"] if k in kat.fej]
    if not kodok and betuk:
        pont: dict[str, float] = {}
        for ut, p in kat.rangsor(lekerdezes, betuk)[:60]:
            pont[ut[:3]] = pont.get(ut[:3], 0.0) + p
        kodok = [k for k, _ in sorted(pont.items(), key=lambda x: (-x[1], x[0]))[:2]]
    ki = [j["ut"] for k in kodok for j in kat.jegyzetek if j["ut"][:3] == k]
    latott, n = set(ki), 0
    for ut, _ in kat.rangsor(lekerdezes, betuk)[:80]:
        if n >= BM25_KIEGESZITES:
            break
        if ut not in latott:
            ki.append(ut)
            latott.add(ut)
            n += 1
    return ki


def tartalek(olv: dict, jl: list[str], kat) -> str | None:
    """A legacy tartaléka: a jelöltek közül a szóalapú rangsor első eleme (ha egyik sincs rangsorolva, a lista első)."""
    return next((u for u, _ in kat.rangsor(f"{olv['cimek']} {olv['tartalom']}", set()) if u in jl), jl[0] if jl else None)


def jegyzetlista(jl: list[str], kat) -> str:
    """„sorszám. tantárgy › fejezet › cím” (a legacy mérése szerint a legjobb formátum)."""
    return "\n".join(f"{i + 1}. {kat.fej[u[:3]]['targy']} › {kat.fej[u[:3]]['nev']} › {kat.cim[u]}" for i, u in enumerate(jl))


def valaszto_prompt(olv: dict, jl: list[str], kat) -> str:
    return VALASZTO_PROMPT.format(tantargy=olv["tantargy"] or "?", cimek=olv["cimek"] or "—", tartalom=olv["tartalom"] or "—",
                                  jegyzetek=jegyzetlista(jl, kat))


def valasztott(valasz, jl: list[str], kat) -> int | None:
    """A legacy `_valasztott()`-ja: előbb a leírt cím (a leghosszabb egyező), aztán az első érvényes sorszám."""
    t = nfc(kimenet.tisztit(valasz)).lower()
    talalt = [(len(c), i) for i, u in enumerate(jl) if (c := nfc(kat.cim.get(u, "")).lower()) and c in t]
    if talalt:
        return max(talalt)[1]
    szamok = [int(x) for x in re.findall(r"\b(\d{1,3})\b", t) if 1 <= int(x) <= len(jl)]
    return szamok[0] - 1 if szamok else None


def dontes(valasz, olv: dict, jl: list[str], kat) -> tuple[str | None, bool]:
    """→ (a választott jegyzet, bizonytalan-e). Egyetlen jelöltnél nincs modellhívás (a hívó nem is kérdez).

    80(h): ha a modell válasza nem értelmezhető (a legacy ekkor a `tartalek()`-ra, a szóalapú rangsor elsőjére esett vissza), a fotó
    **nem köt be**: (None, True), a hívó `kihagyva` állapotba teszi. A kérés (prompt, beállítás) és így a mérés ujjlenyomata nem változik;
    a `tartalek()` csak a C18/C19 mérés viszonyítása (`modulok/eval/fuzet_valaszto`)."""
    if len(jl) == 1:
        return jl[0], False
    i = valasztott(valasz, jl, kat)
    if i is not None:
        return jl[i], False
    return None, True


def ismert_targy(olv: dict, cimkek: dict | None = None) -> bool:
    """80(h): az 1. lépés tantárgya a zárt listában van-e (a tantárgy neve vagy legalább egy érvényes fejezetkód). Ismeretlen tantárgyú
    (pl. a listán nem szereplő) fotó nem kerül a szóalapú rangsor szerinti, bármelyik tantárgyba eső jelöltekhez."""
    return bool(olv.get("fejezetek")) or targy_betu(olv.get("tantargy") or "", cimkek) is not None
