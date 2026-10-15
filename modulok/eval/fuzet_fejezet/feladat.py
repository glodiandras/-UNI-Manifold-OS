"""Aranyhalmaz: a füzetlánc 1. lépése (router-feladat: `fuzet_fejezet`, 63(e)) — 97 fotó.

A legacy erős módszerének képes hívása, változatlan prompttal: a fotó oldalai + a vault tárgyi fejezeteinek
zárt listája → `TANTÁRGY`, `CÍMEK`, `TARTALOM`, `FEJEZET` (legfeljebb két kód). Csak utasítható képmodellre
értelmes; a tiszta OCR-modellek listából nem választanak (azokat az `ocr_kezi` méri).

Összevetés a legacyvel: ott a **lánc végi** jegyzeten mért tantárgy 97/97, fejezet 93/97 (Qwen3.5-9B olvasó +
gemma-4-12B választó, 2026-09-26). Itt az 1. lépés fejezetkódja áll a mérlegen, ezért a szám közelítő
összevetés; a teljes lánc a `fuzet_valaszto`-n mérődik.

**Oldalképek (C21)**: a legacy papírkivágása és forgatása (`modulok/fuzet/kep.py`, a lánccal közös): a kivágott papír a spirálnál
kettévágva; az álló papír oldalai a `fuzet_forgatas` `FORGATO`-tól rögzített irányával forgatva (ha az irány hiányzik, a
tételek nem készülnek el: előbb `bin/mos eval qwen35_9b fuzet_forgatas`). A prompt és a szétszedés a lánccal közös
(`modulok/fuzet/modszer.py`), a szövege változatlan.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ITT = Path(__file__).resolve().parent
sys.path.insert(0, str(ITT.parent))
sys.path.insert(0, str(ITT.parent.parent))
from kozos import arany as A  # noqa: E402
from kozos import kimenet  # noqa: E402
from fuzet import kep, modszer  # noqa: E402

OCR = ITT.parent / "ocr_kezi"
ARANY = A.betolt(OCR)
VERZIO = "fuzet_fejezet-" + A.verzio(ARANY)
ROUTER_FELADAT = "fuzet_fejezet"
MAX_TOKEN = modszer.MAX_TOKEN_FEJEZET
FEJEZET_MAX = modszer.FEJEZET_MAX
PROMPT = modszer.FEJEZET_PROMPT
szetszed = modszer.szetszed


def _forgatas_modul():
    spec = importlib.util.spec_from_file_location("mos_eval_fejezet_forgatas", ITT.parent / "fuzet_forgatas" / "feladat.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fejezetek() -> list[dict]:
    return A.betolt(OCR, "katalogus.json")["fejezetek"]


def fejezetlista(fej: list[dict]) -> str:
    sorok, targy = [], None
    for f in fej:
        if f["targy"] != targy:
            targy = f["targy"]
            sorok.append(f"[{targy}]")
        sorok.append(f"{f['kod']} – {f['nev']}")
    return "\n".join(sorok)


def tetelek(cfg):
    fej = fejezetek()
    lista = fejezetlista(fej)
    kodok = {f["kod"]: f["nev"] for f in fej}
    fg = _forgatas_modul()
    iranyok = fg.iranyok(cfg)
    tmp, px = fg.tmp_mappa(cfg), int(ARANY["kep_px"])
    elokeszitve = []
    for f in ARANY["fotok"]:
        forras = fg.forras(cfg, f["foto"])
        meta, utak = kep.oldalkepek(forras, tmp, px=px)
        elokeszitve.append((f, forras, meta, utak))
    hianyzik = [f["foto"] for f, _, meta, _ in elokeszitve if not meta["fekvo"] and f["foto"] not in iranyok]
    if hianyzik:
        raise FileNotFoundError(f"az álló papírú fotók irányát a `fuzet_forgatas` adja ({fg.FORGATO}); hiányzik "
                                f"{len(hianyzik)} fotóé: {', '.join(hianyzik[:5])} — előbb: bin/mos eval {fg.FORGATO} fuzet_forgatas")
    for f, forras, meta, utak in elokeszitve:
        forgatas = None if meta["fekvo"] else iranyok[f["foto"]]
        if forgatas:
            _, utak = kep.oldalkepek(forras, tmp, forgatas=forgatas, px=px)
        yield {"id": f["foto"],
               "keres": {"messages": [{"role": "user", "content": PROMPT.format(n=len(utak), fejezetek=lista)}],
                         "images": [str(p) for p in utak], "max_tokens": MAX_TOKEN},
               "vart": {"helyes": f["helyes"], "elfogadhato": [e["jegyzet"] for e in f.get("elfogadhato_utolag", [])],
                        "kodok": kodok, "kivagas": meta["kivagas"], "forgatas": forgatas}}


def formatum_ok(valasz, vart) -> bool:
    """C18.1 (csak jelentés): van-e a válaszban `FEJEZET:` mező."""
    return kimenet.mezo(kimenet.tisztit(valasz), "FEJEZET") is not None


def pontoz(rekordok) -> dict:
    n = len(rekordok)
    szam = {"fejezet": 0, "fejezet_elbiralt": 0, "targy": 0, "nincs_kod": 0}
    rossz = []
    for r in rekordok:
        v = r["vart"]
        d = szetszed(r.get("valasz"), v["kodok"])
        szigoru = {h[:3] for h in v["helyes"]}
        elbiralt = szigoru | {h[:3] for h in v.get("elfogadhato", [])}
        valasztott = set(d["fejezetek"])
        szam["nincs_kod"] += not valasztott
        szam["fejezet"] += bool(valasztott & szigoru)
        szam["fejezet_elbiralt"] += bool(valasztott & elbiralt)
        szam["targy"] += bool(valasztott) and d["fejezetek"][0][0] == v["helyes"][0][0]
        if not valasztott & szigoru:
            rossz.append({"id": r["id"], "valasztott": d["fejezetek"], "helyes": sorted(szigoru)})
    arany_ = {k: round(x / n, 4) if n else 0.0 for k, x in szam.items()}
    return {"pontszam": arany_["fejezet"], **arany_, "szam": szam, "legacy_lanc": {"targy": "97/97", "fejezet": "93/97"},
            "rossz": rossz}
