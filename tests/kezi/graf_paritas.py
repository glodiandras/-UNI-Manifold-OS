"""A legacy-paritás a VALÓDI vaulton, a C10.6 óta (CLAUDE.md 1. / 13. döntés; L42): a 2.0 gráfja a legacytől
**pontosan a dokumentált eltérésekben** tér el, és semmi másban.

    bin/mos exec var/venv/bin/python -B tests/kezi/graf_paritas.py      (a discover nem futtatja)

Csak olvas: a vaultot, és a legacy `modulok/eszkozok`-ot (alfolyamatban, `-B`-vel: a legacy fába bytecode sem
kerül; git-parancs a legacyben nem fut). Három kapu:
  1. a referencia-modell (`tests/legacy_szabaly.regi_graf`: a legacy szabály befagyasztott másolata) bájtra azonos
     a legacy `mfd.obsidian_graf`-fal — a másolat hű, tehát az eltéréseket valóban a legacyhez mérjük;
  2. a 2.0 lemezről számolt `feloldas.graf`-ja bájtra azonos a 2.0 indexének gráfjával (ideiglenes DB a `{tmp}`
     alatt, a végén törlődik);
  3. a régi és az új szabály linkenkénti eltérései (`legacy_szabaly.elteresek`) mind dokumentált osztályba esnek
     (K kis-nagybetű, S szegmenshatár, M-/M+/M* maszk); ismeretlen (`?`) nincs.
Előtte és utána a vault stat-lenyomata: ha közben változott (a felhasználó dolgozott), újrafut. A teljes
eltéréslista a `{runs}/graf-paritas-<idő>.json` riportba kerül (ebből készül a NAPLO bejegyzése).
"""
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import config  # noqa: E402
from _kornyezet import cfg_elkulonitve, legacy_eszkozok, legacy_graf, probamappa  # noqa: E402
from core.index import feloldas, indexelo  # noqa: E402
from tests import legacy_szabaly  # noqa: E402


def lenyomat(vault: Path) -> str:
    h = hashlib.sha256()
    for rp, lemez in feloldas.bejaras(vault):
        st = os.stat(vault / lemez)
        h.update(f"{rp}\0{st.st_size}\0{st.st_mtime_ns}\n".encode())
    return h.hexdigest()


def el(g: dict) -> int:
    return sum(len(v) for v in g["out"].values())


def main() -> int:
    cfg = config.load()
    vault = cfg.path("vault")
    eszk = legacy_eszkozok(cfg)
    if eszk is None:
        print("HIBA: a legacy mfd.py nem olvasható (a MOS_LEGACY a régi telepítés gyökerét jelöli ki)")
        return 2
    d = probamappa(cfg, "c106-paritas", szkript="graf_paritas.py")
    mert = False
    hibak = []
    for kor in range(1, 4):
        elotte = lenyomat(vault)
        t0 = time.perf_counter()
        lg = legacy_graf(eszk, vault)
        t_legacy = time.perf_counter() - t0
        rg = legacy_szabaly.regi_graf(vault)
        regi = feloldas.graf_kanonikus(rg)
        t0 = time.perf_counter()
        g = feloldas.graf(vault)
        lemez = feloldas.graf_kanonikus(g)
        t_lemez = time.perf_counter() - t0
        ix = indexelo.Index(cfg_elkulonitve(d / f"kor-{kor}", cfg))
        ix.figyelo_fajta = "lekerdezes"
        ix.lekerdezes_mp = 3600
        ix.indit()
        ix.var(300)
        idx = feloldas.graf_kanonikus(ix.graf())
        epites_ms = ix.allapot()["epites_ms"]
        ix.leallit()
        t0 = time.perf_counter()
        elt = legacy_szabaly.elteresek(vault)
        t_elt = time.perf_counter() - t0
        if lenyomat(vault) != elotte:
            print(f"{kor}. kör: a vault közben változott — újra")
            continue
        mert = True
        print(f"fájl {len(g['files'])}; index-építés {epites_ms} ms")
        print(f"  legacy szabály: él {el(rg)}, feloldatlan cél {len(rg['unresolved'])}, többértelmű alapnév "
              f"{len(rg['tobbertelmu'])}, canvas-hiba {len(rg['canvas_hiba'])}")
        print(f"  2.0 szabály:    él {el(g)}, feloldatlan cél {len(g['unresolved'])}, többértelmű alapnév "
              f"{len(g['tobbertelmu'])}, canvas-hiba {len(g['canvas_hiba'])}")
        for nev, b, t in (("legacy mfd.obsidian_graf", lg, t_legacy), ("referencia-modell", regi, None),
                          ("2.0 feloldas.graf", lemez, t_lemez), ("2.0 index", idx, None)):
            print(f"  {nev:26} {len(b):>9} bájt  sha256 {hashlib.sha256(b).hexdigest()}"
                  + (f"  {t:.2f} s" if t is not None else ""))
        if lg != regi:
            hibak.append("1. kapu: a referencia-modell NEM azonos a legacy gráffal")
        if lemez != idx:
            hibak.append("2. kapu: a 2.0 lemezről számolt gráfja NEM azonos az indexével")
        ossz = legacy_szabaly.osszesit(elt)
        print(f"  linkenkénti eltérés a legacy szabálytól: {len(elt)} {ossz or ''} ({t_elt:.2f} s)")
        for x in elt:
            print(f"    {x['osztaly']:2} {x['forras']}:{x['sor'] or '-'}  [[{x['cel']}]]  {x['regi']} → {x['uj']}  ({x['ok']})")
        if ossz.get("?"):
            hibak.append(f"3. kapu: {ossz['?']} nem osztályozható eltérés")
        if not elt and lg != lemez:
            hibak.append("3. kapu: a gráf eltér a legacytől, de linkenkénti eltérés nincs")
        riport = cfg.path("runs") / time.strftime("graf-paritas-%Y%m%d-%H%M%S.json")
        riport.parent.mkdir(parents=True, exist_ok=True)
        riport.write_text(json.dumps({
            "fajlok": len(g["files"]), "el_legacy": el(rg), "el_uj": el(g),
            "feloldatlan_legacy": sorted(rg["unresolved"].items()), "feloldatlan_uj": sorted(g["unresolved"].items()),
            "osszesites": ossz, "elteresek": elt, "hibak": hibak,
            "sha256": {"legacy": hashlib.sha256(lg).hexdigest(), "referencia": hashlib.sha256(regi).hexdigest(),
                       "lemez": hashlib.sha256(lemez).hexdigest(), "index": hashlib.sha256(idx).hexdigest()},
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  riport: {riport}")
        if hibak:
            for nev, b in (("legacy", lg), ("referencia", regi), ("lemez", lemez), ("index", idx)):
                (d / f"{nev}.json").write_bytes(b)
            print("\n".join(hibak))
            print(f"ELTÉR — a JSON-ok: {d}")
            return 1
        break
    shutil.rmtree(d)                                        # a saját var/tmp próbamappánk
    print("RENDBEN: a referencia-modell a legacy; a lemez és az index gráfja azonos; minden eltérés dokumentált"
          if mert else "NEM MÉRT: a vault minden körben változott")
    return 0 if mert else 3


if __name__ == "__main__":
    sys.exit(main())
