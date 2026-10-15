"""`bin/mos cpp …` — a C++ munkafelület parancssora (C36a). A vaultba nem ír.

    allapot [--json]                  az eszköztár állapota (megvan-e, verziók, linker, SDK-régiség)
    telepit [--lista | --igen | --sdk | --tbd-igazit] [--ujra]
                                      a letöltési lista (alap) · `--igen`: az LLVM letöltése és az SDK másolata (D3:
                                      kifejezett igen) · `--sdk`: csak az SDK másolata · `--tbd-igazit`: a meglévő SDK-másolat
                                      .tbd-iből az ld64.lld számára ismeretlen célok kivétele (hálózat nélkül, idempotens) ·
                                      `--ujra`: újratelepítés (a régit `.regi` néven félreteszi)
    ellenoriz <jegyzet.md | megoldas.cpp> [--cpp FÁJL] [--jegyzet FÁJL] [--hibakereso] [--json-sorok]
                                      fordítás és tesztenként futtatás homokozóban; `--json-sorok`: eseménysorok a core-nak.
                                      Kilépési kód: 0 átment · 1 nem ment át · 2 hiba vagy megszakítva (SIGTERM / SIGINT)
    formaz [FÁJL | -]                 clang-format (stdin → stdout), a fájlt nem írja
    homokozo-proba                    a program-homokozó biztonsági próbái ezen a gépen (RENDBEN / HIBA)
    ai <mod> <megoldas.cpp> [--jegyzet FÁJL] [--megerosit] [--json-sorok]
                                      C36b: AI-segítség (hiba | tipp | megoldas | teszt | stressz) a router kalibrált `kod`
                                      modelljével (a worker: `MOS_WORKER_URL`); a modell kódja csak a homokozóban fut, a motor
                                      nem ír semmit (a javaslatot a felület mutatja)
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
from pathlib import Path

from core import cpp_teszt

from . import eszkoztar, telepites

_ALLAPOT_SZOVEG = {"atment": ("✓", "átment"), "hibas_kimenet": ("✗", "hibás kimenet"), "futasi_hiba": ("✗", "futási hiba"),
                   "szanitizer": ("✗", "sanitizer-hiba"), "idotullepes": ("✗", "időtúllépés"),
                   "memoria": ("✗", "memóriakorlát túllépve"), "kimenet_tullepes": ("✗", "túl sok kimenet"),
                   "iras_korlat": ("✗", "túl sok írás a saját mappába"), "hibas_teszt": ("✗", "hibás teszt-blokk"),
                   "homokozo_hiba": ("✗", "homokozó-hiba")}


def _cfg():
    from core import config
    return config.load()


def _kiir_json(o) -> None:
    print(json.dumps(o, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------- állapot, telepítés

def cmd_allapot(a, cfg) -> int:
    e = eszkoztar.Eszkoztar(cfg)
    st = e.allapot()
    if a.json:
        _kiir_json(st)
        return 0 if st["kesz"] else 1
    print(f"eszköztár : {'KÉSZ' if st['kesz'] else 'NEM KÉSZ (hiányzik: ' + ', '.join(st['hianyzo']) + ')'}")
    print(f"LLVM      : {st['llvm_verzio'] or '—'}  ({st['llvm']})")
    print(f"SDK       : {st['sdk_verzio'] or '—'}  ({st['sdk']})"
          + (f"  — RÉGEBBI a macOS-nél ({st['macos_verzio']}): bin/mos cpp telepit --sdk --ujra" if st["sdk_regi"] else ""))
    if not st["sdk_tbd_igazitva"]:
        print("FIGYELEM  : az SDK-másolat .tbd-iben az ld64.lld számára ismeretlen cél van: bin/mos cpp telepit --tbd-igazit")
    if st.get("linker_figyelmeztetes"):
        print(f"FIGYELEM  : {st['linker_figyelmeztetes']}")
    print(f"linker    : {st['linker']}   clangd: {'van' if st['clangd'] else 'nincs'}   "
          f"clang-format: {'van' if st['clang_format'] else 'nincs'}   llvm-symbolizer: {'van' if st['llvm_symbolizer'] else 'nincs'}")
    if not st["kesz"]:
        print("A telepítéshez: bin/mos cpp telepit (lista), majd bin/mos cpp telepit --igen")
    return 0 if st["kesz"] else 1


def cmd_telepit(a, cfg, telepito=None) -> int:
    t = telepito or telepites.Telepito(cfg, kiir=lambda s: print(s, file=sys.stderr, flush=True))
    if a.tbd_igazit:
        print(json.dumps(telepites.tbd_igazit(cfg.path("sdk")), ensure_ascii=False))
        return 0
    if not (a.igen or a.sdk):
        print(t.lista())
        print("\nA telepítéshez add meg: --igen (az LLVM letöltése és az SDK másolata), vagy --sdk (csak az SDK másolata).")
        return 0
    try:
        if a.igen:
            print(json.dumps(t.llvm(igen=True, ujra=a.ujra), ensure_ascii=False))
        print(json.dumps(t.sdk(ujra=a.ujra), ensure_ascii=False))
    except telepites.TelepitesHiba as exc:
        print(f"HIBA: {exc}", file=sys.stderr)
        return 1
    return cmd_allapot(argparse.Namespace(json=False), cfg)


# ---------------------------------------------------------------------- ellenőrzés

def _cpp_feloldas(jegyzet: Path, cel: str, cfg) -> Path | None:
    """A beágyazott `.cpp` megkeresése: a jegyzet mappájában, a vault gyökerében, végül a vault egyetlen azonos nevű fájlja."""
    for ut in (jegyzet.parent / cel, cfg.path("vault") / cel):
        if ut.is_file():
            return ut
    alap = Path(cel).name.lower()
    talalat: list[Path] = []
    for gyoker, mappak, fajlok in os.walk(cfg.path("vault")):
        mappak[:] = [m for m in mappak if not m.startswith(".")]
        talalat += [Path(gyoker) / f for f in fajlok if f.lower() == alap]
        if len(talalat) > 1:
            break
    return talalat[0] if len(talalat) == 1 else None


def _mp(ms) -> str:
    return f"{ms / 1000:.1f}".replace(".", ",") + " s" if ms >= 1000 else f"{ms:.0f} ms"


def szoveges(e: dict) -> str | None:
    """Egy esemény emberi olvasatra (a CLI szöveges módja)."""
    sz = e["szakasz"]
    if sz == "indul":
        return f"ellenőrzés: {e['cpp']} ({e['mod']}, {e['tesztek_db']} teszt)"
    if sz == "fordit_kesz":
        f = e["fordit"]
        sorok = [f"fordítás: {'✓' if f['ok'] else '✗'} {_mp(f['ms'])}"
                 + (f" ({f['figyelmeztetes_db']} figyelmeztetés)" if f["figyelmeztetes_db"] and f["ok"] else "")]
        if f.get("linker_figyelmeztetes"):
            sorok.append(f"  FIGYELEM: {f['linker_figyelmeztetes']}")
        for d in f["diagnosztika"]:
            hely = f"{d['fajl']}:{d['sor']}:{d['oszlop']}: " if d["sor"] else ""
            sorok.append(f"  {hely}{d['szint']}: {d['uzenet']}")
        if not f["ok"]:
            if f["uzenet"] and not f["diagnosztika"]:
                sorok.append(f"  {f['uzenet']}")
            if f["kivonat"]:
                sorok.append("  " + f["kivonat"].strip().replace("\n", "\n  "))
        return "\n".join(sorok)
    if sz == "teszt":
        t = e["teszt"]
        jel, szoveg = _ALLAPOT_SZOVEG.get(t["allapot"], ("✗", t["allapot"]))
        fej = f"teszt {t['sorszam']}" + (f" · {t['cim']}" if t["cim"] else "")
        sor = f"{fej}: {jel} {szoveg}"
        if t["allapot"] != "hibas_teszt":
            sor += f" ({_mp(t['ido_ms'])}, {t['csucs_mb']:.1f} MB)"
        sorok = [sor]
        if t["allapot"] == "hibas_kimenet":
            for r in [r for r in t["diff"]["sorok"] if r["tipus"] != "egyenlo"][:10]:
                if r["tipus"] == "kihagyva":
                    sorok.append(f"  … {r['db']} egyező sor …")
                else:
                    sorok.append(f"  {r.get('vart_sor') or r.get('kapott_sor')}. sor — várt: {r['vart']!r}  kapott: {r['kapott']!r}")
        elif t["allapot"] == "hibas_teszt":
            sorok.append(f"  {t['hiba']}")
        elif t.get("jelentes"):
            j = t["jelentes"]
            sorok.append(f"  {j['leiras']}" + (f" — {j['fajl']}:{j['sor']}" if j.get("sor") else ""))
        elif t["allapot"] == "futasi_hiba":
            sorok.append(f"  {t['uzenet']}")
        return "\n".join(sorok)
    if sz == "kesz":
        return f"összesítés: {e['atment_db']}/{e['tesztek_db']} teszt ment át" + (f" — {e['uzenet']}" if e["uzenet"] else "")
    if sz == "hiba":
        return f"HIBA: {e['uzenet']}"
    if sz == "megszakitva":
        return "megszakítva"
    return None


def cmd_ellenoriz(a, cfg) -> int:
    from . import ellenorzes
    ut = Path(a.ut)
    b = eszkoztar.beallitas(cfg)
    jegyzet: Path | None
    if ut.suffix.lower() == ".md":
        jegyzet = ut
        if a.cpp:
            cpp = Path(a.cpp)
        else:
            try:
                celok = cpp_teszt.beagyazott_cpp(jegyzet.read_text(encoding="utf-8"))
            except OSError as exc:
                print(f"HIBA: a jegyzet nem olvasható: {exc}", file=sys.stderr)
                return 2
            if not celok:
                print("HIBA: nincs beágyazott .cpp a jegyzetben (![[név.cpp]]); add meg a --cpp kapcsolóval", file=sys.stderr)
                return 2
            cpp = _cpp_feloldas(jegyzet, celok[0], cfg)
            if cpp is None:
                print(f"HIBA: a beágyazott fájl nem található (vagy nem egyértelmű): {celok[0]}", file=sys.stderr)
                return 2
    elif ut.suffix.lower() == ".cpp":
        cpp, jegyzet = ut, (Path(a.jegyzet) if a.jegyzet else None)
    else:
        print("HIBA: a bemenet .md jegyzet vagy .cpp fájl legyen", file=sys.stderr)
        return 2
    if not cpp.is_file():
        print(f"HIBA: a .cpp fájl nem olvasható: {cpp}", file=sys.stderr)
        return 2
    tesztek = []
    if jegyzet is not None:
        try:
            tesztek = cpp_teszt.tesztek(jegyzet.read_text(encoding="utf-8"), max_idokorlat_s=float(b["teszt_idokorlat_max_s"]),
                                       max_memoria_mb=float(b["teszt_memoria_max_mb"]))
        except OSError as exc:
            print(f"HIBA: a jegyzet nem olvasható: {exc}", file=sys.stderr)
            return 2

    megszakit = threading.Event()
    for jel in (signal.SIGTERM, signal.SIGINT):
        signal.signal(jel, lambda *_: megszakit.set())
    utolso: list[str] = []

    def esemeny(d: dict) -> None:
        utolso.append(d["szakasz"])
        if a.json_sorok:
            print(json.dumps(d, ensure_ascii=False), flush=True)
        else:
            sz = szoveges(d)
            if sz:
                print(sz, flush=True)

    r = ellenorzes.Ellenorzes(cfg, esemeny=esemeny, megszakit=megszakit.is_set).fut(
        cpp, tesztek, "hibakereso" if a.hibakereso else "gyors", jegyzet=str(jegyzet) if jegyzet else None)
    if utolso and utolso[-1] in ("hiba", "megszakitva"):
        return 2
    return 0 if r["atment"] else 1


def cmd_formaz(a, cfg) -> int:
    szoveg = sys.stdin.read() if a.fajl == "-" else Path(a.fajl).read_text(encoding="utf-8")
    ok, ki = eszkoztar.Eszkoztar(cfg).formaz(szoveg)
    if not ok:
        print(f"HIBA: {ki}", file=sys.stderr)
        return 1
    sys.stdout.write(ki)
    return 0


def cmd_proba(a, cfg) -> int:
    from . import proba
    from modulok.homokozo import memoria
    from modulok.homokozo.program import Programhomokozo
    ph = Programhomokozo(cfg)
    ok, uzenet = ph.elerheto()
    print(f"program-homokozó: {'elérhető' if ok else 'NEM elérhető'} ({uzenet}); sandbox-exec: {ph.sandbox_exec}; "
          f"memóriaőr: {memoria.forras()}")
    if not ok:
        return 1
    eredmeny = proba.futtat(cfg, ph)
    for r in eredmeny:
        jel = "KIHAGYVA" if r.get("kihagyva") else ("RENDBEN" if r["rendben"] else "HIBA")
        print(f"{jel:8}  {r['nev']:86} {r['allapot']:16} {r['csucs_mb']:7.1f} MB"
              + ("" if r["rendben"] and not r.get("kihagyva") else f"  ({r['uzenet']})"))
    rossz = [r for r in eredmeny if not r["rendben"]]
    kihagyva = sum(bool(r.get("kihagyva")) for r in eredmeny)
    futott = len(eredmeny) - kihagyva
    print(f"\n{'RENDBEN' if not rossz else 'HIBA'}: {futott - len(rossz)}/{futott} próba rendben"
          + (f", {kihagyva} kihagyva" if kihagyva else ""))
    return 1 if rossz else 0


def main(argv=None, *, cfg=None, telepito=None) -> int:
    p = argparse.ArgumentParser(prog="mos cpp", description=__doc__.splitlines()[0])
    al = p.add_subparsers(dest="parancs", required=True)
    s = al.add_parser("allapot", help="az eszköztár állapota")
    s.add_argument("--json", action="store_true")
    t = al.add_parser("telepit", help="az LLVM letöltése és az SDK másolata (D3: kifejezett igen)")
    t.add_argument("--lista", action="store_true", help="csak a letöltési lista (alap)")
    t.add_argument("--igen", action="store_true", help="kifejezett igen: az LLVM letöltése, majd az SDK másolata")
    t.add_argument("--sdk", action="store_true", help="csak az SDK másolata (nincs hálózat)")
    t.add_argument("--tbd-igazit", action="store_true", help="a meglévő SDK-másolat .tbd-inek igazítása (hálózat nélkül)")
    t.add_argument("--ujra", action="store_true", help="újratelepítés; a meglévőt .regi néven félreteszi")
    e = al.add_parser("ellenoriz", help="fordítás és tesztenként futtatás homokozóban")
    e.add_argument("ut", help="a feladat-jegyzet (.md) vagy a megoldás (.cpp)")
    e.add_argument("--cpp", help="a megoldás fájlja (a jegyzet beágyazása helyett)")
    e.add_argument("--jegyzet", help="a tesztek jegyzete, ha az első argumentum a .cpp")
    e.add_argument("--hibakereso", action="store_true", help="-g -fsanitize=address,undefined")
    e.add_argument("--json-sorok", action="store_true", help="eseménysorok JSON-ban (a core-nak)")
    f = al.add_parser("formaz", help="clang-format: stdin → stdout")
    f.add_argument("fajl", nargs="?", default="-")
    al.add_parser("homokozo-proba", help="a program-homokozó biztonsági próbái")
    ai_p = al.add_parser("ai", help="AI-segítség (C36b): hiba | tipp | megoldas | teszt | stressz; csak kalibrált modellel")
    ai_p.add_argument("mod", choices=("hiba", "tipp", "megoldas", "teszt", "stressz"))
    ai_p.add_argument("cpp", help="a megoldás (.cpp)")
    ai_p.add_argument("--jegyzet", help="a feladat-jegyzet (.md: leírás és teszt-blokkok)")
    ai_p.add_argument("--megerosit", action="store_true", help="a teljes megoldás kérésének megerősítése (megoldas mód)")
    ai_p.add_argument("--json-sorok", action="store_true", help="eseménysorok JSON-ban (a core-nak)")
    a = p.parse_args(argv)
    cfg = cfg if cfg is not None else _cfg()
    if a.parancs == "allapot":
        return cmd_allapot(a, cfg)
    if a.parancs == "telepit":
        return cmd_telepit(a, cfg, telepito)
    if a.parancs == "ellenoriz":
        return cmd_ellenoriz(a, cfg)
    if a.parancs == "formaz":
        return cmd_formaz(a, cfg)
    if a.parancs == "ai":
        return cmd_ai(a, cfg)
    return cmd_proba(a, cfg)


def cmd_ai(a, cfg) -> int:
    """C36b: egy AI-kérés (a modell a workeren át, `MOS_WORKER_URL`; a kódja csak a program-homokozóban fut). A vaultba és a
    `.cpp`-be nem ír. Kilépési kód: 0 kész · 2 hiba vagy megszakítva."""
    from . import ai_futas
    megszakit = threading.Event()
    for jel in (signal.SIGTERM, signal.SIGINT):
        signal.signal(jel, lambda *_: megszakit.set())

    def esemeny(d: dict) -> None:
        if a.json_sorok:
            print(json.dumps(d, ensure_ascii=False), flush=True)
        elif d["szakasz"] in ("hiba", "eredmeny", "kesz"):
            print(json.dumps(d, ensure_ascii=False, indent=1), flush=True)
    r = ai_futas.AIFutas(cfg, esemeny=esemeny, megszakit=megszakit.is_set).fut(
        a.mod, Path(a.cpp), Path(a.jegyzet) if a.jegyzet else None, megerosit=a.megerosit)
    return 0 if r.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
