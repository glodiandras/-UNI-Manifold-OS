"""`bin/mos kartya …` — a kártyamag parancssora (C23a; a felület és a végpontok a C23b-ben).

- `ellenoriz`: a kártyamappa elemzése (a vaulthoz csak olvasva): kártyák, hibák; a DB-hez nem nyúl.
- `szinkron`: a kártyamappa → `tanulas.sqlite` (a vaultba nem ír).
- `export [CÉL.apkg]`: a kártyák és az FSRS-állapot Anki-csomagba (alap: `{szemelyes}/export/manifold-kartyak-<idő>.apkg`).
- `import FÁJL.apkg --proba`: a csomag beolvasása és jelentés; a DB-hez és a vaulthoz nem nyúl (az éles import a C23b:
  előbb a kísérőjegyzet gépi írása, utána az állapot).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from core import config
from core.vaultkivul import vaultban_van
from core.index import feloldas

from . import apkg, html, szinkron, utemezo


def _lepesszam(cfg) -> tuple[int, int]:
    b = szinkron.beallitas(cfg)
    return (len(utemezo.lepesek(b.get("tanulasi_lepesek", ["1m", "10m"]))),
            len(utemezo.lepesek(b.get("ujratanulasi_lepesek", ["10m"]))))


def _kiir(d) -> None:
    print(json.dumps(d, ensure_ascii=False, indent=2))


def ellenoriz(cfg, _a) -> int:
    el = szinkron.olvas_mappa(cfg)
    latott, hibak = szinkron.latott_kartyak(el)
    _kiir({"mappa": szinkron.mappa(cfg), "fajlok": len(el), "kartyak": len(latott), "hibak": hibak})
    return 0


def szinkronizal(cfg, _a) -> int:
    _kiir(szinkron.szinkron(cfg))
    return 0


def _media(cfg, kartyak: list[dict]) -> tuple[dict[str, Path], list[str]]:
    """A kártyák képei a vaultból, a core link-feloldójával (L42) → ({fájlnév: út}, feloldatlanok)."""
    vault = cfg.path("vault")
    fel = feloldas.Feloldo(nfc for nfc, _nyers in feloldas.bejaras(vault))
    nyers = {nfc: n for nfc, n in feloldas.bejaras(vault)}
    media, hiany = {}, []
    for k in kartyak:
        for cel in html.kepek(k["kerdes"] + "\n" + k["valasz"]):
            ut, alap, _ = fel.resolve(cel, k.get("jegyzet") or "")
            if ut is None:
                hiany.append(cel)
            else:
                media[alap] = vault / nyers.get(ut, ut)
    return media, sorted(set(hiany))


def exportal(cfg, a) -> int:
    kartyak = apkg.gyujt(cfg)
    cel = Path(a.cel) if a.cel else cfg.path("szemelyes") / "export" / \
        f"manifold-kartyak-{datetime.now().strftime('%Y%m%d-%H%M%S')}.apkg"
    if vaultban_van(cel, cfg.path("vault")):
        print("HIBA: a csomag nem kerülhet a vaultba", file=sys.stderr)
        return 2
    media, hiany = _media(cfg, kartyak)
    b = szinkron.beallitas(cfg)
    jel = apkg.export(cel, kartyak, megtartas=float(b.get("megtartas", 0.9)), lepesszam=_lepesszam(cfg), media=media)
    _kiir({**jel, "feloldatlan_kepek": hiany})
    return 0


def importal(cfg, a) -> int:
    if not a.proba:
        print("HIBA: az éles import a C23b-ben jön (előbb a kísérőjegyzet gépi írása); most csak --proba", file=sys.stderr)
        return 2
    p = apkg.beolvas(Path(a.fajl), _lepesszam(cfg))
    sajat = sum(1 for k in p["kartyak"] if k["azon"])
    allapotok: dict[str, int] = {}
    for k in p["kartyak"]:
        n = {0: "uj", 1: "tanulas", 2: "ismetles", 3: "ujratanulas"}[k["allapot"]["allapot"]]
        allapotok[n] = allapotok.get(n, 0) + 1
    _kiir({"verzio": p["verzio"], "kartyak": len(p["kartyak"]), "sajat": sajat, "idegen": len(p["kartyak"]) - sajat,
           "allapotok": allapotok, "naplo": sum(len(k["naplo"]) for k in p["kartyak"]), "kihagyva": p["kihagyva"],
           "paklik": sorted({k["pakli"] for k in p["kartyak"]}), "media": len(p["media"]),
           "minta": [{"kerdes": k["kerdes"], "valasz": k["valasz"]} for k in p["kartyak"][:3]]})
    return 0


def general(cfg, a) -> int:
    """A feladat-lépés (C23b): kártyák a megadott jegyzetekből, jegyzetenként egy gépi tétel (egy kör). Az automatikus módban a
    jegyzet hibája a többit nem állítja meg; a kézi (egy jegyzet) hibája 5-ös kilépés érthető üzenettel."""
    import os

    from core import gepi_kliens

    from . import lanc
    try:
        worker = lanc.Worker(cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"HIBA: a modell-worker nem érhető el: {exc}", file=sys.stderr)
        return 5
    kor = gepi_kliens.uj_kor(lanc.KOR_ELOTAG)
    osszes, hibak = [], 0
    allj = (lambda: bool(a.stop_fajl) and os.path.exists(a.stop_fajl))
    for i, ut in enumerate(a.ut):
        if allj():
            print("Leállítva (a következő jegyzet előtt).", flush=True)
            break
        try:
            r = lanc.futtat(cfg, ut, gepi=gepi_kliens, worker=worker, automatikus=a.automatikus, proba=a.proba,
                            modell=a.modell, kijeloles=a.kijeloles, kor=kor, allj=allj, naplo=lambda s: print(s, flush=True))
        except (lanc.Megall, gepi_kliens.GepiHiba, ValueError, OSError) as exc:
            hibak += 1
            print(f"HIBA ({ut}): {exc}", file=sys.stderr, flush=True)
            if not a.automatikus:
                return 5
            continue
        osszes.append(r)
        print(f"{ut}: {r['allapot']} · {r.get('kartyak', 0)} kártya" + (" (próba)" if r.get("proba") else ""), flush=True)
        print(f"[manifold-progress] {round(100 * (i + 1) / len(a.ut))}%", flush=True)
    _kiir({"kor": kor, "jegyzetek": osszes, "hibak": hibak})
    return 0 if osszes or not hibak else 5


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="mos kartya", description="Kártyák és FSRS (C23a, C23b)")
    al = ap.add_subparsers(dest="parancs", required=True)
    g = al.add_parser("general", help="kártyák jegyzetekből a modellel (feladat-lépés: a core-on át ír)")
    g.add_argument("--ut", action="append", required=True)
    g.add_argument("--automatikus", action="store_true")
    g.add_argument("--proba", action="store_true", help="az írás a vault APFS-klónjára (D9)")
    g.add_argument("--modell", help="kifejezett modell (csak próba, D9)")
    g.add_argument("--stop-fajl")
    g.add_argument("--kijeloles", help="a „Kártyák ebből” kijelölt szövege (csak egy jegyzetnél)")
    al.add_parser("ellenoriz", help="a kártyamappa elemzése (csak olvas)")
    al.add_parser("szinkron", help="a kártyamappa → tanulas.sqlite")
    e = al.add_parser("export", help="Anki-csomag (.apkg) a kártyákból és az állapotból")
    e.add_argument("cel", nargs="?")
    i = al.add_parser("import", help="Anki-csomag beolvasása (most csak --proba)")
    i.add_argument("fajl")
    i.add_argument("--proba", action="store_true", help="csak jelentés; a DB-hez és a vaulthoz nem nyúl")
    a = ap.parse_args(argv)
    cfg = config.load()
    return {"ellenoriz": ellenoriz, "szinkron": szinkronizal, "export": exportal, "import": importal,
            "general": general}[a.parancs](cfg, a)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
