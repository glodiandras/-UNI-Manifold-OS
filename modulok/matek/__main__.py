"""A matek-motor parancssora: `bin/mos matek <parancs>`. A vaultba közvetlenül nem ír (a `megoldas` a gépi-írás
szolgáltatáson át ír, a feladatsor lépéseként).

    levezetes <jegyzet.md> --sorok 12-19 [--vegeredmeny] [--kikotes "x>=1" …] [--mod auto|egyenlet|kifejezes]
    egyseg "<sor>" [--jeloles v=m/s …]
    arany              az aranyhalmaz 10 hibás és 10 helyes levezetése → felismert első hiba / téves riasztás
    homokozo-proba     a homokozó biztonsági próbái ezen a gépen (RENDBEN / HIBA)
    levezetes-json     (C24b; a core `POST /api/matek/levezetes` alfolyamata) stdin: {sorok: [{sor, szoveg}], vegeredmeny,
                       kikotesek} → stdout: az ellenőrző ítélete, a sorszámok a jegyzet soraira képezve
    megoldas --ut … --tol N --ig M --feladat SZÖVEG [--modell m] [--masodik-modell m] [--nincs-masodik] [--proba]
                       (C24b; a `matek_megoldas` feladat lépése) modell + CAS → `> [!solution]-` callout gépi írással
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MODULOK = Path(__file__).resolve().parent.parent
for _ut in (MODULOK / "eval", MODULOK):
    if str(_ut) not in sys.path:
        sys.path.insert(0, str(_ut))

import matek  # noqa: E402
from homokozo import Homokozo  # noqa: E402


def _cfg():
    from core import config
    return config.load()


def _json(o) -> None:
    print(json.dumps(o, ensure_ascii=False, indent=2))


def cmd_levezetes(a, hk) -> int:
    tol, _, ig = a.sorok.partition("-")
    sorok = matek.jegyzet_sorai(Path(a.jegyzet).read_text(encoding="utf-8"), int(tol), int(ig or tol))
    _json(matek.levezetes_ellenorzese(sorok, vegeredmeny=a.vegeredmeny, kikotesek=a.kikotes, mod=a.mod,
                                      homokozo=hk))
    return 0


def cmd_egyseg(a, hk) -> int:
    jelolesek = dict(j.split("=", 1) for j in a.jeloles)
    _json(matek.egyseg_ellenorzese(a.sor, jelolesek=jelolesek, homokozo=hk))
    return 0


def arany_riport(hk) -> dict:
    """A `matek_ellenorzo` aranyhalmaz levezetései a homokozóban → összesítés és tételenkénti eredmény."""
    from kozos import arany as A
    adat = A.betolt(MODULOK / "eval" / "matek")
    feladat = {f["id"]: f for f in adat["feladatok"]}
    tetelek = [{"id": h["id"], "sorok": [s["latex"] for s in h["sorok"]], "hibas_sor": h["hibas_sor"],
                "hiba": h["hiba"]} for h in adat["levezetesek"]]
    tetelek += [{"id": f"jo-{f['id']}", "sorok": [s["latex"] for s in f["lepesek"]], "hibas_sor": None, "hiba": None}
                for f in adat["feladatok"] if f.get("lepesek")]
    lepes = float(hk.beall["lepes_idokorlat_s"])
    eredmenyek = hk.futtat([{"muvelet": "hivas", "nev": "matek.levezetes",
                             "args": {"sorok": t["sorok"], "lepes_idokorlat_s": lepes}} for t in tetelek],
                           idokorlat_s=lepes * 20)
    sorok, felismert, hely_jo, riasztas, nem_ell = [], 0, 0, 0, 0
    for t, e in zip(tetelek, eredmenyek):
        r = e["ertek"] if e["allapot"] == "ok" else {"allapot": "nem_ellenorizheto", "elso_hiba": None}
        hiba = r.get("elso_hiba")
        if t["hibas_sor"] is None:
            riasztas += hiba is not None
        else:
            felismert += hiba is not None
            hely_jo += bool(hiba and hiba["sor"] == t["hibas_sor"])
        nem_ell += r["allapot"] == "nem_ellenorizheto"
        sorok.append({"id": t["id"], "hiba": t["hiba"], "vart_sor": t["hibas_sor"], "allapot": r["allapot"],
                      "talalt_sor": hiba and hiba["sor"], "fajta": hiba and hiba["fajta"]})
    hibas = sum(t["hibas_sor"] is not None for t in tetelek)
    return {"arany_verzio": A.verzio(adat), "hibas_levezetes": hibas, "felismert": felismert,
            "pontos_helyen": hely_jo, "helyes_kontroll": len(tetelek) - hibas, "teves_riasztas": riasztas,
            "nem_ellenorizheto": nem_ell, "tetelek": sorok}


def cmd_arany(a, hk) -> int:
    r = arany_riport(hk)
    for t in r["tetelek"]:
        print(f"{t['id']:8} {str(t['hiba'] or 'helyes'):16} várt: {str(t['vart_sor'] or '—'):3} "
              f"→ {t['allapot']:20} {t['talalt_sor'] or '—'} {t['fajta'] or ''}")
    print(f"\nArany: {r['arany_verzio']}. Hibás levezetés: {r['felismert']}/{r['hibas_levezetes']} felismerve, "
          f"{r['pontos_helyen']}/{r['hibas_levezetes']} a pontos sorban; helyes kontroll: {r['teves_riasztas']}/"
          f"{r['helyes_kontroll']} téves riasztás; nem ellenőrizhető: {r['nem_ellenorizheto']}.")
    return 0


def cmd_proba(a, hk) -> int:
    from homokozo import memoria, proba
    cfg = _cfg()
    ok, uzenet = hk.elerheto()
    print(f"homokozó: {'elérhető' if ok else 'NEM elérhető'} ({uzenet}); sandbox-exec: {hk.sandbox_exec}; "
          f"memóriaőr: {memoria.forras()}")
    if not ok:
        return 1
    eredmeny = proba.futtat(hk, cfg.path("vault"), Path(cfg.table["home"]), cfg.path("tmp"), Path(cfg.source))
    for r in eredmeny:
        jel = "KIHAGYVA" if r.get("kihagyva") else ("RENDBEN" if r["rendben"] else "HIBA")
        print(f"{jel:8}  {r['nev']:58} {r['allapot']:16} {r['csucs_mb']:7.1f} MB"
              + ("" if r["rendben"] and not r.get("kihagyva") else f"  ({r['uzenet']})"))
    rossz = [r for r in eredmeny if not r["rendben"]]
    kihagyva = sum(bool(r.get("kihagyva")) for r in eredmeny)
    futott = len(eredmeny) - kihagyva
    print(f"\n{'RENDBEN' if not rossz else 'HIBA'}: {futott - len(rossz)}/{futott} próba rendben"
          + (f", {kihagyva} kihagyva" if kihagyva else ""))
    return 1 if rossz else 0


KERES_HIBA = 64                    # a `levezetes-json` kilépési kódja hibás kérésre (a core 500-at ad)
MAX_SOR = 60
MAX_SOR_HOSSZ = 500


def _levezetes_keres(d) -> tuple[list[tuple[int, str]], bool, list[str]]:
    if not isinstance(d, dict) or not isinstance(d.get("sorok"), list) or not 1 <= len(d["sorok"]) <= MAX_SOR:
        raise ValueError(f"a `sorok` 1–{MAX_SOR} elemű lista legyen")
    sorok = []
    for s in d["sorok"]:
        if (not isinstance(s, dict) or isinstance(s.get("sor"), bool) or not isinstance(s.get("sor"), int)
                or not isinstance(s.get("szoveg"), str) or len(s["szoveg"]) > MAX_SOR_HOSSZ):
            raise ValueError("a sor {sor: egész, szoveg: legfeljebb %d jel} legyen" % MAX_SOR_HOSSZ)
        sorok.append((s["sor"], s["szoveg"]))
    kik = d.get("kikotesek") or []
    if not isinstance(kik, list) or len(kik) > 8 or not all(isinstance(k, str) and len(k) <= 200 for k in kik):
        raise ValueError("a `kikotesek` legfeljebb 8 rövid szöveg legyen")
    return sorok, bool(d.get("vegeredmeny")), kik


def levezetes_jegyzetsorokra(sorok: list[tuple[int, str]], vegeredmeny: bool, kikotesek: list[str], hk) -> dict:
    """A jegyzet sorai → az ellenőrző ítélete, minden sorszám (`sor`, `honnan`, `hova`, `elso_hiba.sor`) mellé a jegyzet
    sorszáma (`jegyzet_sor`, `jegyzet_honnan`, `jegyzet_hova`): a margójel oda kerül."""
    parok = matek.sorszammal(sorok)
    if not parok:
        return {"allapot": "nem_ellenorizheto", "ok": "a kijelölésben nincs képlet-sor", "elso_hiba": None,
                "atmenetek": [], "sorok": []}
    terkep = [n for _, n in parok]
    r = matek.levezetes_ellenorzese([s for s, _ in parok], vegeredmeny=vegeredmeny, kikotesek=kikotesek, homokozo=hk)

    def j(i):
        return terkep[i - 1] if isinstance(i, int) and 1 <= i <= len(terkep) else None
    for s in r.get("sorok") or []:
        s["jegyzet_sor"] = j(s.get("sor"))
    for a in r.get("atmenetek") or []:
        a["jegyzet_honnan"], a["jegyzet_hova"] = j(a.get("honnan")), j(a.get("hova"))
    if isinstance(r.get("elso_hiba"), dict):
        r["elso_hiba"]["jegyzet_sor"] = j(r["elso_hiba"].get("sor"))
    return r


def cmd_levezetes_json(a, hk) -> int:
    try:
        sorok, vegeredmeny, kikotesek = _levezetes_keres(json.loads(sys.stdin.read() or "{}"))
    except ValueError as exc:
        print(str(exc))
        return KERES_HIBA
    print(json.dumps(levezetes_jegyzetsorokra(sorok, vegeredmeny, kikotesek, hk), ensure_ascii=False))
    return 0


def cmd_megoldas(a, hk) -> int:
    import os
    from core import gepi_kliens
    from matek import lanc
    stop = os.environ.get("MANIFOLD_STOP_FAJL")
    feladat = a.feladat
    from core.modell import kliens
    try:
        worker = lanc.Worker(_cfg())
    except kliens.KliensHiba as exc:
        print(f"HIBA: a modell-worker nem érhető el: {exc}", file=sys.stderr)
        return 5
    try:
        r = lanc.futtat(ut=a.ut, tol=a.tol, ig=a.ig, feladat=feladat, gepi=gepi_kliens, worker=worker,
                        homokozo=hk, proba=a.proba, modell=a.modell, masodik_modell=a.masodik_modell,
                        masodik=not a.nincs_masodik, allj=lambda: bool(stop and os.path.exists(stop)),
                        naplo=lambda s: print(s, flush=True))
    except lanc.Megall as exc:
        print(f"HIBA: {exc}", file=sys.stderr)
        return 3
    except gepi_kliens.GepiHiba as exc:
        print(f"HIBA: a core elutasította a kérést ({exc.kod}): {exc}", file=sys.stderr)
        return 4
    except kliens.KliensHiba as exc:
        print(f"HIBA: a modell-worker hibája ({exc.kod}): {exc}", file=sys.stderr)
        return 5
    print(json.dumps(r, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="mos matek", description=__doc__.splitlines()[0])
    al = p.add_subparsers(dest="parancs", required=True)
    lv = al.add_parser("levezetes", help="egy jegyzet kijelölt sorainak ellenőrzése (csak olvas)")
    lv.add_argument("jegyzet")
    lv.add_argument("--sorok", required=True, help="pl. 12-19 (a jegyzet sorszámai, 1-től)")
    lv.add_argument("--vegeredmeny", action="store_true", help="a végeredményt is mondja meg")
    lv.add_argument("--kikotes", action="append", default=[], help='pl. "x>=1" (a feladat szövegéből)')
    lv.add_argument("--mod", default="auto", choices=("auto", "egyenlet", "kifejezes"))
    eg = al.add_parser("egyseg", help="egy fizikai sor mértékegység-ellenőrzése")
    eg.add_argument("sor")
    eg.add_argument("--jeloles", action="append", default=[], help="pl. v=m/s")
    al.add_parser("arany", help="az aranyhalmaz levezetéseinek kiértékelése")
    al.add_parser("homokozo-proba", help="a homokozó biztonsági próbái")
    al.add_parser("levezetes-json", help="a core végpontjának alfolyamata (stdin/stdout JSON)")
    mg = al.add_parser("megoldas", help="a `matek_megoldas` feladat lépése (modell + CAS → callout, gépi írással)")
    mg.add_argument("--ut", required=True)
    mg.add_argument("--tol", type=int, required=True)
    mg.add_argument("--ig", type=int, required=True)
    mg.add_argument("--feladat", required=True, help="a feladat szövege (a jegyzet tol–ig sorai, változatlanul)")
    mg.add_argument("--modell", help="kifejezett modell (csak próbában)")
    mg.add_argument("--masodik-modell", help="a második vélemény kifejezett modellje (csak próbában)")
    mg.add_argument("--nincs-masodik", action="store_true")
    mg.add_argument("--proba", action="store_true", help="az írás a vault másolatára (a vault nem változik)")
    a = p.parse_args(argv)
    try:
        cfg = _cfg()
    except Exception:                                           # a konfiguráció nélkül is fusson (alapértékek)
        cfg = None
    hk = Homokozo(cfg)
    return {"levezetes": cmd_levezetes, "egyseg": cmd_egyseg, "arany": cmd_arany, "homokozo-proba": cmd_proba,
            "levezetes-json": cmd_levezetes_json, "megoldas": cmd_megoldas}[a.parancs](a, hk)


if __name__ == "__main__":
    sys.exit(main())
