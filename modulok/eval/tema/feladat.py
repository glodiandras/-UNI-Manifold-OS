"""Aranyhalmaz: egy oktatóvideó témája (router-feladat: `tema`, C20b) — 118 staging-forrás, két kérés forrásonként.

A videólánc témadöntésének modell-ága (`modulok/ytdlp/itelet.py`, a legacy `media_itelet` portja): a modell egyszer az átiratból
(`TEMA_PROMPT_TARTALOM`), egyszer a címből és a kiadó útvonalából (`TEMA_PROMPT_METAADAT`) választ a tárgy számozott témalistájából;
a lánc erős sávja: a kettő ugyanazt adja, és a lexikai jel nem mond ellent. A mérés pontosan az éles kérést küldi (a prompt és a lista
a lánc függvényeiből; a lista befagyasztva az aranyban).

**Bíró**: a szigorú találat (a válasz sorszáma = a címke témája; a 3 témátlan videónál a helyes válasz „egyik sem”), a megengedő
(az elfogadható halmaz), és a lánc szabálya forrásonként: az automatikus döntések aránya és pontossága (A = B, a téma a lexikai
top-10-ben vagy a cím megnevezi). A pontszám a szigorú találati arány a két kérésfajtán együtt. Legacy-mérce (2026-09-20,
Qwen3-VL-4B): auto 84/118, szigorú pontosság 83/84.

Az átirat nem a repóban áll: az arany a staging forrásmappájára hivatkozik (út + a `transcript.md` sha256-ja).
"""
from __future__ import annotations

import sys
from pathlib import Path

ITT = Path(__file__).resolve().parent
sys.path.insert(0, str(ITT.parent))
sys.path.insert(0, str(ITT.parents[2]))
from kozos import arany as A  # noqa: E402
from kozos import kimenet  # noqa: E402

from modulok.ytdlp import itelet, staging, vaultoldal as VO  # noqa: E402
from modulok.ytdlp.szovegreteg import ablak_szoveg, cuek  # noqa: E402

ARANY = A.betolt(ITT)
VERZIO = "tema-" + A.verzio(ARANY)
ROUTER_FELADAT = "tema"
LEGACY = {"auto": "84/118", "szigoru": "83/84", "megengedo": "84/84", "modell": "Qwen3-VL-4B-Instruct-4bit", "datum": "2026-09-20"}


def atirat(cfg, v: dict) -> str:
    mappa = cfg.path("staging") / v["staging"]
    tr = mappa / "transcript.md"
    if A.sha256(tr) != v["atirat_sha256"]:
        raise ValueError(f"a staging átirata megváltozott az arany rögzítése óta: {v['staging']}")
    src = staging.olvas(mappa)
    return ablak_szoveg(cuek(VO.vtt_stagingbol(src, "hu")))


def tetelek(cfg):
    for v in ARANY["videok"]:
        lista, temak = ARANY["listak"][v["targy"]], ARANY["temak"][v["targy"]]
        pa, pb = itelet.tema_promptok(atirat(cfg, v), v["cim"], v["lap"], lista)
        vart = {"temak": temak, "tema": v["tema"], "elfogadhato": v["elfogadhato"], "video": v["id"],
                "lex_rang_top10": v["lex_rang_top10"], "cim_tema": v["cim_tema"]}
        for fajta, prompt in (("tartalom", pa), ("metaadat", pb)):
            if prompt:
                yield {"id": f"{v['id']}#{fajta}", "keres": {"messages": [{"role": "user", "content": prompt}],
                                                              "max_tokens": itelet.TEMA_MAX_TOKEN},
                       "vart": {**vart, "fajta": fajta}}


def dontes(valasz, vart) -> str | None:
    i = itelet.sorszam(kimenet.tisztit(valasz), len(vart["temak"]))
    return vart["temak"][i - 1] if i else None


def formatum_ok(valasz, vart) -> bool:
    v = kimenet.tisztit(valasz)
    return itelet.sorszam(v, len(vart["temak"])) is not None or "egyik" in v.lower()


def pontoz(rekordok) -> dict:
    szig = meng = 0
    fajtak: dict[str, list[int]] = {}
    par: dict[str, dict] = {}
    for r in rekordok:
        v = r["vart"]
        d = dontes(r.get("valasz"), v)
        jo = d == v["tema"]
        ok = jo or (d is not None and d in v["elfogadhato"])
        szig += jo
        meng += ok
        fajtak.setdefault(v["fajta"], [0, 0])
        fajtak[v["fajta"]][0] += jo
        fajtak[v["fajta"]][1] += 1
        par.setdefault(v["video"], {"vart": v})[v["fajta"]] = d
    n = len(rekordok)
    auto = auto_jo = auto_ok = 0
    for p in par.values():
        a, b, v = p.get("tartalom"), p.get("metaadat"), p["vart"]
        lex = bool(a) and (a in v["lex_rang_top10"] or v["cim_tema"] == a)
        if a and a == b and lex:
            auto += 1
            auto_jo += a == v["tema"]
            auto_ok += a == v["tema"] or a in v["elfogadhato"]
    return {"pontszam": round(szig / n, 4) if n else 0.0, "szigoru": round(szig / n, 4) if n else 0.0,
            "megengedo": round(meng / n, 4) if n else 0.0,
            "fajtank": {k: round(x[0] / x[1], 4) for k, x in fajtak.items() if x[1]},
            "lanc": {"forras": len(par), "auto": auto, "auto_arany": round(auto / len(par), 4) if par else 0.0,
                     "auto_szigoru": round(auto_jo / auto, 4) if auto else None, "auto_megengedo": round(auto_ok / auto, 4) if auto else None},
            "legacy": LEGACY}
