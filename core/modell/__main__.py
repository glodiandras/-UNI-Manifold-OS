"""`python -m core.modell <worker | bench | eval | lista | router>` — a `bin/mos` hívja."""
from __future__ import annotations

import argparse
import json
import sys

from .. import config


def _helyben(hub, repo: str) -> bool:
    return any((hub / f"models--{repo.replace('/', '--')}" / "snapshots").glob("*"))


def kalibracio_jelzes(r: dict) -> str:
    """Egy kalibrációs sor a `lista` kimenetében: `feladat:pont`, ✓ csak az érvényes, jóváhagyott (nem vázlat) kalibrált sorra;
    az érvénytelen (`ervenyes = 0`, pl. a C18.1 előtti, „elavult” sor) és a `-vazlat` verziójú sor pontja nem valódi mérés:
    jelölve látszik (`[érvénytelen]`, `[vázlat]`), a router nem használja."""
    from . import kalibracio
    ervenyes = bool(r.get("ervenyes", 1))
    vazlat = kalibracio.vazlat(r.get("aranyhalmaz_verzio") or "")
    jel = "✓" if r.get("kalibralt") and ervenyes and not vazlat else ""
    return f"{r['feladat']}:{r['pontszam']:.3g}{jel}" + ("[érvénytelen]" if not ervenyes else "") + ("[vázlat]" if vazlat else "")


def lista(argv: list[str]) -> int:
    from . import beallitas as B
    from . import kalibracio
    cfg = config.load()
    b = B.betolt(cfg)
    t = kalibracio.megnyit(cfg)
    kal = {}
    for r in t.tabla():
        kal.setdefault(r["modell"], []).append(kalibracio_jelzes(r))
    t.close()
    hub = b.models / "hub"
    munka = b.keret_gb("munka")
    print(f"{'név':<24} {'futtató':<22} {'csúcs':>6}  {'keret':<6} {'helyben':<8} kalibráció")
    for m in b.modellek.values():
        keret = "munka" if (m.csucs_gb or 0) <= munka else ("tavol" if (m.csucs_gb or 0) <= b.keret_gb("tavol") else "—")
        cs = f"{m.csucs_gb:g}{'*' if m.csucs_mert else ''}" if m.csucs_gb is not None else "?"
        jel = "igen" if _helyben(hub, m.repo) else "nincs"
        if m.konvertalas:
            jel += " (konv.)"
        print(f"{m.nev:<24} {m.futtato:<22} {cs:>6}  {keret:<6} {jel:<8} {' '.join(kal.get(m.nev, [])) or '—'}")
    for nev in sorted(set(kal) - set(b.modellek)):                      # a regiszterből kivett modell sorai
        print(f"{nev:<24} {'[nincs a regiszterben]':<22} {'':>6}  {'—':<6} {'—':<8} {' '.join(kal[nev])}")
    print("* mért csúcs (legacy); a többi becslés (C04). ✓ kalibrált (D9). [vázlat]: jóvá nem hagyott aranyhalmazon mért, "
          "[érvénytelen]: a mérés érvényességi kapuja nem engedte át — az ilyen pont nem valódi mérés, a router nem használja.")
    return 0


def router(argv: list[str]) -> int:
    from . import beallitas as B
    from . import kalibracio
    from .router import Router, RoutingHiba
    ap = argparse.ArgumentParser(prog="mos router")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tabla")
    v = sub.add_parser("valaszt")
    v.add_argument("feladat")
    v.add_argument("--keret", default="munka")
    a = ap.parse_args(argv)
    cfg = config.load()
    b = B.betolt(cfg)
    t = kalibracio.megnyit(cfg)
    try:
        if a.cmd == "tabla":
            sorok = t.tabla()
            print(json.dumps(sorok, ensure_ascii=False, indent=1) if sorok else "A kalibrációs tábla üres (a C19 tölti).")
            return 0
        try:
            from .halmaz import Verziok
            d = Router(b, t, verziok=Verziok(cfg.path("modulok"))).valaszt(a.feladat, b.keret_gb(a.keret))
        except RoutingHiba as exc:
            print(f"nincs döntés: {exc}")
            return 1
        print(json.dumps(d.publikus(), ensure_ascii=False))
        return 0
    finally:
        t.close()


def main(argv: list[str]) -> int:
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    if cmd == "worker":
        from . import worker
        return worker.main()
    if cmd == "bench":
        from . import bench
        return bench.main(rest)
    if cmd == "eval":
        from . import eval as ev
        return ev.main(rest)
    if cmd == "lista":
        return lista(rest)
    if cmd == "router":
        return router(rest)
    print("használat: python -m core.modell <worker | bench | eval | lista | router>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
