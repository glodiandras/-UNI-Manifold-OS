"""`bin/mos kereses …` — a hibrid keresés CLI-je (C25b-mag). **Csak olvas**: a meglévő `vault.sqlite`-ot és (ha van) a
`vektor.sqlite`-ot nyitja olvasásra; indexet és vektortárat nem épít (az a core-é).

    bin/mos kereses hibrid "<kérdés>" [--limit N] [--mod hibrid|lexikai] [--json]
    bin/mos kereses allapot [--json]
    bin/mos kereses forrasok "<kérdés>" [--json]     a „Kérdezz a vaulttól” forrásvizsgálata (modell nélkül)
    bin/mos kereses meres [--json]                   a négy változat a kereses/parok.json párjain (ami nincs kötve: nem mért)

A CLI-ben nincs beágyazó és reranker (modellt nem tölt be, §4): a keresés lexikai, a mérés az FTS5-alapszintet adja. A
modellel kötött mérés a C25b modellfele (K160).

    python -m core.index.hibrid frissit [--stop-fajl F] [--max N]

A `vektorindex` feladat lépése (C25b, `core/vektorindex_feladat.py`): a feladatsor indítja a worker címével
(`MOS_WORKER_URL`), és csak ez írja a `vektor.sqlite`-ot; a beágyazó a router kalibrált `beagyazas` modellje, a kérések
`auto` módban (aktív használatkor szünetelnek, M3). A stop-fájl megjelenésekor jegyzethatáron áll meg.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _olvaso(cfg):
    from ..olvaso import fajl_olvaso
    return fajl_olvaso(Path(cfg.path("index")) / "vault.sqlite")


def _kereso(cfg):
    from . import kereso
    from .vektortar import NincsTar, Vektortar
    try:
        t = Vektortar(Path(cfg.path("index")) / "vektor.sqlite", csak_olvas=True)
    except NincsTar:
        t = None
    return kereso.HibridKereso(_olvaso(cfg), t, None, None, kereso.beallitas(cfg),
                               float(cfg.section("index").get("regex_idokorlat_mp", 2)))


def frissit(argv: list[str]) -> int:
    import os
    from ... import config
    from ...kereses_modell import WorkerBeagyazo, router_modell
    from ...modell import kliens
    from . import frissites
    from .vektortar import Vektortar
    ap = argparse.ArgumentParser(prog="mos kereses frissit", description="A vektorindex frissítése (a feladatsor lépése).")
    ap.add_argument("--stop-fajl", default=os.environ.get("MANIFOLD_STOP_FAJL"))
    ap.add_argument("--max", type=int, default=None)
    a = ap.parse_args(argv)
    cfg = config.load()
    try:
        u = kliens.url(cfg)
    except kliens.KliensHiba as e:
        print(f"kereses frissit: {e}", file=sys.stderr)
        return 1
    nev = router_modell(u, "beagyazas", "tavol")
    if not nev:
        print("kereses frissit: a routernek nincs kalibrált `beagyazas` modellje", file=sys.stderr)
        return 1
    b = WorkerBeagyazo(lambda: u, nev, mod="auto", feladat_id=os.environ.get("MOS_FELADAT"))
    tar = Vektortar(Path(cfg.path("index")) / "vektor.sqlite")
    try:
        e = frissites.frissit(_olvaso(cfg), tar, b, folytathat=lambda: not (a.stop_fajl and os.path.exists(a.stop_fajl)),
                              max_jegyzet=a.max)
    finally:
        tar.close()
    print(json.dumps(e.to_dict(), ensure_ascii=False))
    return 1 if e.hibak else 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["frissit"]:
        return frissit(argv[1:])
    from ... import config
    from ...vaultio import Invalid
    from ..indexelo import NemKesz
    ap = argparse.ArgumentParser(prog="mos kereses", description="Hibrid keresés (csak olvas).")
    al = ap.add_subparsers(dest="parancs", required=True)
    h = al.add_parser("hibrid")
    h.add_argument("q")
    h.add_argument("--limit", type=int, default=20)
    h.add_argument("--mod", default="hibrid")
    f = al.add_parser("forrasok")
    f.add_argument("q")
    al.add_parser("allapot")
    al.add_parser("meres")
    for p in al.choices.values():
        p.add_argument("--json", action="store_true", help="géppel olvasható kimenet")
    a = ap.parse_args(argv)
    cfg = config.load()
    try:
        k = _kereso(cfg)
        if a.parancs == "hibrid":
            r = k.keres(a.q, a.limit, a.mod)
            sorok = [f"{i:>3}. {t['ut']}  {t.get('agak', '')}" for i, t in enumerate(r["talalatok"], 1)]
            fej = f"{r['mod']} ({r.get('ok') or 'rendben'}): {r['osszes']}{'+' if r['legalabb'] else ''} találat"
        elif a.parancs == "allapot":
            r = k.tar.allapot() if k.tar is not None else {"van": False}
            r["miert_lexikai"] = k.miert_lexikai()
            fej, sorok = json.dumps(r, ensure_ascii=False), []
        elif a.parancs == "forrasok":
            from . import kerdezz
            r = kerdezz.valaszol(a.q, k, None, b=kerdezz.beallitas(cfg), prof=kerdezz.profil(cfg))
            fej = f"{r['allapot']}: {len(r['forrasok'])} forrás"
            sorok = [f"[{x['szam']}] {x['ut']} {' › '.join(x['fejezet'])} (sor {x['sor_kezd']}–{x['sor_veg']}, "
                     f"fedés {x['fedes']})" for x in r["forrasok"]]
        else:
            from modulok.eval.kereses import hibrid as meres
            import korpusz
            parok = korpusz.parok()
            r = meres.futtat(k, parok["parok"], halmaz=parok.get("verzio"))
            fej = f"halmaz {r['halmaz']}, {r['parok']} pár; döntés: {r['dontes']}"
            sorok = [f"{v}: " + (json.dumps({m: x.get(m) for m in ('recall1', 'recall5', 'recall10', 'mrr')})
                                 if "nem_mert" not in x else f"nem mért ({x['nem_mert']})")
                     for v, x in r["valtozatok"].items()]
    except (NemKesz, Invalid) as e:
        print(f"kereses: {e}", file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(fej)
        for s in sorok:
            print(s)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
