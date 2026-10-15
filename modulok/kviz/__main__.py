"""`bin/mos kviz …` — a kvíz parancssora (C22a; a `general` a C22b feladat-lépése).

- `ellenoriz JEGYZET`: egy kvízjegyzet elemzése a vaultban (csak olvas): kérdések, hibák, és hogy a kérdések idézete még ott
  áll-e a forrásjegyzetben (a sodródás: a jegyzet azóta megváltozott → új kvíz kell).
- `proba FORRÁS --forgatokonyv F.json [--n N]`: a lánc álmodellel (a forgatókönyv: `{"generalo": "<a modell válasza>",
  "tudas": {"<kérdés>": "<a helyesnek tartott válasz szövege>"}}`); a kvízjegyzetet kiírja, a vaultba nem ír.
- `general --ut JEGYZET [--modell M] [--proba]`: a feladat-lépés (C22b, a `kviz_general` feladattípus indítja): a modell a workeren
  át, az írás a core gépi-írás szolgáltatásán át (egy tétel, `Mos-Forras: mos-kviz`).
- `statisztika`: a „hibás a kérdés” jelölések modellenként (`tar.modell_statisztika`; csak olvas).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from pathlib import Path

from core import config
from core.vaultio import _H1_ELOTAG

from modulok.kapuk import forras as KF

from . import formatum as FM
from . import generalas as G


def _olvas(cfg, rp: str) -> tuple[str, Path]:
    vault = cfg.path("vault").resolve()
    p = (vault / rp).resolve()
    if not p.is_relative_to(vault) or not p.is_file():
        raise SystemExit(f"HIBA: nincs ilyen jegyzet a vaultban: {rp}")
    return p.read_text(encoding="utf-8"), p


def ellenoriz(cfg, a) -> int:
    szoveg, _ = _olvas(cfg, a.jegyzet)
    e = FM.elemez(szoveg, azon_tartalek="KVIZ-00000000-000000-kezi")
    ki: dict = {"hibak": e.hibak}
    rc = 1 if e.hibak else 0
    if e.kviz:
        k = e.kviz
        ki.update(azon=k.azon, forras=k.forras, modell=k.modell, keszult=k.keszult, kerdes=len(k.kerdesek))
        try:
            fs = KF.ForrasSzoveg.jegyzetbol(_olvas(cfg, k.forras + ".md")[0], cim=G.cim_of(k.forras + ".md"))
            ki["sodrodott"] = [q.id for q in k.kerdesek if fs.keres(q.idezet, 0.97) is None]
            rc = rc or int(bool(ki["sodrodott"]))
        except SystemExit:
            ki["forras_hianyzik"] = True
            rc = 1
    print(json.dumps(ki, ensure_ascii=False, indent=2))
    return rc


def proba(cfg, a) -> int:
    szoveg, p = _olvas(cfg, a.forras)
    f = json.loads(Path(a.forgatokonyv).read_text(encoding="utf-8"))
    tudas = f.get("tudas", {})

    def generalo(_prompt: str, _max: int) -> str:
        return f["generalo"]

    def ellenorzo(prompt: str, _max: int) -> str:
        m = re.search(r"KÉRDÉS: (.*)\n((?:[ABCD]\) .*\n?)+)", prompt)
        for betu, opcio in re.findall(r"([ABCD])\) (.*)", m.group(2)) if m else []:
            if opcio == tudas.get(m.group(1)):
                return betu
        return "nem egyértelmű"

    try:
        b = G.beallitas(cfg)
        if a.karakter_per_kerdes:
            b = dataclasses.replace(b, karakter_per_kerdes=a.karakter_per_kerdes)
        e = G.general(szoveg, a.forras, generalo, ellenorzo, n=a.n, modell="almodell", b=b,
                      log=lambda s: print(s, file=sys.stderr))
    except G.Megall as ex:
        print(f"HIBA: {ex}", file=sys.stderr)
        return 1
    print(FM.ir(e.kviz))
    print(json.dumps({"statisztika": e.statisztika, "elvetett": e.elvetett}, ensure_ascii=False, indent=2), file=sys.stderr)
    return 0


def general(cfg, a) -> int:
    """A feladat-lépés (C22b): egy kvíz a jegyzetből; hiba esetén 5-ös kilépés érthető üzenettel."""
    import os

    from core import gepi_kliens

    from . import lanc
    try:
        worker = lanc.Worker(cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"HIBA: a modell-worker nem érhető el: {exc}", file=sys.stderr)
        return 5
    allj = (lambda: bool(a.stop_fajl) and os.path.exists(a.stop_fajl))

    def halad(arany: float) -> None:
        print(f"[manifold-progress] {min(95, round(95 * arany))}%", flush=True)

    try:
        r = lanc.futtat(cfg, a.ut, gepi=gepi_kliens, worker=worker, proba=a.proba, modell=a.modell, n=a.n, allj=allj,
                        naplo=lambda s: print(s, flush=True), halad=halad)
    except (lanc.Megall, gepi_kliens.GepiHiba, ValueError, OSError) as exc:
        print(f"HIBA ({a.ut}): {exc}", file=sys.stderr, flush=True)
        return 5
    st = r["statisztika"]
    print(f"{r['kviz']}: {r['kerdesek']} kérdés · {r['modell']}" + (" (próba)" if r.get("proba") else "")
          + " · elvetve: " + (", ".join(f"{k} {v}" for k, v in sorted(st.get("elvetve", {}).items(), key=lambda x: -x[1])) or "—"),
          flush=True)
    print("[manifold-progress] 100%", flush=True)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


def statisztika(cfg, _a) -> int:
    from . import tar
    print(json.dumps(tar.modell_statisztika(cfg), ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="mos kviz", description="Kvíz egy jegyzetből (C22a, C22b)")
    al = ap.add_subparsers(dest="parancs", required=True)
    e = al.add_parser("ellenoriz", help="egy kvízjegyzet elemzése és sodródás-vizsgálata (csak olvas)")
    e.add_argument("jegyzet", help="a kvízjegyzet vault-relatív útja")
    p = al.add_parser("proba", help="a lánc álmodellel; a kvízjegyzet a kimenetre, a vaultba nem ír")
    p.add_argument("forras", help="a forrásjegyzet vault-relatív útja")
    p.add_argument("--forgatokonyv", required=True)
    p.add_argument("--n", type=int)
    p.add_argument("--karakter-per-kerdes", dest="karakter_per_kerdes", type=int,
                   help="felülírja a [kviz] karakter_per_kerdes-t (rövid próbajegyzethez: kisebb szám, több jelölt)")
    g = al.add_parser("general", help="kvíz egy jegyzetből a modellel (feladat-lépés: a core-on át ír)")
    g.add_argument("--ut", required=True)
    g.add_argument("--proba", action="store_true", help="az írás a vault APFS-klónjára (D9)")
    g.add_argument("--modell", help="kifejezett modell (csak próba, D9)")
    g.add_argument("--n", type=int, help="a kérdések száma (alap: [kviz] kerdes_alap)")
    g.add_argument("--stop-fajl")
    al.add_parser("statisztika", help="a „hibás a kérdés” jelölések modellenként (csak olvas)")
    a = ap.parse_args(argv)
    cfg = config.load()
    return {"ellenoriz": ellenoriz, "proba": proba, "general": general, "statisztika": statisztika}[a.parancs](cfg, a)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
