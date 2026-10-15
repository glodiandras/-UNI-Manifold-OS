"""Aranyhalmaz: a füzetlánc 2. lépése, a zárt listás jegyzetválasztás (router-feladat: `fuzet_valaszto`) — 97 fotó (C19).

A legacy erős módszerének (`fuzet_eros.py`, `calibration.json → fuzet.eros`, 2026-09-26) 2. lépése a 2.0-ban, a legacy kódjának
futtatása nélkül: az 1. lépés olvasata (`TANTÁRGY`, `CÍMEK`, `TARTALOM`, `FEJEZET`) → a választott fejezet(ek) elméleti jegyzetei
+ a tantárgy(ak)on belüli szóalapú rangsor első öt jegyzete → a modell egy sorszámot ír. A legacy ALAP-változata: `kimenet: szam`,
leírás, gondolkodás és kép nélkül, 24 token, a `jegyzet_prompt.szam` szövegével; nincs értelmezhető sorszám → a szóalapú rangsor
első jelöltje (a legacy tartaléka).

**Az 1. lépés** a `fuzet_fejezet` feladat rögzített sorai az `OLVASO` modelltől (a legacy olvasója is a Qwen3.5-9B volt):
fotónként a fájl utolsó, nem üres sora (a sor a kérés ujjlenyomatával íródott; ha az olvasó újramér, a 2. lépés promptja és vele
az ujjlenyomata is változik, így a választó sorai újramérnek). A katalógus és a szóalapú rangsor a fagyasztott
`ocr_kezi/katalogus.json` és az `ocr_kezi` bírója (cím ×4, címsorok ×2 — a legacy `fuzet.index` mezősúlyaival).

**Bíró**: ugyanaz a 97 fotó és ugyanaz a kötési arany, mint a legacy 87/97-es mérésénél (`ocr_kezi/arany.json`, `helyes`:
szigorú; `elfogadhato_utolag`: elbírált). A pontszám a szigorú találati arány — közvetlenül összevethető a legacy 87/97-tel
(0,897) és 91/97-tel (0,938). A C21 óta az 1. lépés oldalképei a legacy papírkivágásával és forgatásával készülnek
(`modulok/fuzet/kep.py`); a prompt, a jelöltlista és a választás a lánccal közös (`modulok/fuzet/modszer.py`, változatlan szöveg).
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unicodedata
from pathlib import Path

ITT = Path(__file__).resolve().parent
sys.path.insert(0, str(ITT.parent))
sys.path.insert(0, str(ITT.parent.parent))
from kozos import arany as A  # noqa: E402
from kozos import kimenet  # noqa: E402
from fuzet import modszer  # noqa: E402
from fuzet.katalogus import Katalogus  # noqa: E402

OCR = ITT.parent / "ocr_kezi"
ARANY = A.betolt(OCR)
VERZIO = "fuzet_valaszto-" + A.verzio(ARANY)
ROUTER_FELADAT = "fuzet_valaszto"
OLVASO = "qwen35_9b"
MAX_TOKEN = 24
BM25_KIEGESZITES = 5
FEJEZET_MAX = 2
TANTARGYAK = {"M": "Matematika", "F": "Fizika", "T": "Történelem", "I": "Irodalom", "N": "Magyar nyelvtan",
              "D": "Digitális kultúra", "E": "Angol nyelv"}
LEGACY = {"szigoru": "87/97", "elbiralt": "91/97", "datum": "2026-09-26",
          "modszer": "Qwen3.5-9B olvasó (papírkivágás, forgatás) + gemma-4-12B választó, kimenet: szam"}

PROMPT = modszer.VALASZTO_PROMPT
_kat: list = []


def kat() -> Katalogus:
    if not _kat:
        _kat.append(Katalogus.fagyasztott())
    return _kat[0]


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def katalogus() -> tuple[dict, list[dict]]:
    k = kat()
    return k.fej, k.jegyzetek


targy_betu = modszer.targy_betu


def olvasat(valasz) -> dict:
    """Az 1. lépés válasza → tantárgy, címek, tartalom, fejezetkódok (a lánccal közös szétszedő)."""
    return modszer.olvasat(valasz, kat())


def jeloltek(olv: dict) -> list[str]:
    """A legacy `jeloltek()`-je (`modszer.jeloltek`, a fagyasztott katalógussal)."""
    return modszer.jeloltek(olv, kat())


def jegyzetlista(jl: list[str]) -> str:
    return modszer.jegyzetlista(jl, kat())


def olvasatok(cfg) -> dict[str, dict]:
    """Az olvasó (`OLVASO`) `fuzet_fejezet` sorai fotónként (a fájl utolsó, nem üres sora)."""
    ut = cfg.path("runs") / "eval" / OLVASO / "fuzet_fejezet.jsonl"
    if not ut.is_file():
        raise FileNotFoundError(f"hiányzik az 1. lépés mérése: {ut} — előbb: bin/mos eval {OLVASO} fuzet_fejezet")
    ki: dict[str, dict] = {}
    for s in ut.read_text(encoding="utf-8").splitlines():
        if s.strip():
            r = json.loads(s)
            if isinstance(r.get("valasz"), str) and r["valasz"].strip():
                ki[r["id"]] = r
    return ki


def tetelek(cfg):
    olv_sorok = olvasatok(cfg)
    hianyzik = [f["foto"] for f in ARANY["fotok"] if f["foto"] not in olv_sorok]
    if hianyzik:
        raise FileNotFoundError(f"az 1. lépés ({OLVASO} · fuzet_fejezet) {len(hianyzik)} fotóra nem adott olvasatot: "
                                f"{', '.join(hianyzik[:5])}")
    for f in ARANY["fotok"]:
        o = olvasat(olv_sorok[f["foto"]]["valasz"])
        jl = jeloltek(o)
        yield {"id": f["foto"],
               "keres": {"messages": [{"role": "user", "content": modszer.valaszto_prompt(o, jl, kat())}],
                         "max_tokens": MAX_TOKEN},
               "vart": {"helyes": f["helyes"], "elfogadhato": [e["jegyzet"] for e in f.get("elfogadhato_utolag", [])],
                        "jeloltek": jl, "tartalek": modszer.tartalek(o, jl, kat()), "olvaso_fejezetek": o["fejezetek"],
                        "olvaso_beallitas": olv_sorok[f["foto"]].get("beallitas")}}


def valasztott(valasz, jl: list[str]) -> int | None:
    """A legacy `_valasztott()`-ja: előbb a leírt cím (a leghosszabb egyező), aztán az első érvényes sorszám."""
    return modszer.valasztott(valasz, jl, kat())


def formatum_ok(valasz, vart) -> bool:
    """C18.1 (csak jelentés): van-e értelmezhető választás."""
    return valasztott(valasz, vart["jeloltek"]) is not None


def pontoz(rekordok) -> dict:
    n = len(rekordok)
    szam = {"szigoru": 0, "elbiralt": 0, "fejezet": 0, "a_listan": 0, "tartalek": 0}
    hossz, rossz = [], []
    for r in rekordok:
        v = r["vart"]
        jl = v["jeloltek"]
        i = valasztott(r.get("valasz"), jl)
        if i is None:
            szam["tartalek"] += 1
        dontes = jl[i] if i is not None else v["tartalek"]
        helyes = set(v["helyes"])
        jo = helyes | set(v.get("elfogadhato", []))
        szam["szigoru"] += dontes in helyes
        szam["elbiralt"] += dontes in jo
        szam["fejezet"] += bool(dontes) and dontes[:3] in {h[:3] for h in jo}
        szam["a_listan"] += bool(jo & set(jl))
        hossz.append(len(jl))
        if dontes not in helyes:
            rossz.append({"id": r["id"], "dontes": dontes, "helyes": v["helyes"][0], "a_listan": bool(helyes & set(jl))})
    arany_ = {k: round(x / n, 4) if n else 0.0 for k, x in szam.items()}
    return {"pontszam": arany_["szigoru"], **arany_, "szam": szam, "olvaso": OLVASO,
            "lista_atlag": round(sum(hossz) / n, 1) if n else 0.0, "lista_max": max(hossz, default=0),
            "legacy": LEGACY, "rossz": rossz}
