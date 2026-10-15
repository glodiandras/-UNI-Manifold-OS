"""Soronkénti lefedettség a `core/` Python-kódjára, letöltés nélkül (C33, T185; a stdlib `sys.monitoring`, Python ≥ 3.12).

    bin/mos exec <python> -B tests/kezi/lefedettseg.py [tests.test_x …] [--min 0]

A megadott tesztmodulokat (alap: a teljes `tests/` discover) folyamaton belül futtatja, és a `core/` minden fájljára
megszámolja, a végrehajtható sorai (a lefordított kódobjektumok `co_lines()`-a) közül melyik futott. A `LINE` esemény
soronként egyszer jelez (utána `DISABLE`), így a futás csak kissé lassabb. Kimenet: fájlonkénti arány, és a
`{runs}/lefedettseg-<idő>.json`. A vitest-oldali lefedettséghez a `@vitest/coverage-v8` csomag kellene (D3: új letöltés,
jóváhagyásra vár — K-tétel); ez a Python-oldal.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import config  # noqa: E402

CORE = REPO / "core"


def vegrehajthato(ut: Path) -> set[int]:
    """A fájl végrehajtható sorai: a modul és minden beágyazott kódobjektum `co_lines()`-a."""
    try:
        kod = compile(ut.read_text(encoding="utf-8"), str(ut), "exec")
    except (SyntaxError, UnicodeDecodeError):
        return set()
    sorok: set[int] = set()
    verem = [kod]
    while verem:
        c = verem.pop()
        sorok.update(s for _, _, s in c.co_lines() if s is not None)
        verem.extend(k for k in c.co_consts if isinstance(k, types.CodeType))
    return sorok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Soronkénti lefedettség a core/-ra (sys.monitoring).")
    ap.add_argument("modulok", nargs="*", help="tesztmodulok (alap: a teljes tests/ discover)")
    ap.add_argument("--min", type=float, default=0.0, help="a teljes arány alsó korlátja (%%; alap 0: csak jelentés)")
    a = ap.parse_args(argv)
    mon = sys.monitoring
    eszkoz = mon.COVERAGE_ID
    mon.use_tool_id(eszkoz, "manifold-lefedettseg")
    futott: dict[str, set[int]] = {}
    gyoker = str(CORE) + "/"

    def sor(kod, sorszam):
        f = kod.co_filename
        if f.startswith(gyoker):
            futott.setdefault(f, set()).add(sorszam)
        return mon.DISABLE
    mon.register_callback(eszkoz, mon.events.LINE, sor)
    mon.set_events(eszkoz, mon.events.LINE)
    try:
        betolto = unittest.TestLoader()
        keszlet = (betolto.loadTestsFromNames(a.modulok) if a.modulok
                   else betolto.discover(str(REPO / "tests"), top_level_dir=str(REPO)))
        eredmeny = unittest.TextTestRunner(verbosity=0).run(keszlet)
    finally:
        mon.set_events(eszkoz, 0)
        mon.register_callback(eszkoz, mon.events.LINE, None)
        mon.free_tool_id(eszkoz)
    fajlok = {}
    ossz_v = ossz_f = 0
    for p in sorted(CORE.rglob("*.py")):
        v = vegrehajthato(p)
        if not v:
            continue
        f = len(v & futott.get(str(p), set()))
        ossz_v += len(v)
        ossz_f += f
        fajlok[str(p.relative_to(REPO))] = {"sorok": len(v), "futott": f, "arany": round(100 * f / len(v), 1)}
    teljes = round(100 * ossz_f / max(ossz_v, 1), 1)
    for nev, d in sorted(fajlok.items(), key=lambda x: x[1]["arany"])[:25]:
        print(f"  {d['arany']:5.1f}%  {d['futott']:5d}/{d['sorok']:<5d} {nev}")
    print(f"[lefedettség] a core/ {len(fajlok)} fájlja: {ossz_f}/{ossz_v} sor = {teljes}% "
          f"(tesztek: {eredmeny.testsRun}, hiba: {len(eredmeny.failures) + len(eredmeny.errors)})")
    cfg = config.load()
    runs = cfg.path("runs")
    runs.mkdir(parents=True, exist_ok=True)
    cel = runs / time.strftime("lefedettseg-%Y%m%d-%H%M%S.json")
    cel.write_text(json.dumps({"ido": time.strftime("%Y-%m-%dT%H:%M:%S"), "modulok": a.modulok or ["discover"],
                               "teljes": teljes, "fajlok": fajlok}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[lefedettség] {cel}")
    return 0 if teljes >= a.min and eredmeny.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
