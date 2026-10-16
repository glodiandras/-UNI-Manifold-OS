"""`python -m modulok.kod …` — the multi-language workbench engine (F10). It never writes the vault.

    nyelvek [--json] [--nyelv ID]       the language profiles with their toolchain state (discovery; no download, D3)
    ellenoriz <source | note.md> [--jegyzet NOTE.md] [--nyelv ID] [--mod gyors|hibakereso] [--json-sorok]
                                        compile + every `teszt` block in the sandbox. Exit: 0 passed · 1 not passed ·
                                        2 error or interrupted (SIGTERM / SIGINT)
    ai <mode> <source> [--jegyzet NOTE.md] [--nyelv ID] [--megerosit] [--json-sorok]
                                        one AI request (hiba | tipp | megoldas | teszt | stressz); D9: only a calibrated model
                                        runs for real, otherwise a trial (`proba`) — the result is a suggestion only
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
from core import kod_nyelvek as KN


def _cfg():
    from core import config
    return config.load()


def _ki(d: dict, json_sorok: bool) -> None:
    if json_sorok:
        print(json.dumps(d, ensure_ascii=False), flush=True)
    else:
        print(json.dumps(d, ensure_ascii=False, indent=1), flush=True)


def _hiba(kod: str, uzenet: str, json_sorok: bool, **param) -> int:
    if json_sorok:
        print(json.dumps({"szakasz": "hiba", "kod": kod, "param": param, "uzenet": uzenet}, ensure_ascii=False), flush=True)
    else:
        print(f"ERROR: {uzenet}", file=sys.stderr)
    return 2


def _profil(nyelv: str | None, forras: Path) -> KN.Profil | None:
    return KN.profil(nyelv) if nyelv else KN.nyelv_ut(forras.name)


def _forras_feloldas(jegyzet: Path, cel: str, cfg) -> Path | None:
    """The embedded source: next to the note, at the vault root, or the vault's single file of that name."""
    kandidatok = [jegyzet.parent / cel]
    try:
        vault = cfg.path("vault")
        kandidatok.append(vault / cel)
    except Exception:                                    # noqa: BLE001 — no vault in this layout
        vault = None
    for ut in kandidatok:
        if ut.is_file():
            return ut
    if vault is None:
        return None
    alap = Path(cel).name.lower()
    talalat: list[Path] = []
    for gyoker, mappak, fajlok in os.walk(vault):
        mappak[:] = [m for m in mappak if not m.startswith(".")]
        talalat += [Path(gyoker) / f for f in fajlok if f.lower() == alap]
        if len(talalat) > 1:
            break
    return talalat[0] if len(talalat) == 1 else None


def _megszakito() -> threading.Event:
    e = threading.Event()
    for jel in (signal.SIGTERM, signal.SIGINT):
        signal.signal(jel, lambda *_: e.set())
    return e


def cmd_nyelvek(a, cfg) -> int:
    from .felderites import Felderites
    fd = Felderites(cfg)
    profilok = [KN.profil(a.nyelv)] if a.nyelv else list(KN.PROFILOK)
    if None in profilok:
        return _hiba("kod.ismeretlen_nyelv", f"Unknown language: {a.nyelv}", a.json, nyelv=a.nyelv)
    lista = [fd.nyelv(p) for p in profilok]
    if a.json:
        print(json.dumps({"nyelvek": lista}, ensure_ascii=False, indent=1))
    else:
        for d in lista:
            allapot = "ready" if d["elerheto"] else "MISSING"
            eszk = ", ".join(f"{e['nev']}={e.get('valos') or e.get('ut') or '-'}" for e in d["eszkozok"])
            print(f"{d['azonosito']:11} {allapot:8} {eszk}")
            if d["hiba"]:
                print(f"            {d['hiba']['uzenet']}")
    return 0


def _tesztek(cfg, jegyzet: Path | None, b: dict) -> list:
    if jegyzet is None:
        return []
    return cpp_teszt.tesztek(jegyzet.read_text(encoding="utf-8"), max_idokorlat_s=float(b["teszt_idokorlat_max_s"]),
                             max_memoria_mb=float(b["teszt_memoria_max_mb"]))


