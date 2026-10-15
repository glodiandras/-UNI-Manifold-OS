"""C10 kész-feltétele: a link-feloldás API-ja a VALÓDI vaulton ugyanazt adja, mint a C06 gráfja (L42), és a
fejezet-/blokk-horgonyok illesztésének mérése (csak olvas; a discover nem futtatja).

    bin/mos exec var/venv/bin/python -B tests/kezi/link_feloldas_paritas.py

1. Az index minden link-sorára az új `Index.feloldas` ugyanazt a célt adja, mint a tárolt (a gráfhoz használt)
   `cel` — 0 eltérés a kapu. (A bájtos gráf-paritást a `graf_paritas.py` méri; ez a feloldás-API-t.)
2. A `[[Jegyzet#Fejezet]]` és `[[Jegyzet#^blokk]]` linkek: a cél jegyzetben megtalálható-e a horgony a
   `beagyazas` szabályával (az Obsidian pontos szabálya nem mérhető, ez a közelítés találati aránya). A nem
   találtakból mintát ír; a média-horgonyokat (`page=`, `t=`) külön számolja. Mérés (2026-10-01): a valódi
   vaultban NINCS fejezet- vagy blokk-link, csak PDF `#page=N` (4195) és videó `#t=` (1074) horgony; a
   fejezet/blokk-illesztést ezért csak az álvaulti tesztek védik.
Az index ideiglenes DB-ben épül (`{tmp}`), a végén törlődik.
"""
import collections
import json
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import config  # noqa: E402
from _kornyezet import cfg_elkulonitve, probamappa  # noqa: E402
from core.index import indexelo  # noqa: E402


def main() -> int:
    cfg = config.load()
    d = probamappa(cfg, "c10-feloldas", szkript="link_feloldas_paritas.py")
    ix = indexelo.Index(cfg_elkulonitve(d, cfg))
    ix.figyelo_fajta = "lekerdezes"
    ix.lekerdezes_mp = 3600
    ix.indit()
    ix.var(300)
    hibak = 0
    try:
        sorok = ix.link_sorok()
        t0 = time.perf_counter()
        csoport = collections.defaultdict(list)
        for r in sorok:
            csoport[r["forras"]].append(r)
        eltero = []
        for forras, lista in csoport.items():
            for r, e in zip(lista, ix.feloldas(forras, [x["cel_nyers"] or "" for x in lista])):
                if e["ut"] != r["cel"]:
                    eltero.append((forras, r["cel_nyers"], r["cel"], e["ut"]))
        print(f"1. feloldás-paritás: {len(sorok)} link, {len(csoport)} forrás, eltérés: {len(eltero)} "
              f"({time.perf_counter() - t0:.2f} s)")
        for x in eltero[:10]:
            print("   ELTÉR", x)
        hibak += bool(eltero)

        stat = collections.Counter()
        nem = []
        with ix._olvaso() as c:
            horgonyok = c.execute("SELECT f.ut, l.cel_nyers, l.alcel, l.cel FROM link l JOIN fajl f ON f.id = l.forras_id "
                                  "WHERE l.alcel IS NOT NULL AND l.alcel != '' AND l.cel IS NOT NULL AND f.torolve IS NULL").fetchall()
        t0 = time.perf_counter()
        for forras, cel, alcel, ut in horgonyok:
            if not ut.lower().endswith(".md"):
                stat[f"nem jegyzet: {ut.rsplit('.', 1)[-1].lower()} #{alcel.split('=')[0]}= (a felületé: C16)"] += 1
                continue
            b = ix.beagyazas(forras, cel, alcel)
            fajta = "blokk" if alcel.startswith("^") else "fejezet"
            if b.get("alcel_hiba"):
                stat[f"{fajta}: nincs találat"] += 1
                if len(nem) < 40:
                    nem.append({"forras": forras, "cel": ut, "alcel": alcel})
            else:
                stat[f"{fajta}: megtalálva"] += 1
        print(f"2. horgony-illesztés a valódi vaulton ({len(horgonyok)} horgonyos link, {time.perf_counter() - t0:.2f} s):")
        for k, v in sorted(stat.items()):
            print(f"   {k:48} {v}")
        for x in nem[:15]:
            print("   nem találta:", x["forras"], "→", x["cel"], "#" + x["alcel"])
        riport = cfg.path("runs") / time.strftime("link-feloldas-%Y%m%d-%H%M%S.json")
        riport.parent.mkdir(parents=True, exist_ok=True)
        riport.write_text(json.dumps({"linkek": len(sorok), "eltero": eltero, "horgony": dict(stat), "nem_talalt_minta": nem},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"   riport: {riport}")
    finally:
        ix.leallit()
        shutil.rmtree(d)
    print("RENDBEN: a feloldás-API a gráf feloldásával azonos" if not hibak else "ELTÉR")
    return hibak


if __name__ == "__main__":
    sys.exit(main())
