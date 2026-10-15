"""A `kotes` aranyhalmaz elkészítése (C20b; egyszeri, a legacy olvasott címkéiből). Csak olvas: a legacy alkalmazásmappájának másolata
(`{state}/Manifold-media/itelet/`: `n_kotes_minta.json` + `n_cimkek.json`, `n_kotes_minta_2.json` + `n_cimkek_2.json`); az `arany.json`-t írja.

    bin/mos exec var/venv/bin/python -B modulok/eval/kotes/keszit.py [--itelet <mappa>] [--ki modulok/eval/kotes/arany.json]

A 141 pár a magyar nyelvi (N) videók TELJES saját témájú kötés-populációja (a legacy `media_link.kotes` szerint), mind olvasva
(Claude, 2026-09-20: 25, 2026-09-23: 116): 1 = az ablak elmagyarázza a jegyzet tartalmát, 0 = csak említi vagy másról szól. Az ablak
és a jegyzetrészlet szövege a mintafájlokból jön (a legacy ugyanezt mutatta a modellnek), így a halmaz a vaulttól független.
A legacy T-tárgyú 320 elemű mérése (`kotes_meres.jsonl`) szöveg nélküli (a vault régi állapotából képződött): nem kerül át.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ITT = Path(__file__).resolve().parent
sys.path.insert(0, str(ITT.parents[2]))

from core import config  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--itelet")
    ap.add_argument("--ki", default=str(ITT / "arany.json"))
    a = ap.parse_args(argv)
    d = Path(a.itelet or config.load().path("video_jobs").parent / "itelet")
    parok = []
    for minta, cimkek, ido in (("n_kotes_minta.json", "n_cimkek.json", "2026-09-20"), ("n_kotes_minta_2.json", "n_cimkek_2.json", "2026-09-23")):
        m = json.loads((d / minta).read_text(encoding="utf-8"))
        c = json.loads((d / cimkek).read_text(encoding="utf-8"))
        indok = c.get("nemleges_indok") or c.get("indoklas") or {}
        if len(m) != len(c["cimkek"]):
            raise SystemExit(f"a minta és a címkék száma eltér: {minta}")
        for i, (p, y) in enumerate(zip(m, c["cimkek"]), 1):
            parok.append({"id": f"{Path(minta).stem}-{i:03d}", "azonosito": p["azonosito"], "video": p["video"], "tema": p["tema"],
                          "jegyzet": p["jegyzet"], "jegyzet_cim": p["jegyzet_cim"], "t": p["t"], "p": p["p"],
                          "ablak_szoveg": p["ablak_szoveg"], "jegyzet_reszlet": p["jegyzet_reszlet"], "y": int(y),
                          "indok": indok.get(str(i)), "olvasva": ido})
    arany = {"verzio": "v1", "allapot": "jovahagyott", "keszult": time.strftime("%Y-%m-%d"), "jovahagyva": time.strftime("%Y-%m-%d"),
             "ellenorzes": {"ki": "a C20b chat (Claude), a koordinátor felhatalmazásával",
                            "modszer": "a legacy olvasott címkéi változatlanul (Claude, 2026-09-20 és 2026-09-23, a gazda döntése: "
                                       "„Claude, egyszeri alkalommal”); a legacy mérése ezen a populáción: p ≥ 0,90 és „igen” → 45/45"},
             "forras": "legacy {state}/Manifold-media/itelet/n_kotes_minta*.json + n_cimkek*.json (a 2.0 var/ C02-es klónja, csak olvasva)",
             "parok": parok}
    Path(a.ki).write_text(json.dumps(arany, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(parok)} pár ({sum(p['y'] for p in parok)} pozitív) → {a.ki}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
