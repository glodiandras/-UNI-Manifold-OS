"""Aranyhalmaz: elmagyarázza-e a videó felirat-ablaka a jegyzet tartalmát (router-feladat: `kotes`, C20b) — 141 olvasott pár.

A videólánc kötési javaslatainak modell-olvasása (`modulok/ytdlp/itelet.py` `KOTES_PROMPT`, a legacy `media_itelet.kotes_itelet`
portja): a modell a felirat-ablakot (≤ 1400 karakter) és a jegyzet legközelebbi bekezdését (≤ 900) kapja, és egy szóval felel
(igen/nem). A lánc szabálya (`itelet.kotes_dontes`): a javaslat csak „igen” ÉS a verifikátor p-je a tárgy sávjában (N: ≥ 0,90)
mellett köt — a modell „nem”-je nem elvetés, csak nem kötés.

**Bíró**: a pontosság (igen/nem a címke szerint; az értelmezhetetlen válasz hibás), és a lánc szabálya: az elfogadott párok
pontossága és száma. A pontszám a pontosság. Legacy-mérce (gemma-4-12B, 2026-09-23): p ≥ 0,90 és „igen” → 45/45.
"""
from __future__ import annotations

import sys
from pathlib import Path

ITT = Path(__file__).resolve().parent
sys.path.insert(0, str(ITT.parent))
sys.path.insert(0, str(ITT.parents[2]))
from kozos import arany as A  # noqa: E402
from kozos import kimenet  # noqa: E402

from modulok.ytdlp import itelet  # noqa: E402

ARANY = A.betolt(ITT)
VERZIO = "kotes-" + A.verzio(ARANY)
ROUTER_FELADAT = "kotes"
LEGACY = {"elfogadva": "45/45", "szabaly": "p ≥ 0,90 és igen (N)", "modell": "gemma-4-12B-it-4bit", "datum": "2026-09-23"}


def tetelek(cfg):
    for p in ARANY["parok"]:
        yield {"id": p["id"], "keres": {"messages": [{"role": "user", "content": itelet.kotes_prompt(p["ablak_szoveg"], p["jegyzet_cim"],
                                                                                                    p["jegyzet_reszlet"])}],
                                        "max_tokens": itelet.KOTES_MAX_TOKEN},
               "vart": {"y": p["y"], "p": p["p"], "targy": p["tema"][:1]}}


def formatum_ok(valasz, vart) -> bool:
    return itelet.igen_nem(kimenet.tisztit(valasz)) is not None


def pontoz(rekordok) -> dict:
    n = len(rekordok)
    jo = elf = elf_jo = igen = igen_jo = 0
    for r in rekordok:
        v = r["vart"]
        i = itelet.igen_nem(kimenet.tisztit(r.get("valasz")))
        jo += (i is True and v["y"] == 1) or (i is False and v["y"] == 0)
        if i is True:
            igen += 1
            igen_jo += v["y"] == 1
        if itelet.kotes_dontes(v["p"], True, v["targy"], i):
            elf += 1
            elf_jo += v["y"] == 1
    return {"pontszam": round(jo / n, 4) if n else 0.0, "pontossag": round(jo / n, 4) if n else 0.0,
            "igen": igen, "igen_pontossag": round(igen_jo / igen, 4) if igen else None,
            "lanc": {"elfogadva": elf, "elfogadva_helyes": elf_jo, "pontossag": round(elf_jo / elf, 4) if elf else None},
            "pozitiv": sum(r["vart"]["y"] for r in rekordok), "legacy": LEGACY}
