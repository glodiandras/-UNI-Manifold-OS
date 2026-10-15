"""A `tema` aranyhalmaz elkészítése (C20b; egyszeri, a legacy olvasott címkéiből). Csak olvas: a legacy alkalmazásmappájának másolatát
(`{state}/Manifold-media/itelet/`: `tema_meres.jsonl`, `cimkek.json`), a staging-klónt és a vaultot; az `arany.json`-t írja.

    bin/mos exec var/venv/bin/python -B modulok/eval/tema/keszit.py [--itelet <mappa>] [--ki modulok/eval/tema/arany.json]

A 118 forrás a legacy 2026-09-20-i mérésének populációja (a lánc témadöntésre váró irodalom- és nyelvtanvideói), a címke Claude
olvasása (2026-09-19, `cimkek.json`): elsődleges téma + elfogadható halmaz; 3 bibliai videónál nincs megfelelő téma (helyes: „egyik
sem”). A témalista a mostani vault tárgyankénti témáiból képződik (`itelet.temalista`), és befagyasztva kerül az aranyba: a mérés és
az éles lánc ugyanazt a promptot kapja. Az átirat nem kerül a repóba: az arany a staging forrásmappájára hivatkozik (út + a
`transcript.md` sha256-ja), a szöveget a mérés onnan képzi (`vaultoldal.vtt_stagingbol`).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ITT = Path(__file__).resolve().parent
REPO = ITT.parents[2]
sys.path.insert(0, str(REPO))

from core import config  # noqa: E402
from modulok.ytdlp import egyezes as X, itelet, staging  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--itelet")
    ap.add_argument("--ki", default=str(ITT / "arany.json"))
    a = ap.parse_args(argv)
    cfg = config.load()
    d = Path(a.itelet or cfg.path("video_jobs").parent / "itelet")
    meres = [json.loads(s) for s in (d / "tema_meres.jsonl").read_text(encoding="utf-8").splitlines() if s.strip()]
    cimkek = json.loads((d / "cimkek.json").read_text(encoding="utf-8"))
    idx = X.NoteIndex(cfg.path("vault"))
    gy = cfg.path("staging")
    targyak = sorted({r["targy"] for r in meres})
    temak = {t: itelet.temak_targyban(idx, t) for t in targyak}
    videok, hiany = [], []
    for r in meres:
        vid = r["azonosito"].split("-", 1)[1]
        m = staging.keres_azonosito(vid, gy)
        if not m:
            hiany.append(r["azonosito"])
            continue
        tr = Path(m) / "transcript.md"
        c = cimkek.get(r["azonosito"]) or {}
        videok.append({"id": r["azonosito"], "cim": r["cim"], "lap": r["lap"], "targy": r["targy"], "csoport": r["csoport"],
                       "tema": c.get("tema", r.get("tema")), "elfogadhato": c.get("elfogadhato") or r.get("elfogadhato") or [],
                       "staging": str(Path(m).relative_to(gy)), "atirat_sha256": hashlib.sha256(tr.read_bytes()).hexdigest(),
                       "lex_rang_top10": r.get("lex_rang_top10") or [], "cim_tema": r.get("cim_tema"),
                       "legacy": {"tartalom": r["itelet"].get("tartalom"), "metaadat": r["itelet"].get("metaadat"),
                                  "modell": r["itelet"].get("azonosito")}})
    arany = {"verzio": "v1", "allapot": "jovahagyott", "keszult": time.strftime("%Y-%m-%d"), "jovahagyva": time.strftime("%Y-%m-%d"),
             "ellenorzes": {"ki": "a C20b chat (Claude), a koordinátor felhatalmazásával",
                            "modszer": "a legacy olvasott címkéi (Claude, 2026-09-19: cím, a kiadó útvonala, a vault jegyzetcímei; 12 kétes "
                                       "videónál az átirat is) változatlanul; a 2026-09-20-i legacy mérés ezen a 118 forráson futott "
                                       "(A=B + lexikai kapu: 84/118 auto, szigorú 83/84, megengedő 84/84)"},
             "forras": "legacy {state}/Manifold-media/itelet/tema_meres.jsonl + cimkek.json (a 2.0 var/ C02-es klónja, csak olvasva)",
             "listak": {t: itelet.temalista(temak[t], idx) for t in targyak}, "temak": temak, "videok": videok}
    Path(a.ki).write_text(json.dumps(arany, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(videok)} videó → {a.ki}" + (f"; a stagingben nincs: {hiany}" if hiany else ""))
    return 1 if hiany else 0


if __name__ == "__main__":
    sys.exit(main())
