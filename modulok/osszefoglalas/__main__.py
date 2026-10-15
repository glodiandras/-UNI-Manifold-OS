"""`bin/mos osszefoglalas …` — az összefoglaló parancssora (C26a: a mag, csak olvas; C26b: `general`, `meres`).

- `general --szint jegyzet|mappa|video --ut X [--ut …] [--automatikus] [--proba] [--modell M] [--kiegeszit] [--stop-fajl F]`:
  az éles lánc (a feladat-lépés: a modellt a workeren át hívja, a vaultba a core gépi-írás szolgáltatásán át ír; a `MOS_CORE_URL`
  a feladatsortól jön). Egy összefoglaló = egy tétel = egy gépi commit.
- `meres --modell M [--keret munka|tavol] --ki JELENTES.json [--limit N]`: az éles lánc mérése a C18 `szoveg` aranyhalmazon
  (a vaultba nem ír).

- `ellenoriz JEGYZET`: egy összefoglaló-jegyzet elemzése a vaultban: állítások, hibák, és hogy az idézetek még ott állnak-e a
  forrásban (`sodrodott`: a jegyzet azóta megváltozott), a horgonyok léteznek-e (`horgony_hianyzik`).
- `proba FORRÁS --forgatokonyv F.json [--max-allitas N]`: a lánc álhívóval (a forgatókönyv: `{"hivo": "<a modell válasza
  minden hívásra>"}` vagy `{"valaszok": ["<1. hívás válasza>", …]}`); az összefoglaló a kimenetre, a statisztika a hibakimenetre.
- `kontextus JEGYZET… [--max-karakter N] [--kerdes S] [--valasz FÁJL]`: a kontextus-csomag a kimenetre (az azonosító → út
  leképezés a hibakimenetre); `--valasz`-zal a visszamásolt külső AI-válasz feldolgozása: a kapun átment `## Állítások` blokk a
  kimenetre (kézi beillesztéshez), az elvetettek a hibakimenetre.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from core import config
from core.index import elemzo

from . import formatum as FM
from . import kontextus as KX
from . import lanc as L
from . import szakaszolas as SZ


def _olvas(cfg, rp: str) -> str:
    vault = cfg.path("vault").resolve()
    p = (vault / rp).resolve()
    if not p.is_relative_to(vault) or not p.is_file():
        raise SystemExit(f"HIBA: nincs ilyen jegyzet a vaultban: {rp}")
    return p.read_text(encoding="utf-8")


def _bemenet(cfg, rp: str, b: L.Beallitas) -> tuple[SZ.Bemenet, str]:
    """A forrásjegyzet → `Bemenet` az index-tábláival (a core elemzőjéből: az index nem nyílik meg)."""
    md = _olvas(cfg, rp)
    j = elemzo.elemez(md)
    return SZ.jegyzet_bemenet(md, rp.removesuffix(".md"), FM.cim_of(rp), j.fejezetek, j.blokkok,
                              b.darab_max_karakter, b.szakasz_min_karakter), md


def ellenoriz(cfg, a) -> int:
    from . import ellenorzes as EL
    vault = cfg.path("vault").resolve()

    def olvas(rp: str):
        p = (vault / rp).resolve()
        return p.read_text(encoding="utf-8") if p.is_relative_to(vault) and p.is_file() else None

    def letezik(rp: str) -> bool:
        p = (vault / rp).resolve()
        return p.is_relative_to(vault) and p.is_file()

    ki, rc = EL.vizsgal(_olvas(cfg, a.jegyzet), olvas, letezik, L.beallitas(cfg))
    ki.pop("reszletek", None)
    ki.pop("cim", None)
    print(json.dumps(ki, ensure_ascii=False, indent=2))
    return rc


def proba(cfg, a) -> int:
    b = L.beallitas(cfg)
    f = json.loads(Path(a.forgatokonyv).read_text(encoding="utf-8"))
    valaszok = list(f.get("valaszok", []))

    def hivo(_prompt: str, _max: int) -> str:
        return valaszok.pop(0) if valaszok else f.get("hivo", "")

    bem, _ = _bemenet(cfg, a.forras, b)
    try:
        e = L.osszefoglal(bem, hivo, "almodell", FM.cim_of(a.forras), b=b, p=L.profil(cfg), max_allitas=a.max_allitas,
                          log=lambda s: print(s, file=sys.stderr))
    except L.Megall as ex:
        print(f"HIBA: {ex}", file=sys.stderr)
        return 1
    print(FM.ir(e.osszefoglalo))
    print(json.dumps({"statisztika": e.statisztika, "elvetett": e.elvetett, "uj_horgonyok": e.uj_horgonyok},
                     ensure_ascii=False, indent=2), file=sys.stderr)
    return 0


def kontextus(cfg, a) -> int:
    b = L.beallitas(cfg)
    jegyzetek = [KX.Jegyzet(rp, _olvas(cfg, rp)) for rp in a.jegyzetek]
    try:
        cs = KX.csomag(jegyzetek, a.max_karakter or b.kontextus_max_karakter, a.kerdes or "")
    except L.Megall as ex:
        print(f"HIBA: {ex}", file=sys.stderr)
        return 1
    if not a.valasz:
        print(cs.szoveg)
        print(json.dumps({"azonositok": cs.azonositok, "benne": cs.benne, "csonkolt": cs.csonkolt, "kihagyott": cs.kihagyott,
                          "karakter": cs.karakter}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 0
    e = KX.valasz_feldolgoz(Path(a.valasz).read_text(encoding="utf-8"), jegyzetek, b=b, p=L.profil(cfg))
    print(json.dumps({"statisztika": e.statisztika, "elvetett": e.elvetett}, ensure_ascii=False, indent=2), file=sys.stderr)
    if not e.osszefoglalo.allitasok:
        print("HIBA: egyetlen állítás sem ment át a forráshűség-kapun", file=sys.stderr)
        return 1
    print(FM.torzs(e.osszefoglalo))
    return 0


def general(cfg, a) -> int:
    """A feladat-lépés (C26b): összefoglaló a megadott utakhoz, utanként egy gépi tétel (egy kör). Az automatikus módban egy út hibája
    a többit nem állítja meg; a kézi (egy út) hibája 5-ös kilépés érthető üzenettel."""
    from core import gepi_kliens

    from . import futtat as F
    try:
        worker = F.Worker(cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"HIBA: a modell-worker nem érhető el: {exc}", file=sys.stderr)
        return 5
    osszes, hibak = [], 0
    allj = (lambda: bool(a.stop_fajl) and os.path.exists(a.stop_fajl))
    for i, ut in enumerate(a.ut):
        if allj():
            print("Leállítva (a következő előtt).", flush=True)
            break
        try:
            r = F.futtat(cfg, a.szint, ut, gepi=gepi_kliens, worker=worker, automatikus=a.automatikus, proba=a.proba, modell=a.modell,
                         kiegeszit=a.kiegeszit, allj=allj, naplo=lambda s: print(s, flush=True))
        except (L.Megall, gepi_kliens.GepiHiba, ValueError, OSError) as exc:
            hibak += 1
            print(f"HIBA ({ut}): {exc}", file=sys.stderr, flush=True)
            if not a.automatikus:
                return 5
            continue
        osszes.append(r)
        print(f"{ut}: {r['allapot']} · {r.get('allitasok', 0)} állítás" + (" (próba)" if r.get("proba") else ""), flush=True)
        print(f"[manifold-progress] {round(100 * (i + 1) / len(a.ut))}%", flush=True)
    print(json.dumps({"osszefoglalok": osszes, "hibak": hibak}, ensure_ascii=False, indent=2))
    return 0 if osszes or not hibak else 5


def meres(cfg, a) -> int:
    from . import meres as M
    return M.main(a)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="mos osszefoglalas", description="Összefoglalás és kontextus-csomag (C26a, modell nélkül)")
    al = ap.add_subparsers(dest="parancs", required=True)
    e = al.add_parser("ellenoriz", help="egy összefoglaló-jegyzet elemzése és sodródás-vizsgálata (csak olvas)")
    e.add_argument("jegyzet", help="az összefoglaló-jegyzet vault-relatív útja")
    p = al.add_parser("proba", help="a lánc álhívóval; az összefoglaló a kimenetre, a vaultba nem ír")
    p.add_argument("forras", help="a forrásjegyzet vault-relatív útja")
    p.add_argument("--forgatokonyv", required=True)
    p.add_argument("--max-allitas", dest="max_allitas", type=int)
    k = al.add_parser("kontextus", help="a külső AI-nak szánt csomag, és a visszamásolt válasz feldolgozása (csak olvas)")
    k.add_argument("jegyzetek", nargs="+", help="a jegyzetek vault-relatív útjai")
    k.add_argument("--max-karakter", dest="max_karakter", type=int)
    k.add_argument("--kerdes")
    k.add_argument("--valasz", help="a külső AI visszamásolt válaszát tartalmazó fájl")
    g = al.add_parser("general", help="az éles lánc (feladat-lépés: a core-on át ír)")
    g.add_argument("--szint", choices=("jegyzet", "mappa", "video"), default="jegyzet")
    g.add_argument("--ut", action="append", required=True)
    g.add_argument("--automatikus", action="store_true")
    g.add_argument("--proba", action="store_true", help="az írás a vault APFS-klónjára (D9)")
    g.add_argument("--modell", help="kifejezett modell (csak próba, D9)")
    g.add_argument("--kiegeszit", action="store_true", help="mappa-szint: a hiányzó jegyzet-összefoglalókat előbb elkészíti")
    g.add_argument("--stop-fajl")
    m = al.add_parser("meres", help="az éles lánc mérése a C18 `szoveg` aranyhalmazon")
    m.add_argument("--modell", required=True)
    m.add_argument("--keret", default=None, help="munka | tavol (saját worker a keret-felülírással)")
    m.add_argument("--ki", required=True)
    m.add_argument("--limit", type=int)
    a = ap.parse_args(argv)
    cfg = config.load()
    return {"ellenoriz": ellenoriz, "proba": proba, "kontextus": kontextus, "general": general, "meres": meres}[a.parancs](cfg, a)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
