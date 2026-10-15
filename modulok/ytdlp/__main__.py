"""`bin/mos video …` — a videólánc parancsai (C20a, C20b). Csak a `letoltes` használ hálózatot (D3); a `staging-klon` a kifejezett `--igen`
után klónoz. A vaultba csak az `integral` ír (C20b), a gépi-írás szolgáltatáson át, modellt a workeren át kér (a betöltő tölt); kézzel
csak `--proba`-val (a vault APFS-klónjára), élesben a feladatsor lépéseként."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core import config  # noqa: E402

from . import klon, konvertalas, staging, utnorm  # noqa: E402
from .eszkoz import pin as _pin, sha256 as _sha256  # noqa: E402


def _json(adat) -> None:
    print(json.dumps(adat, ensure_ascii=False, indent=2))


def _zar_verzio(cfg, csomag: str) -> str | None:
    p = cfg.root / "config" / "requirements.lock"
    m = re.search(rf"^{re.escape(csomag)}==(\S+)", p.read_text(encoding="utf-8"), re.M) if p.is_file() else None
    return m.group(1) if m else None


def cmd_eszkoz_ellenorzes(cfg, args) -> int:
    """Az eszközök a runtime alól: ffmpeg (a pin sha256-ja, a konvertáláshoz szükséges kódolók), yt-dlp (a lock verziója), node, yt-dlp-ejs."""
    ki, rossz = [], 0

    def sor(allapot: str, nev: str, uzenet: str) -> None:
        nonlocal rossz
        ki.append({"allapot": allapot, "nev": nev, "uzenet": uzenet})
        rossz += allapot == "hiba"

    ff = cfg.path("ffmpeg")
    if not (ff.is_file() and os.access(ff, os.X_OK)):
        sor("hiba", "ffmpeg", f"hiányzik: {ff} — bin/mos runtime fetch ffmpeg (a home-beli és a PATH-os tiltott)")
    else:
        pin = _pin(cfg, "FFMPEG_BIN_SHA256")
        sha = _sha256(ff)
        if pin and sha != pin:
            sor("hiba", "ffmpeg", f"a sha256 eltér a rögzítettől ({sha[:12]}… ≠ {pin[:12]}…): {ff}")
        else:
            verzio = subprocess.run([str(ff), "-version"], capture_output=True, text=True).stdout.splitlines()[:1]
            kodolok = subprocess.run([str(ff), "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
            hianyzo = [k for k in ("libx264", "aac") if not re.search(rf"\s{k}\s", kodolok)]
            if hianyzo:
                sor("hiba", "ffmpeg", f"hiányzó kódoló a konvertáláshoz: {', '.join(hianyzo)}")
            else:
                sor("ok", "ffmpeg", f"{verzio[0] if verzio else '?'} · sha256 {sha[:12]}… egyezik · libx264, aac · {ff}")
    try:
        from importlib import metadata
        verzio, lock = metadata.version("yt-dlp"), _zar_verzio(cfg, "yt-dlp")
        sor("ok" if lock in (None, verzio) else "figyelem", "yt-dlp", f"{verzio} (lock: {lock})")
    except metadata.PackageNotFoundError:
        sor("hiba", "yt-dlp", "a yt-dlp nincs telepítve a venvbe (bin/mos runtime install)")
    try:
        import yt_dlp_ejs  # noqa: F401
        sor("ok", "yt-dlp-ejs", "importálható (a YouTube JS-kihívásához)")
    except ImportError:
        sor("figyelem", "yt-dlp-ejs", "hiányzik: YouTube-nál csak 360p érhető el")
    node = cfg.path("node")
    sor("ok" if node.is_file() else "figyelem", "node", f"{node}" if node.is_file() else f"hiányzik: {node}")
    if args.json:
        _json(ki)
    else:
        for r in ki:
            print(f"[{r['allapot']:<7}] {r['nev']:<11} {r['uzenet']}")
    return 1 if rossz else 0


def cmd_felmeres(cfg, args) -> int:
    """A staging videóinak kodekje (csak olvas): hány nem natív, mi a konvertálás terve. Nem módosít semmit."""
    ff = str(cfg.path("ffmpeg"))
    gyoker = Path(args.staging or cfg.path("staging"))
    if not gyoker.is_dir():
        print(f"nincs staging: {gyoker}", file=sys.stderr)
        return 1
    fajlok = sorted(p for p in gyoker.rglob("video.*") if p.is_file() and p.suffix.lower() not in (".json", ".md"))
    if args.limit:
        fajlok = fajlok[:args.limit]
    ossz: dict[str, int] = {}
    nem_nativ = []
    for p in fajlok:
        f = konvertalas.felmeres(ff, p)
        n, ok = konvertalas.nativ_e(f, p.suffix, video=tuple(cfg.section("video").get("nativ_video", konvertalas.ALAP_VIDEO)),
                                    hang=tuple(cfg.section("video").get("nativ_hang", konvertalas.ALAP_HANG)))
        kulcs = f"{p.suffix.lower()} {f.video or '-'}/{f.hang or '-'}"
        ossz[kulcs] = ossz.get(kulcs, 0) + 1
        if not n:
            nem_nativ.append({"ut": str(p.relative_to(gyoker)), "ok": ok, "terv": konvertalas.terv(f, p.suffix)["mod"]})
    jelentes = {"staging": str(gyoker), "videok": len(fajlok), "nem_nativ": len(nem_nativ), "bontas": dict(sorted(ossz.items())),
                "nem_nativ_lista": nem_nativ[:50]}
    if args.json:
        _json(jelentes)
    else:
        print(f"{len(fajlok)} videó a {gyoker} alatt, ebből nem natív: {len(nem_nativ)}")
        for k, v in sorted(ossz.items()):
            print(f"  {v:>4}  {k}")
        for r in nem_nativ[:20]:
            print(f"  nem natív: {r['ut']} — {r['ok']} → {r['terv']}")
    return 0


def cmd_staging_klon(cfg, args) -> int:
    legacy = args.forras or (os.path.join(os.environ["MOS_LEGACY"], "modulok", "ytdlp", "staging") if os.environ.get("MOS_LEGACY") else None)
    if not legacy:
        print("HIBA: add meg a forrást (--forras <legacy>/modulok/ytdlp/staging) vagy a MOS_LEGACY-t; a legacy útja nincs beégetve", file=sys.stderr)
        return 2
    cel = Path(args.cel or cfg.path("staging"))
    try:
        r = klon.klonoz(legacy, cel, igen=args.igen,
                        archivum_forras=Path(legacy).parent / "archive", archivum_cel=Path(args.cel).parent / "archive" if args.cel else cfg.path("ytdlp_archivum"))
    except klon.KlonHiba as e:
        print(f"HIBA: {e}", file=sys.stderr)
        return 1
    if not args.igen:
        print("\nA klónozáshoz add meg: --igen (a forrásba nem írok, a célt nem írom felül).")
    if args.json:
        _json(r)
    return 0


def _utak(cfg, args) -> tuple[Path, Path]:
    return Path(args.jobs or cfg.path("video_jobs")), Path(args.staging or cfg.path("staging"))


def cmd_utnorm(cfg, args) -> int:
    jobs, stag = _utak(cfg, args)
    r = utnorm.felmeres(jobs, stag)
    if args.json:
        _json(r)
    else:
        print(f"{r['state_json']} state.json a {jobs} alatt; a feloldás gyökerei: staging = {stag}")
        for a, n in r["alakok"].items():
            print(f"  {a:<12} {n:>4} út")
        for k, v in r["kulcsok"].items():
            print(f"  {k:<20} {v['letezik']}/{v['osszes']} létezik, nem oldható fel: {v['nem_oldhato']}")
        if r["nem_letezo_db"]:
            print(f"  {r['nem_letezo_db']} út a jelenlegi gyökerek alatt nem létezik, pl.: {r['nem_letezo'][:2]}")
    return 1 if r["nem_letezo_db"] or r["olvasasi_hibak"] else 0


def cmd_leltar(cfg, args) -> int:
    gyoker = Path(args.staging or cfg.path("staging"))
    sorok = staging.leltar(gyoker)
    if args.json:
        _json(sorok)
        return 0
    allapotok: dict[str, int] = {}
    for s in sorok:
        allapotok[str(s["integration_status"])] = allapotok.get(str(s["integration_status"]), 0) + 1
    hibas = [s for s in sorok if s["hiba"]]
    print(f"{len(sorok)} forrásmappa a {gyoker} alatt; integration_status szerint: {allapotok}; hibás: {len(hibas)}")
    for s in hibas[:10]:
        print(f"  hiba: {s['mappa']}: {s['hiba']}")
    return 0


BEJARAS_FRISS_S = 24 * 3600         # a `--igen` ennél nem régebbi felfedezést újrahasznál (különben újra bejár)


def cmd_bejaras(cfg, args) -> int:
    """`letoltes --bejaras <url>`: 1. felfedezés (csak a lista, letöltés nincs); 2. `--igen`: a még meg nem lévő videók letöltése a
    stagingbe a szokásos úton. A megszakított letöltés ugyanígy újraindítva folytatódik (a már stagingben lévő videó kimarad)."""
    from . import bejaras, lanc
    if args.url:
        print("HIBA: a --bejaras mellé nem adható külön link", file=sys.stderr)
        return 64
    start = args.bejaras.strip()
    try:
        from core.videolanc import urlek_ellenoriz
        from core.tasks import Invalid
        try:
            urlek_ellenoriz([start], 1)
        except Invalid as e:
            print(f"HIBA: {e}", file=sys.stderr)
            return 64
        eredmeny = None if (args.ujra or not args.igen) else bejaras.betolt(cfg, start, BEJARAS_FRISS_S)
        if eredmeny is None:
            eredmeny = bejaras.felfedez(cfg, start, stop_fajl=os.environ.get("MANIFOLD_STOP_FAJL"))
            print(f"A lista mentve: {bejaras.ment(cfg, eredmeny)}")
        else:
            print(f"A legutóbbi bejárás listája ({eredmeny.get('ido')}); újra bejárni: --ujra")
    except Exception as e:  # noqa: BLE001 — az msp típusos hibája (CrawlError, NetworkError…): a hint a felhasználónak szól
        if not hasattr(e, "hint"):
            raise
        print(f"HIBA: {getattr(e, 'message', e)}\n{getattr(e, 'hint', '') or ''}", file=sys.stderr)
        return 1
    megvan = bejaras.megvan_fuggveny(lanc.msp_konfig(cfg))
    for t in eredmeny.get("tetelek") or []:
        t["megvan"] = megvan(t["video"])
    if args.json:
        _json(eredmeny)
    else:
        bejaras.kiir(eredmeny)
    urlek, meglevo = bejaras.letoltendo(eredmeny, megvan)
    if args.max is not None:
        urlek = urlek[:args.max]
    korlat = bejaras.bejaras_max(cfg)
    if not args.igen:
        print(f"\n{len(urlek)} videó letölthető, {meglevo} már megvan. Semmi nem töltődött le. A letöltéshez: "
              f"bin/mos video letoltes --bejaras {start} --igen" + (f" --max {len(urlek)}" if len(urlek) > korlat else ""))
        return 0
    if not urlek:
        print(f"Nincs letöltendő videó ({meglevo} már megvan).")
        return 0
    if len(urlek) > korlat and (args.max is None or args.max < len(urlek)):
        print(f"HIBA: {len(urlek)} videó a [video] bejaras_max ({korlat}) fölött: erősítsd meg a számot: --max {len(urlek)}", file=sys.stderr)
        return 64
    print(f"\nLetöltés: {len(urlek)} videó ({meglevo} már megvan, kimarad). Megállítás: Ctrl-C; újraindítva folytatódik.")
    return lanc.letoltes(cfg, urlek, stop_fajl=os.environ.get("MANIFOLD_STOP_FAJL"))


def cmd_letoltes(cfg, args) -> int:
    from . import lanc
    if getattr(args, "bejaras", None):
        return cmd_bejaras(cfg, args)
    if not args.url:
        print("HIBA: adj meg legalább egy linket, vagy --bejaras <oldal>", file=sys.stderr)
        return 64
    proba = None
    if args.proba:
        proba = cfg.path("tmp") / "video-proba" / config_ido()
        proba.mkdir(parents=True, exist_ok=True)
        print(f"[próba] a staging és az archívum ide kerül: {proba}")
    return lanc.letoltes(cfg, list(args.url), proba_gyoker=proba, stop_fajl=os.environ.get("MANIFOLD_STOP_FAJL"))


def config_ido() -> str:
    import time
    return time.strftime("%Y%m%d-%H%M%S")


def cmd_integral(cfg, args) -> int:
    """C20b: a staging forrásainak bevitele a vaultba (gépi írás, tételenként visszavonható). Az éles írás csak a feladatsor
    lépéseként indul (`MOS_FELADAT`); kézzel a `--proba` fut (a vault APFS-klónjára ír, D9). Kifejezett modell mindig próba."""
    from . import bevitel, integralas
    from .modell import NincsModell
    kif = {"atirat": args.atirat, "tema": args.tema, "kotes": args.kotes}
    if any(kif.values()) and not args.proba:
        print("kifejezett modell csak próbában (--proba) futhat (D9)", file=sys.stderr)
        return 64
    if not args.proba and not os.environ.get("MOS_FELADAT"):
        print("az éles bevitel csak a feladatsor lépéseként indul (a vezérlőből); kézzel: --proba", file=sys.stderr)
        return 64
    mappak = [Path(m) for m in args.mappa]
    if args.csoport:
        uj, hibak = bevitel.csoport(cfg, Path(args.csoport))
        for h in hibak:
            print(f"[bevitel] HIBA: {h}")
        mappak += uj
        if not uj:
            return 1 if hibak else 0
    if args.tema_mappa is not None and not mappak:
        print("a --tema-mappa csak kijelölt forrással (--mappa vagy --csoport) adható meg, nem az összes várakozóra", file=sys.stderr)
        return 64
    try:
        lanc_ = integralas.Integralas(cfg, proba=args.proba, kifejezett=kif,
                                      stop=integralas.Stop(os.environ.get("MANIFOLD_STOP_FAJL")), max_db=args.max,
                                      tema_mappa=args.tema_mappa)
    except ValueError as e:                   # core.videolanc.TemamappaHiba
        print(f"HIBA: {e}", file=sys.stderr)
        return 64
    try:
        r = lanc_.futtat(mappak or None)
    except NincsModell as e:
        print(f"[videó] {e}", file=sys.stderr)
        return 2
    return 1 if r["eredmeny"].get("hiba") else 0


def cmd_lepes(cfg, args) -> int:
    """A `video_letoltes` és a `video_integralas` feladat belső lépése (a feladatsor indítja; `core/videolanc.py`)."""
    from . import halozat_orzo, lanc
    if args.lepes == "integral":
        return cmd_integral(cfg, args)
    if args.lepes == "bejaras":
        return lepes_bejaras(cfg, args)
    if args.lepes == "letoltes":
        if os.environ.get("MOS_VIDEO_HELYI_ENGEDELY") != "1":    # kizárólag a loopback-szerveres tesztek kapcsolója (tests/test_video_e2e.py)
            halozat_orzo.telepit()      # A3-13: a yt-dlp átirányítása és a DNS-újrakötés sem érhet helyi/privát címet
        return lanc.letoltes(cfg, list(args.url), proba_gyoker=Path(args.proba_gyoker) if args.proba_gyoker else None,
                             stop_fajl=os.environ.get("MANIFOLD_STOP_FAJL"), eredmeny_fajl=Path(args.ki) if args.ki else None)
    return 2


def lepes_bejaras(cfg, args) -> int:
    """A `video_bejaras` feladat lépése: felfedezés, az eredmény a `--ki` fájlba (a core onnan adja a felületnek). Letöltés nincs."""
    from . import bejaras, halozat_orzo
    if os.environ.get("MOS_VIDEO_HELYI_ENGEDELY") != "1":    # kizárólag a loopback-szerveres tesztek kapcsolója
        halozat_orzo.telepit()
    if len(args.url) != 1 or not args.ki:
        print("HIBA: egy --url és a --ki kell", file=sys.stderr)
        return 64
    print("[manifold-progress] 0%", flush=True)
    try:
        eredmeny = bejaras.felfedez(cfg, args.url[0], log=lambda s: print(s, flush=True),
                                    stop_fajl=os.environ.get("MANIFOLD_STOP_FAJL"))
    except Exception as e:  # noqa: BLE001
        if not hasattr(e, "hint"):
            raise
        print(f"HIBA: {getattr(e, 'message', e)} {getattr(e, 'hint', '') or ''}", flush=True)
        return 1
    from core import tartos
    ki = Path(args.ki)
    ki.parent.mkdir(parents=True, exist_ok=True)
    tartos.atomi_ir(ki, json.dumps(eredmeny, ensure_ascii=False, indent=1).encode("utf-8"))
    tt = eredmeny["tetelek"]
    print(f"Összegzés: {len(tt)} videó ({sum(1 for t in tt if t.get('megvan'))} már megvan), {eredmeny['oldalak']} oldal olvasva"
          + (" — megszakítva" if eredmeny.get("megszakitva") else ""), flush=True)
    print("[manifold-progress] 100%", flush=True)
    return 0


def _tesztek(cfg, pytest: bool) -> int:
    rc = 0
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    if pytest:
        p = subprocess.run([sys.executable, "-B", "-m", "pytest", "-p", "no:cacheprovider"], cwd=REPO / "modulok" / "ytdlp", env=env)
        rc |= p.returncode
    p = subprocess.run([sys.executable, "-B", "-m", "unittest", "tests.test_video_selftest", "tests.test_video_staging"], cwd=REPO, env=env)
    return rc | p.returncode


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bin/mos video", description=__doc__)
    al = ap.add_subparsers(dest="parancs", required=True)

    p = al.add_parser("eszkoz-ellenorzes", help="ffmpeg, yt-dlp, node a runtime alól")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_eszkoz_ellenorzes)

    p = al.add_parser("felmeres", help="a staging videóinak kodekje (csak olvas)")
    p.add_argument("--staging")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_felmeres)

    p = al.add_parser("staging-klon", help="a legacy staging APFS-klónja méretlistával")
    p.add_argument("--forras", help="a legacy staging (alap: $MOS_LEGACY/modulok/ytdlp/staging)")
    p.add_argument("--cel", help="alap: [utak] staging")
    p.add_argument("--igen", action="store_true", help="a felhasználó jóváhagyása: nélküle csak a méretlista")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_staging_klon)

    p = al.add_parser("utnorm", help="a state.json-ok régi útjainak feloldása (csak olvas)")
    p.add_argument("--jobs")
    p.add_argument("--staging")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_utnorm)

    p = al.add_parser("leltar", help="a staging forrásmappái és integration_status-a (csak olvas)")
    p.add_argument("--staging")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_leltar)

    p = al.add_parser("letoltes", help="linkek letöltése a stagingbe (HÁLÓZAT: D3); --bejaras: egy oldal összes videója")
    p.add_argument("url", nargs="*")
    p.add_argument("--proba", action="store_true", help="a staging és az archívum a {tmp} alá kerül, pillanatkép nincs")
    p.add_argument("--bejaras", metavar="OLDAL", help="az oldal (és az alatta lévő oldalak) összes videója: előbb csak a lista")
    p.add_argument("--igen", action="store_true", help="a bejárás listájának letöltése (nélküle csak a lista)")
    p.add_argument("--ujra", action="store_true", help="a --igen előtt újra bejár (alap: a 24 órán belüli listát használja)")
    p.add_argument("--max", type=int, help="legfeljebb ennyi videó; a [video] bejaras_max fölötti számot ezzel kell megerősíteni")
    p.add_argument("--json", action="store_true", help="a bejárás listája JSON-ban")
    p.set_defaults(fn=cmd_letoltes)

    def integral_kapcsolok(p):
        p.add_argument("--mappa", action="append", default=[], help="staging-forrásmappa (vagy szülő); alap: a `pending` források")
        p.add_argument("--csoport", help="a behúzott fájlok beérkező csoportja ({video_bejovo}/<csoport>)")
        p.add_argument("--proba", action="store_true", help="a gépi írás a vault APFS-klónjára (D9)")
        p.add_argument("--atirat", help="kifejezett átirat-modell (csak próbában)")
        p.add_argument("--tema", help="kifejezett téma-modell (csak próbában)")
        p.add_argument("--kotes", help="kifejezett kötés-modell (csak próbában)")
        p.add_argument("--max", type=int)
        p.add_argument("--tema-mappa", metavar="MAPPA",
                       help="kényszerített célmappa (pl. \"D13 - CS50\"): a téma-modell nem fut, a mellékletek a <MAPPA>/Média alá; "
                            "csak --mappa/--csoport mellett (86. döntés, javasolt)")

    p = al.add_parser("integral", help="C20b: a staging forrásainak bevitele a vaultba (kézzel csak --proba)")
    integral_kapcsolok(p)
    p.set_defaults(fn=cmd_integral)

    p = al.add_parser("lepes", help="a feladat belső lépése (a feladatsor indítja)")
    p.add_argument("lepes", choices=["letoltes", "integral", "bejaras"])
    p.add_argument("--url", action="append", default=[])
    p.add_argument("--ki", help="bejaras: az eredmény JSON-fájlja; letoltes: a letöltött forrásmappák listája (a core bevitele)")
    p.add_argument("--proba-gyoker")
    integral_kapcsolok(p)
    p.set_defaults(fn=cmd_lepes)

    p = al.add_parser("selftest", help="a portolt média-selftest (modell, hálózat és vault-író nélkül)")
    p.set_defaults(fn=lambda cfg, a: _tesztek(cfg, pytest=False))
    p = al.add_parser("test", help="az msp pytest-készlete + a portolt média-selftest")
    p.set_defaults(fn=lambda cfg, a: _tesztek(cfg, pytest=True))

    args = ap.parse_args(argv)
    return int(args.fn(config.load(), args) or 0)


if __name__ == "__main__":
    sys.exit(main())
