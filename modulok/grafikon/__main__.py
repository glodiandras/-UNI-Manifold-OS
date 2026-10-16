"""A grafikon-modul parancssora: `bin/mos grafikon <parancs>`. Csak olvas; a vaultba nem ír, modellt nem tölt.

    felismer "<LaTeX képlet>"                   a képlet → plot-blokk javaslat (JSON)
    jegyzet <fájl.md> [--mindet]                a jegyzet képletei → javaslatok sorral (JSON)
    elemez "<kifejezés>" <alsó> <felső>         zérushely, szélsőérték, aszimptota az ablakon (JSON)
    elemez-json                                 stdin: {"fuggvenyek": ["…"], "ablak": [a, b]} → stdout: {"fuggvenyek": [...]}
                                                (a core `POST /api/grafikon/elemzes` ezt hívja alfolyamatként)
    arany [--json]                              a `grafikon` aranyhalmaza + a szintetikus halmaz mérése a homokozón át
    vektorok [--ir]                             a Python ↔ TypeScript közös vektorok ellenőrzése (--ir: előállítása)
    terv <fájl.md>                              a jegyzetbe beírható blokkok terve (csak olvas; JSON)
    beiras <vault-út>  [--proba]                a jegyzet blokkjainak beírása a gépi-írás szolgáltatáson át (MOS_CORE_URL kell);
                                                alapból csak terv, `--proba`: az írás a vault másolatára megy
    automatikus [--szaraz] [--proba] [--max N] [--ut JEGYZET…] [--modell-ag] [--modell M]
                                                az automatikus mód egy futása; alapból csak döntések (szárazon), `--proba`: klónra
                                                ír; az éles írás (`--eles`) csak a feladatsor lépéseként (MOS_FELADAT) indul;
                                                `--ut`: a közös ütemező kijelölte jegyzetek (nélküle a vault bejárása és a közös döntés)
    modell-meres --modell M [--keret munka|tavol] [--ki F.json] [--limit N]
                                                a modell-ág mérése az aranyhalmaz képletein (workerrel; a vaultba nem ír)
    tiltolista                                  a tiltott képletek listája (csak olvas; a levétel a vezérlő API-ján át)
    modell-ellenorzes "<képlet>" <blokk.txt>    egy (modell által adott) blokk-törzs négy kapuja a felismerő képletével (csak olvas)

A SymPy-értelmezés minden parancsban a CAS-homokozó gyermekében fut (CLAUDE.md 46. döntés).
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
if str(MODULOK.parent) not in sys.path:                  # a `core` és a `modulok.…` (C35b-mag: gépi-írás kliens, közös automatika-mérték)
    sys.path.append(str(MODULOK.parent))

import grafikon  # noqa: E402


KERES_HIBA = 64                    # a core ezt a kilépési kódot ismeri fel hibás kérésként


def _json(o) -> None:
    print(json.dumps(o, ensure_ascii=False, indent=2))


def _homokozo():
    from homokozo import Homokozo
    return Homokozo()


def cmd_felismer(a, hk, stdin) -> int:
    _json(grafikon.felismer(a.keplet, homokozo=hk))
    return 0


def cmd_jegyzet(a, hk, stdin) -> int:
    _json(grafikon.felismer_jegyzet(Path(a.fajl).read_text(encoding="utf-8"), mindet=a.mindet, homokozo=hk))
    return 0


def cmd_elemez(a, hk, stdin) -> int:
    _json(grafikon.elemzes(a.kifejezes, [a.also, a.felso], homokozo=hk))
    return 0


def cmd_elemez_json(a, hk, stdin) -> int:
    """A core alfolyamat-hívása. Hibás kérésre 64-es kilépési kód (EX_USAGE; a Python saját 2-es hibakódjával nem ütközik) és `{"hiba": …}`; a homokozó hibája tételenként az
    `allapot`-ban (`homokozo_hiba`), 0-s kilépéssel: a core a JSON-ból dönt."""
    try:
        k = json.loads(stdin.read())
        f, ablak = k["fuggvenyek"], k["ablak"]
        if (not isinstance(f, list) or not f or len(f) > grafikon.MAX_FUGGVENY
                or not all(isinstance(x, str) for x in f) or not isinstance(ablak, list) or len(ablak) != 2):
            raise ValueError(f"fuggvenyek: 1–{grafikon.MAX_FUGGVENY} szöveg; ablak: két határ")
    except (ValueError, KeyError, TypeError) as h:
        _json({"hiba": f"hibás kérés: {h}"})
        return KERES_HIBA
    _json({"fuggvenyek": grafikon.elemzesek(f, ablak, homokozo=hk)})
    return 0


def cmd_arany(a, hk, stdin) -> int:
    from grafikon import meres
    return meres.main(["--json"] if a.json else [], hk=hk)


def cmd_vektorok(a, hk, stdin) -> int:
    from grafikon import vektorok
    return vektorok.main(["--ir"] if a.ir else [])


# ------------------------------------------------------------------ C35b-mag: automatikus beírás (olvasó/próba módú CLI)

def _cfg():
    from core import config
    return config.load()


def _felismero(hk):
    return lambda szoveg: grafikon.felismer_jegyzet(szoveg, homokozo=hk)


def _modell_hivo(cfg, eles: bool, modell_ag: bool, modell: str | None = None):
    """A modell-ág hívója (lusta worker-kötés), vagy `None`. Éles (`--eles`) futásban csak a `[grafikon.automatika] modell_ag`
    kapcsolóval (alapból hamis); kézi/próba futásban a `--modell-ag` vagy a kifejezett `--modell` kapcsolóval — a kimenete ekkor
    is próba (D9: a kifejezett modell nem kalibrált; a `proba` írás klónra megy)."""
    from grafikon import automatika, modell_hivo
    if eles:
        return modell_hivo.Hivo(cfg, mod="auto") if automatika.beallitas(cfg).modell_ag else None
    return modell_hivo.Hivo(cfg, modell=modell, mod="auto") if (modell_ag or modell) else None


def _beiro(cfg, hk, proba: bool, max_db=None, varakozas_mp=30.0, kliens=None, modell=None):
    from core import gepi_kliens, plot_allapot
    from grafikon import beiras
    return beiras.Beiro(kliens or gepi_kliens, _felismero(hk), plot_allapot.Tiltolista(cfg), plot_allapot.Beirasok(cfg),
                        proba=proba, max_db=max_db or beiras.MAX_DB, varakozas_mp=varakozas_mp, modell=modell, homokozo=hk)


def cmd_terv(a, hk, stdin) -> int:
    """Egy helyi jegyzetfájl terve (a core-ra nincs szükség; a tiltólistát a `{state}`-ből olvassa, ha van)."""
    from core import plot_allapot
    from grafikon import beiras
    szoveg = Path(a.fajl).read_text(encoding="utf-8")
    try:
        tiltott = plot_allapot.Tiltolista(_cfg()).kulcsok()
    except Exception:                                    # nincs konfiguráció / állapot: tiltólista nélküli terv
        tiltott = frozenset()
    besz, ki = beiras.terv(szoveg, grafikon.felismer_jegyzet(szoveg, homokozo=hk), tiltott)
    _json({"beszurasok": [{"kulcs": b.kulcs, "utan_sor": b.veg_sor, "fajta": b.fajta, "blokk": b.blokk} for b in besz],
           "kihagyva": ki})
    return 0


def cmd_beiras(a, hk, stdin) -> int:
    from core import gepi_kliens
    from grafikon import beiras
    cfg = _cfg()
    b = _beiro(cfg, hk, proba=True if a.proba else False)
    if not a.proba:                                      # a CLI alapból nem ír: terv az olvasott jegyzetre
        d = gepi_kliens.olvas(a.ut)
        besz, ki = beiras.terv(d["tartalom"], grafikon.felismer_jegyzet(d["tartalom"], homokozo=hk), b.tiltolista.kulcsok())
        _json({"allapot": "terv", "beszurasok": [{"kulcs": x.kulcs, "utan_sor": x.veg_sor, "blokk": x.blokk} for x in besz],
               "kihagyva": ki})
        return 0
    _json(b.jegyzet(a.ut))
    return 0


def cmd_automatikus(a, hk, stdin) -> int:
    import os
    from core import automatika as OA
    from core import plot_allapot, vezerlo
    from grafikon import automatika, beiras
    if a.eles and not os.environ.get("MOS_FELADAT"):
        print("az éles írás csak a feladatsor lépéseként indul (MOS_FELADAT); kézzel: --proba vagy --szaraz", file=sys.stderr)
        return 2
    cfg = _cfg()
    beall = automatika.beallitas(cfg)
    szaraz = a.szaraz or not (a.eles or a.proba)
    proba = bool(a.proba) or not a.eles                  # az `--eles --proba` (vezérlő-kérés) is klónra ír
    tar = OA.Tar(cfg)
    ki = {"dontesek": [], "jegyzetek": [], "szamlalo": {}, "megallt": None}
    utak = list(a.ut or ())
    if not utak:                                         # kézi mód: a közös döntés a vault bejárásán
        kapcsolo = bool(vezerlo.kapcsolok(cfg)["asszisztens"])
        ki.update(automatika.jeloltek(cfg, tar, kapcsolo_be=kapcsolo, beall=beall))
        utak = [d["ut"] for d in ki["dontesek"]]
    else:
        ki["dontesek"] = [{"ut": u, "ok": "kapott"} for u in utak]
    if szaraz:
        return _json_ki(ki)
    b = _beiro(cfg, hk, proba=proba, max_db=None, varakozas_mp=beall.varakozas_mp,
               modell=_modell_hivo(cfg, a.eles and not a.proba, a.modell_ag, a.modell))
    elo = []
    if a.eles and not proba:                             # a tiltólista frissítése az éles futás elején (a visszavonás nem tiltólistáz)
        try:
            elo = beiras.torles_ellenorzes(b.kliens, b.tiltolista, b.beirasok, beiras.visszavont_shak(b.kliens))
        except Exception as e:                           # a napló nem olvasható: nem döntünk törlésről (zárva hibázás)
            print(f"a törlés-ellenőrzés kimaradt: {e}", file=sys.stderr)
    futas = automatika.futas(cfg, b, tar, utak, proba=proba, stop_fajl=a.stop_fajl, max_jegyzet=a.max,
                             log=lambda s: print(s, flush=True))
    ki.update({"jegyzetek": futas["jegyzetek"], "megallt": futas["megallt"], "torles_ellenorzes": elo})
    return _json_ki(ki)


def _json_ki(o) -> int:
    _json(o)
    return 0


def cmd_tiltolista(a, hk, stdin) -> int:
    from core import plot_allapot
    _json({"tiltott": plot_allapot.Tiltolista(_cfg()).lista()})
    return 0


def cmd_modell_ellenorzes(a, hk, stdin) -> int:
    from grafikon import modell_ag
    j = grafikon.felismer(a.keplet, homokozo=hk)
    torzs = modell_ag.kinyer(Path(a.blokk).read_text(encoding="utf-8"))
    _json({"felismeres": {k: j.get(k) for k in ("fajta", "bizonyossag", "ok")},
           "ellenorzes": modell_ag.ellenoriz(torzs, j, hk) if torzs is not None else {"allapot": "elvetve", "ok": "nincs kinyerhető blokk"}})
    return 0


def main(argv=None, hk=None, stdin=None) -> int:
    if argv is None:                                      # szkriptként indítva (bin/mos grafikon …) a parancssor az argv
        argv = sys.argv[1:]
    if argv and argv[0] == "modell-meres":               # a mérés saját argumentumai (C35b): modell_meres.main
        from grafikon import modell_meres
        return modell_meres.main(list(argv[1:]), homokozo=hk)
    p = argparse.ArgumentParser(prog="bin/mos grafikon", description="a ```plot blokk felismerése és jellemzői")
    s = p.add_subparsers(dest="parancs", required=True)
    q = s.add_parser("felismer")
    q.add_argument("keplet")
    q = s.add_parser("jegyzet")
    q.add_argument("fajl")
    q.add_argument("--mindet", action="store_true", help="a `nincs` (nem grafikon) tételeket is")
    q = s.add_parser("elemez")
    q.add_argument("kifejezes")
    q.add_argument("also")
    q.add_argument("felso")
    s.add_parser("elemez-json")
    q = s.add_parser("arany")
    q.add_argument("--json", action="store_true", help="a tételenkénti riport JSON-ban")
    q = s.add_parser("vektorok")
    q.add_argument("--ir", action="store_true", help="a vektorfájlok újraírása (különben csak ellenőrzés)")
    q = s.add_parser("terv")
    q.add_argument("fajl")
    q = s.add_parser("beiras")
    q.add_argument("ut")
    q.add_argument("--proba", action="store_true", help="az írás a vault másolatára megy (a vault nem változik)")
    q = s.add_parser("automatikus")
    q.add_argument("--szaraz", action="store_true", help="csak a döntések (alap, ha sem --proba, sem --eles)")
    q.add_argument("--proba", action="store_true", help="az írás a vault APFS-klónjára megy")
    q.add_argument("--eles", action="store_true", help="éles írás: csak a feladatsor lépéseként (MOS_FELADAT)")
    q.add_argument("--max", type=int, default=None, help="egy futásban legfeljebb ennyi jegyzet")
    q.add_argument("--stop-fajl", default=None)
    q.add_argument("--ut", action="append", default=None, help="a feldolgozandó jegyzet (ismételhető; a közös ütemező adja)")
    q.add_argument("--modell-ag", action="store_true", help="a modell-ág is fut (kézi/próba módban a kimenete próba)")
    q.add_argument("--modell", default=None, help="kifejezett modell a modell-ághoz (nem kalibrált: próba)")
    s.add_parser("tiltolista")
    q = s.add_parser("modell-ellenorzes")
    q.add_argument("keplet")
    q.add_argument("blokk")
    a = p.parse_args(argv)
    fv = {"terv": cmd_terv, "beiras": cmd_beiras, "automatikus": cmd_automatikus, "tiltolista": cmd_tiltolista,
          "modell-ellenorzes": cmd_modell_ellenorzes, "felismer": cmd_felismer, "jegyzet": cmd_jegyzet, "elemez": cmd_elemez, "elemez-json": cmd_elemez_json,
          "vektorok": cmd_vektorok, "arany": cmd_arany}
    if a.parancs == "vektorok":                       # nem kell homokozó: a vektorokat folyamaton belül számolja
        return cmd_vektorok(a, None, None)
    if a.parancs == "tiltolista":                     # nem kell homokozó
        return cmd_tiltolista(a, None, None)
    return fv[a.parancs](a, hk if hk is not None else _homokozo(), stdin if stdin is not None else sys.stdin)


if __name__ == "__main__":
    sys.exit(main())
