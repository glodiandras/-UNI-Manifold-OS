"""`bin/mos kapu …` — a közös forráshűség-kapu parancssora (a modellt nem hív, a vaultba nem ír).

- `meres [--irj FÁJL] [--mag N] [--jegyzetek N]`: a küszöbök mérése a `szoveg` halmazon (~1–2 perc); a riportot kiírja
  vagy a `--irj` fájlba teszi (`docs/C22-KAPU-MERES.md`); kilépési kód 0, ha a 90%-os pozitív padló tartható, különben 1.
- `minta [--darab N] [--ki FÁJL]`: az átnézési lap (a küszöb két oldaláról N-N eset).
- `ellenoriz JEGYZET --idezet … --allitas … [--profil NÉV]`: egy állítás vizsgálata egy vault-jegyzeten (csak olvas).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from core import config
from core.vaultkivul import vaultban_van
from core.vaultio import _H1_ELOTAG

from . import forras as F
from . import huseg as H
from . import meres as M


def _kiir(szoveg: str, ut: str | None, cfg=None) -> None:
    if not ut:
        print(szoveg)
        return
    cel = Path(ut).resolve()
    if cfg is not None and vaultban_van(cel, cfg.path("vault")):
        raise SystemExit("HIBA: a riport nem kerülhet a vaultba")
    cel.parent.mkdir(parents=True, exist_ok=True)
    cel.write_text(szoveg + "\n", encoding="utf-8")
    print(f"kiírva: {cel}", file=sys.stderr)


def meres(a) -> int:
    cfg = config.load()
    h, merdek, p, mutatok, padlo = M.futtat(a.mag, a.jegyzetek)
    parancs = "bin/mos kapu meres" + (f" --irj {a.irj}" if a.irj else "") + (f" --mag {a.mag}" if a.mag != 1 else "")
    _kiir(M.riport(h, merdek, p, mutatok, padlo, parancs, date.today().isoformat()), a.irj, cfg)
    print(f"\nkiválasztva:\n{M.profil_szoveg(p)}\npadló: {padlo}  {json.dumps(mutatok)}", file=sys.stderr)
    return 0 if padlo >= M.PADLO else 1


def minta(a) -> int:
    cfg = config.load()
    h = M.halmaz(None, a.mag, a.jegyzetek)
    merdek = M.merj_esetek(h)
    p = H.profil(cfg)
    p = H.Profil(**{**p.__dict__, "idezet_min_szo": 1, "idezet_max_szo": None})
    ut = a.ki or str(cfg.path("tmp") / "c22-kapu-minta.md")
    _kiir(M.minta_lap(merdek, p, h, a.darab), ut, cfg)
    return 0


def ellenoriz(a) -> int:
    cfg = config.load()
    vault = cfg.path("vault").resolve()
    ut = (vault / a.jegyzet).resolve()
    if not ut.is_relative_to(vault) or not ut.is_file():
        print(f"HIBA: nincs ilyen jegyzet a vaultban: {a.jegyzet}", file=sys.stderr)
        return 2
    cim = _H1_ELOTAG.sub("", ut.stem)
    fs = F.ForrasSzoveg.jegyzetbol(ut.read_text(encoding="utf-8"), cim=cim)
    v = H.ellenoriz(fs, a.allitas, a.idezet, H.profil(cfg, a.profil))
    d = v.to_dict()
    if v.hely:
        d["mondat"] = fs.mondat(*v.hely)
        d["szakasz_cim"] = fs.szakaszok[v.szakasz].cim
    print(json.dumps(d, ensure_ascii=False, indent=2))
    return 0 if v.ok else 1


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="mos kapu", description="Közös forráshűség-kapu")
    al = ap.add_subparsers(dest="parancs", required=True)
    m = al.add_parser("meres", help="a küszöbök mérése a szoveg halmazon")
    m.add_argument("--irj", help="a riport fájlja (alap: kiírja)")
    m.add_argument("--mag", type=int, default=1)
    m.add_argument("--jegyzetek", type=int, help="csak az első N jegyzet (gyors próba)")
    n = al.add_parser("minta", help="az átnézési lap (a küszöb két oldaláról N-N eset)")
    n.add_argument("--darab", type=int, default=10)
    n.add_argument("--ki")
    n.add_argument("--mag", type=int, default=1)
    n.add_argument("--jegyzetek", type=int)
    e = al.add_parser("ellenoriz", help="egy állítás vizsgálata egy vault-jegyzeten (csak olvas)")
    e.add_argument("jegyzet", help="vault-relatív út")
    e.add_argument("--idezet", required=True)
    e.add_argument("--allitas", required=True)
    e.add_argument("--profil", choices=H.FOGYASZTOK)
    a = ap.parse_args(argv)
    return {"meres": meres, "minta": minta, "ellenoriz": ellenoriz}[a.parancs](a)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