def _bemenet(a, cfg) -> tuple[Path, Path | None] | int:
    ut = Path(a.ut)
    if ut.suffix.lower() == ".md":
        jegyzet = ut
        try:
            celok = KN.beagyazott_forrasok(jegyzet.read_text(encoding="utf-8"))
        except OSError as exc:
            return _hiba("kod.nincs_jegyzet", f"The note is not readable: {exc}", a.json_sorok)
        if not celok:
            return _hiba("kod.nincs_beagyazott_forras", "There is no embedded source file in the note (![[name.ext]]).",
                         a.json_sorok)
        forras = _forras_feloldas(jegyzet, celok[0], cfg)
        if forras is None:
            return _hiba("kod.forras_nem_talalhato", f"The embedded file is not found (or ambiguous): {celok[0]}", a.json_sorok,
                         nev=celok[0])
        return forras, jegyzet
    return ut, (Path(a.jegyzet) if a.jegyzet else None)


def cmd_ellenoriz(a, cfg) -> int:
    from .ellenorzes import Ellenorzes
    r = _bemenet(a, cfg)
    if isinstance(r, int):
        return r
    forras, jegyzet = r
    p = _profil(a.nyelv, forras)
    if p is None:
        return _hiba("kod.ismeretlen_nyelv", f"Unknown language of {forras.name}", a.json_sorok, nev=forras.name)
    if not forras.is_file():
        return _hiba("kod.nincs_forras", f"The source is not readable: {forras.name}", a.json_sorok, ut=forras.name)
    from modulok.cpp.eszkoztar import beallitas as cpp_beallitas
    b = cpp_beallitas(cfg) if p.motor == "cpp" else KN.beallitasok(cfg)       # C/C++: the `[cpp]` limits, unchanged
    try:
        tesztek = _tesztek(cfg, jegyzet, b)
    except OSError as exc:
        return _hiba("kod.nincs_jegyzet", f"The note is not readable: {exc}", a.json_sorok)
    megszakit = _megszakito()
    utolso: list[str] = []

    def esemeny(d: dict) -> None:
        utolso.append(d["szakasz"])
        _ki(d, a.json_sorok)
    res = Ellenorzes(cfg, p, esemeny=esemeny, megszakit=megszakit.is_set).fut(forras, tesztek, a.mod,
                                                                             jegyzet=str(jegyzet) if jegyzet else None)
    if utolso and utolso[-1] in ("hiba", "megszakitva"):
        return 2
    return 0 if res["atment"] else 1


def cmd_ai(a, cfg) -> int:
    from .ai_futas import AIFutas
    forras = Path(a.ut)
    p = _profil(a.nyelv, forras)
    if p is None:
        return _hiba("kod.ismeretlen_nyelv", f"Unknown language of {forras.name}", a.json_sorok, nev=forras.name)
    megszakit = _megszakito()
    r = AIFutas(cfg, p, esemeny=lambda d: _ki(d, a.json_sorok), megszakit=megszakit.is_set).fut(
        a.mod, forras, Path(a.jegyzet) if a.jegyzet else None, megerosit=a.megerosit)
    return 0 if r.get("ok") else 2


def main(argv=None, *, cfg=None) -> int:
    pr = argparse.ArgumentParser(prog="mos kod", description=__doc__.splitlines()[0])
    al = pr.add_subparsers(dest="parancs", required=True)
    n = al.add_parser("nyelvek", help="the language profiles and their toolchains")
    n.add_argument("--json", action="store_true")
    n.add_argument("--nyelv")
    e = al.add_parser("ellenoriz", help="compile + tests in the sandbox")
    e.add_argument("ut")
    e.add_argument("--jegyzet")
    e.add_argument("--nyelv", choices=KN.azonositok())
    e.add_argument("--mod", default="gyors", choices=KN.MODOK)
    e.add_argument("--json-sorok", action="store_true")
    i = al.add_parser("ai", help="one AI request (D9: calibrated or trial)")
    i.add_argument("mod", choices=KN.AI_MODOK)
    i.add_argument("ut")
    i.add_argument("--jegyzet")
    i.add_argument("--nyelv", choices=KN.azonositok())
    i.add_argument("--megerosit", action="store_true")
    i.add_argument("--json-sorok", action="store_true")
    a = pr.parse_args(argv)
    cfg = cfg if cfg is not None else _cfg()
    if a.parancs == "nyelvek":
        return cmd_nyelvek(a, cfg)
    if a.parancs == "ellenoriz":
        return cmd_ellenoriz(a, cfg)
    return cmd_ai(a, cfg)


if __name__ == "__main__":
    sys.exit(main())
