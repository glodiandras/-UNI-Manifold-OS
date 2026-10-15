"""A füzetlánc parancssora (C21): `bin/mos fuzet <parancs>`.

    lanc [ÚT…] [--proba] [--cel <jegyzet.md>] [--olvaso M] [--valaszto M] [--atirat M] [--max N] [--stop-fajl F]
        a figyelt mappák (vagy a megadott mappák/fájlok) új fotóinak köre; `--cel`: „Beszúrás az aktív jegyzetbe” (nincs választás)
    ellenoriz [--proba] [--limit N] [--olvaso M] [--valaszto M] [--stop-fajl F]
        a bekötött fotók újradöntése, eltérésnél átkötés (`mos-fuzet-ellenor`)
    allapot                      a lánc állapotának összesítője (JSON; csak olvas)
    kivag <kép> [--ki MAPPA]     a papírkivágás és az oldalképek próbája (modell nélkül; a `{tmp}` alá)

Az éles írás (`--proba` nélkül) csak a feladatsor lépéseként (MOS_FELADAT) indul; kézzel a `--proba` fut (a vault APFS-klónjára ír,
D9). A kifejezett modell (`--olvaso` …) mindig próba: a worker `proba: true`-val válaszol, a gépi írás élesben elutasítja.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

MODULOK = Path(__file__).resolve().parent.parent
for _ut in (MODULOK / "eval", MODULOK):
    if str(_ut) not in sys.path:
        sys.path.insert(0, str(_ut))
if str(MODULOK.parent) not in sys.path:
    sys.path.append(str(MODULOK.parent))

from core import config  # noqa: E402
from core import fuzet as F  # noqa: E402

from fuzet import kep  # noqa: E402
from fuzet.lanc import Lanc, Stop  # noqa: E402
from fuzet.modell import NincsModell  # noqa: E402

KERES_HIBA = 64


def _lanc(cfg, a) -> Lanc:
    kif = {"fuzet_fejezet": a.olvaso, "fuzet_valaszto": getattr(a, "valaszto", None), "ocr_kezi": getattr(a, "atirat", None)}
    if any(kif.values()) and not a.proba:
        raise SystemExit("kifejezett modell csak próbában (--proba) futhat (D9)")
    if not a.proba and not os.environ.get("MOS_FELADAT"):
        raise SystemExit("az éles írás csak a feladatsor lépéseként indul (a vezérlőből); kézzel: --proba")
    return Lanc(cfg, proba=a.proba, kifejezett=kif, cel=getattr(a, "cel", None), stop=Stop(a.stop_fajl),
                max_foto=getattr(a, "max", None))


def cmd_lanc(cfg, a) -> int:
    if a.cel and not (a.cel.endswith(".md") and (cfg.path("vault") / a.cel).is_file()):
        print(f"nincs ilyen jegyzet: {a.cel}", file=sys.stderr)
        return KERES_HIBA
    r = _lanc(cfg, a).futtat([Path(u).expanduser().resolve() for u in a.utak] or None)
    return 0 if not r["eredmeny"].get("hiba") or len(r["eredmeny"]) > 1 else 1


def cmd_ellenoriz(cfg, a) -> int:
    _lanc(cfg, a).ellenoriz(a.limit)
    return 0


def cmd_allapot(cfg, a) -> int:
    st = F.allapot_betolt(cfg)
    db: dict[str, int] = {}
    for r in st.values():
        db[r.get("allapot") or "?"] = db.get(r.get("allapot") or "?", 0) + 1
    print(json.dumps({"foto": len(st), "allapot": db, "figyelt_mappak": [str(m) for m in F.figyelt_mappak(cfg)]},
                     ensure_ascii=False, indent=1))
    return 0


def cmd_kivag(cfg, a) -> int:
    ki = Path(a.ki) if a.ki else cfg.path("tmp") / "fuzet-kivag"
    meta, utak = kep.oldalkepek(Path(a.kep), ki)
    print(json.dumps({**meta, "oldalak": [str(u) for u in utak]}, ensure_ascii=False, indent=1))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mos fuzet", description="füzetfotók bekötése a vault elméleti jegyzeteibe (C21)")
    sp = ap.add_subparsers(dest="cmd", required=True)
    for nev in ("lanc", "ellenoriz"):
        s = sp.add_parser(nev)
        s.add_argument("--proba", action="store_true")
        s.add_argument("--olvaso")
        s.add_argument("--valaszto")
        s.add_argument("--stop-fajl")
        if nev == "lanc":
            s.add_argument("utak", nargs="*")
            s.add_argument("--cel")
            s.add_argument("--atirat")
            s.add_argument("--max", type=int)
        else:
            s.add_argument("--limit", type=int)
    sp.add_parser("allapot")
    s = sp.add_parser("kivag")
    s.add_argument("kep")
    s.add_argument("--ki")
    a = ap.parse_args(argv)
    cfg = config.load()
    try:
        return {"lanc": cmd_lanc, "ellenoriz": cmd_ellenoriz, "allapot": cmd_allapot, "kivag": cmd_kivag}[a.cmd](cfg, a)
    except NincsModell as e:
        print(f"[füzet] {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
