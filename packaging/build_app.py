"""A `Manifold.app` termék-csomag építése (F9; PLAN §7, P5) — a héj (`shell/build.sh` kimenete) + a kódfa + a futtatókörnyezet.

Elrendezés (a `core/config.py` termék-elrendezése, `[elrendezes.termek]`):
    Manifold.app/Contents/
      MacOS/Manifold                    a Swift héj (a `shell/build.sh` fordítja; itt csak másolódik)
      Resources/epites.json             a BEFAGYASZTOTT build-jegyzék (verzió, commit, build-idő, fájl-hash-ek; `core/epites.py`)
      Resources/manifold/               a kódfa ({os}; csak olvasható, semmi nem ír bele)
        bin/mos  core/  modulok/  config/ (presetek nélkül)  app/dist/  docs/user/
        runtime/python                  hordozható CPython (python-build-standalone)
        runtime/venv                    RELOKÁLHATÓ venv (`relokacio.py`)
        runtime/ffmpeg/ffmpeg           a videólánc pinelt ffmpeg-je (ha van)
        runtime/node/bin/node           csak a videó-modulhoz (ha van)
        runtime/git                     hordozható git (RUNTIME_PREFIX; `hordozhato_git.py`)

Lépések: előfeltételek (a héj- és a felület-build friss-e a forráshoz; a hordozható git megvan-e) → staging-mappa a
`<kimenet>/.epites-<pid>` alatt → kódfa (a git által látott fájlok, a `.gitattributes` export-ignore és a csomagoló
kizárásai nélkül) → runtime → bájtkód (checked-hash, a forrásút levágva: a csomagba futás közben semmi nem ír) → Info.plist
verzió → `epites.json` befagyasztás → tartalom-ellenőrzés (`csomag_tartalom.py`) és önellenőrzés → aláírás (opció) →
a kész csomag a `<kimenet>/Manifold.app` helyére. Hálózat nincs (D3): a venv a helyi wheelhouse-ból épül.

    python packaging/build_app.py epit [--kimenet var/build] [--venv epit|masol --venv-forras <venv>] [--git-nelkul]
                                       [--elavult-ok] [--alairas nincs|adhoc|identitas] [--dmg | --dmg-dry-run] …
    python packaging/build_app.py ellenoriz <Manifold.app> [--max-mb N]
    python packaging/build_app.py dmg <Manifold.app> [--kimenet <x.dmg>] [--dry-run]
    python packaging/build_app.py alair <Manifold.app> --mod adhoc|identitas
    python packaging/build_app.py notarizal <x.dmg>
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import plistlib
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from csomag_kozos import (APP_NEV, KOD_ALUT, REPO, CsomagHiba, Futtato, Naplo, bajtkod_torles,  # noqa: E402
                          forras_fajlok, futtat, klonoz, utvonal_beallit)

utvonal_beallit()
import alairas  # noqa: E402
import csomag_tartalom  # noqa: E402
import dmg_keszito  # noqa: E402
import hordozhato_git  # noqa: E402
import relokacio  # noqa: E402
from core import epites  # noqa: E402


@dataclass
class Beallitasok:
    repo: Path = REPO
    kimenet: Path = REPO / "var" / "build"
    hej_app: Path = REPO / APP_NEV
    dist: Path = REPO / "app" / "dist"
    python: Path = REPO / "runtime" / "python"
    venv_mod: str = "epit"                               # epit | masol
    venv_forras: Path | None = None
    uv: Path = REPO / "runtime" / "uv"
    wheels: Path = REPO / "runtime" / "wheels"
    lock: Path = REPO / "config" / "requirements.lock"
    uv_cache: Path = REPO / "var" / "cache" / "uv"
    ffmpeg: Path | None = REPO / "runtime" / "ffmpeg" / "ffmpeg"
    node: Path | None = REPO / "runtime" / "node" / "bin" / "node"
    git: Path | None = REPO / "runtime" / "git"
    git_nelkul: bool = False
    elavult_ok: bool = False
    bajtkod: bool = True
    alairas: str = "nincs"
    verzio: str | None = None
    build_szam: str | None = None
    tartalom_max_mb: int | None = None
    tiltott_extra: tuple[str, ...] = ()
    figyelmeztetesek: list[str] = field(default_factory=list)


@dataclass
class Eredmeny:
    app: Path
    epites: dict
    figyelmeztetesek: list[str]
    tartalom: csomag_tartalom.Jelentes


def _json(p: Path) -> dict:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise CsomagHiba("jegyzek_hianyzik", f"nem olvasható build-jegyzék: {p} ({e})") from e
    if not isinstance(d, dict):
        raise CsomagHiba("jegyzek_hibas", f"érvénytelen build-jegyzék: {p}")
    return d


def _friss(b: Beallitasok, resz: str, epult: str, javitas: str, naplo) -> None:
    """A forrás-build egyezik-e a mostani forrással; ha nem: hiba, vagy `--elavult-ok` mellett figyelmeztetés a jegyzékben."""
    most = epites.ujjlenyomat(b.repo, resz)
    if epult == most:
        return
    uzenet = f"a(z) {resz} buildje elavult a forráshoz képest (build: {epult[:12]}, forrás: {most[:12]}) — {javitas}"
    if not b.elavult_ok:
        raise CsomagHiba(f"{resz}_elavult", uzenet + " (vagy --elavult-ok: fejlesztői próba-csomag)")
    b.figyelmeztetesek.append(uzenet)
    naplo("FIGYELEM: " + uzenet)


def elofeltetelek(b: Beallitasok, futtato: Futtato, naplo) -> dict:
    """Mi kell a csomaghoz, és megvan-e → a forrás-buildek azonosítói és a git állapota."""
    ki: dict = {}
    hej = b.hej_app / "Contents" / "MacOS" / "Manifold"
    if not (hej.is_file() and os.access(hej, os.X_OK)):
        raise CsomagHiba("hej_hianyzik", f"nincs lefordított héj: {hej} — futtasd: bash shell/build.sh")
    ki["hej"] = str(_json(b.hej_app / "Contents" / "Resources" / "epites.json").get("hej") or "")
    _friss(b, "hej", ki["hej"], "futtasd: bash shell/build.sh", naplo)
    if not (b.dist / "index.html").is_file():
        raise CsomagHiba("felulet_hianyzik", f"nincs felület-build: {b.dist / 'index.html'} — futtasd: bin/mos app build")
    ki["felulet"] = str(_json(b.dist / "epites.json").get("felulet") or "")
    _friss(b, "felulet", ki["felulet"], "futtasd: bin/mos app build", naplo)
    if not (b.python / "bin" / "python3").exists():
        raise CsomagHiba("python_hianyzik", f"nincs hordozható Python: {b.python} — bin/mos runtime fetch")
    if b.venv_mod == "masol":
        if b.venv_forras is None or not (b.venv_forras / "pyvenv.cfg").is_file():
            raise CsomagHiba("venv_forras_hianyzik", f"a --venv masol módhoz egy meglévő venv kell (--venv-forras): {b.venv_forras}")
    elif b.venv_mod != "epit":
        raise CsomagHiba("venv_mod", f"ismeretlen venv-mód: {b.venv_mod} (epit | masol)")
    if b.git_nelkul or b.git is None:
        ki["git"] = None
        uz = "a csomagban nincs hordozható git: a gépi pillanatképek a rendszer-gitet (Xcode Command Line Tools) használják"
        b.figyelmeztetesek.append(uz)
        naplo("FIGYELEM: " + uz)
    else:
        ki["git"] = hordozhato_git.kotelezo(b.git, futtato)
    for nev, ut in (("ffmpeg", b.ffmpeg), ("node", b.node)):
        if ut is not None and not ut.is_file():
            uz = f"nincs {nev} ({ut}): a videólánc ebben a csomagban nem fut (bin/mos runtime fetch)"
            b.figyelmeztetesek.append(uz)
            naplo("FIGYELEM: " + uz)
    return ki


def _kodfa(b: Beallitasok, root: Path, naplo) -> int:
    fajlok = forras_fajlok(b.repo)
    for rel in fajlok:
        cel = root / rel
        cel.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(b.repo / rel, cel, follow_symlinks=False)
    n = len(fajlok)
    for dp, almappak, nevek in os.walk(b.dist):
        almappak[:] = [a for a in almappak if not a.startswith(".")]
        for f in nevek:
            if f.startswith("."):
                continue
            src = Path(dp, f)
            cel = root / "app" / "dist" / src.relative_to(b.dist)
            cel.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, cel, follow_symlinks=False)
            n += 1
    naplo(f"kódfa: {n} fájl")
    return n


def _runtime(b: Beallitasok, root: Path, git_info, futtato: Futtato, naplo) -> dict:
    rt = root / "runtime"
    rt.mkdir(parents=True, exist_ok=True)
    klonoz(b.python, rt / "python")
    bajtkod_torles(rt / "python")
    naplo(f"runtime/python: {b.python}")
    venv = rt / "venv"
    if b.venv_mod == "epit":
        naplo("runtime/venv: uv, offline, a wheelhouse-ból (requirements.lock hash-ei)")
        relokacio.venv_epit(uv=b.uv, python_mappa=rt / "python", cel=venv, wheels=b.wheels, lock=b.lock, cache=b.uv_cache,
                            futtato=futtato)
    else:
        naplo(f"runtime/venv: másolat ({b.venv_forras})")
        relokacio.venv_masol(b.venv_forras, venv)
    valtozas = relokacio.relokal(venv, rt / "python")
    hibak = relokacio.ellenoriz(venv, rt / "python")
    if hibak:
        raise CsomagHiba("venv_relokacio", "a venv nem relokálható: " + "; ".join(hibak[:10]))
    relokacio.futtathato_proba(venv, futtato)
    naplo(f"runtime/venv: relokálva ({len(valtozas)} változtatás)")
    info: dict = {"python": relokacio.python_verzio_nev(rt / "python").removeprefix("python")}
    if b.ffmpeg is not None and b.ffmpeg.is_file():
        (rt / "ffmpeg").mkdir()
        shutil.copy2(b.ffmpeg, rt / "ffmpeg" / "ffmpeg")
        info["ffmpeg"] = True
    if b.node is not None and b.node.is_file():
        (rt / "node" / "bin").mkdir(parents=True)
        shutil.copy2(b.node, rt / "node" / "bin" / "node")
        lic = b.node.parent.parent / "LICENSE"
        if lic.is_file():
            shutil.copy2(lic, rt / "node" / "LICENSE")
        info["node"] = True
    if git_info is not None:
        klonoz(b.git, rt / "git")
        bajtkod_torles(rt / "git")
        info["git"] = hordozhato_git.ellenoriz_helyben(rt / "git", futtato).szotar()
    else:
        info["git"] = None
    return info


def _bajtkod(root: Path, futtato: Futtato, naplo, figyelmeztetesek: list[str]) -> None:
    """Előfordított bájtkód (checked-hash: a forrás hash-ével ellenőrzött, mtime-független — a csomag másolása után is érvényes,
    futás közben semmi nem ír; a forrásút a csomag gyökeréig levágva, fejlesztői út nem kerül a .pyc-be)."""
    py = root / "runtime" / "venv" / "bin" / "python"
    mappak = [root / "core", root / "modulok", *sorted((root / "runtime" / "python" / "lib").glob("python3.*")),
              *sorted((root / "runtime" / "venv" / "lib").glob("python3.*"))]
    env = {"PATH": "/usr/bin:/bin"}
    # -B: a fordító folyamat saját importjai ne hagyjanak (abszolút utas) bájtkódot; -f: minden fájl újrafordul
    p = futtato([py, "-I", "-B", "-m", "compileall", "-f", "-q", "-j", "0", "--invalidation-mode", "checked-hash", "-s", str(root),
                 *map(str, mappak)], env=env, check=False, timeout=3600)
    if p.returncode != 0:
        hibas = sum(1 for s in (p.stdout or "").splitlines() if s.startswith("***"))
        uz = f"a bájtkód-fordítás {hibas or 'néhány'} fájlnál hibát jelzett (ezek futáskor forrásból töltődnek)"
        figyelmeztetesek.append(uz)
        naplo("FIGYELEM: " + uz)
    naplo("bájtkód: kész (checked-hash)")


def _git_adatok(repo: Path, futtato: Futtato) -> tuple[str, bool]:
    p = futtato(["git", "-C", repo, "rev-parse", "HEAD"], check=False)
    commit = p.stdout.strip() if p.returncode == 0 else ""
    s = futtato(["git", "-C", repo, "status", "--porcelain"], check=False)
    return commit, (s.returncode == 0 and not s.stdout.strip())


def _epitve() -> str:
    sde = os.environ.get("SOURCE_DATE_EPOCH")
    t = dt.datetime.fromtimestamp(int(sde), dt.UTC) if sde and sde.isdigit() else dt.datetime.now(dt.UTC)
    return t.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _info_plist(app: Path, b: Beallitasok) -> tuple[str, str]:
    p = app / "Contents" / "Info.plist"
    with open(p, "rb") as fh:
        d = plistlib.load(fh)
    if b.verzio:
        d["CFBundleShortVersionString"] = b.verzio
    if b.build_szam:
        d["CFBundleVersion"] = b.build_szam
    with open(p, "wb") as fh:
        plistlib.dump(d, fh)
    return str(d.get("CFBundleShortVersionString", "")), str(d.get("CFBundleVersion", ""))


def epit(b: Beallitasok, *, futtato: Futtato = futtat, naplo=print) -> Eredmeny:
    kezdet = time.monotonic()
    b.kimenet = Path(b.kimenet).resolve()
    b.figyelmeztetesek = []
    elo = elofeltetelek(b, futtato, naplo)
    staging = b.kimenet / f".epites-{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        app = staging / APP_NEV
        klonoz(b.hej_app, app)
        root = app / KOD_ALUT
        if root.exists():
            raise CsomagHiba("hej_tartalom", f"a héj-build már tartalmaz kódfát ({root}): a shell/build.sh kimenetét add meg")
        _kodfa(b, root, naplo)
        info = _runtime(b, root, elo["git"], futtato, naplo)
        if b.bajtkod:
            _bajtkod(root, futtato, naplo, b.figyelmeztetesek)
        termek_verzio, build = _info_plist(app, b)
        commit, tiszta = _git_adatok(b.repo, futtato)
        if not tiszta:
            b.figyelmeztetesek.append("a forrás munkafája nem tiszta (nem commitolt változások): a commit nem írja le pontosan a csomagot")
        jegyzek = epites.befagyaszt(root, termek_verzio=termek_verzio, build=build, commit=commit, tiszta=tiszta,
                                    epitve=_epitve(), felulet=elo["felulet"], hej=elo["hej"],
                                    egyeb={**info, "bajtkod": b.bajtkod, "alairas": b.alairas,
                                           "figyelmeztetesek": list(b.figyelmeztetesek)})
        (app / "Contents" / "Resources" / "epites.json").write_text(json.dumps(jegyzek, ensure_ascii=False, indent=1) + "\n",
                                                                     encoding="utf-8")
        naplo(f"epites.json: {termek_verzio} ({build}), commit {commit[:12] or '-'}{'' if tiszta else ' (+helyi változások)'}, "
              f"{len(jegyzek['csomag']['fajlok'])} fájl-hash")
        tiltott = csomag_tartalom.alap_tiltott_szovegek(b.repo, extra=[str(b.kimenet), str(staging), *b.tiltott_extra])
        jel = csomag_tartalom.ellenoriz(app, tiltott_szovegek=tiltott, repo=b.repo,
                                        max_bajt=b.tartalom_max_mb * 2**20 if b.tartalom_max_mb else None)
        if not jel.ok:
            raise CsomagHiba("tartalom", f"a csomag-tartalom ellenőrzése {len(jel.hibak)} hibát talált:\n  "
                                         + "\n  ".join(jel.hibak[:30]))
        naplo(f"tartalom: tiszta ({jel.fajlok} fájl, {jel.bajt / 2**20:.0f} MB)")
        ell = epites.csomag_ellenoriz(root, jegyzek, runtime=True)
        if not ell["ok"]:
            raise CsomagHiba("onellenorzes", f"a kész csomag nem egyezik a saját jegyzékével: {ell}")
        alairas.alair(app, b.alairas, futtato=futtato, naplo=naplo)
        cel = b.kimenet / APP_NEV
        if cel.exists():
            regi = b.kimenet / f".regi-{os.getpid()}-{int(time.time())}"
            cel.rename(regi)
            shutil.rmtree(regi, ignore_errors=True)
        app.rename(cel)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    naplo(f"kész: {cel} ({time.monotonic() - kezdet:.0f} s)" + (f"; {len(b.figyelmeztetesek)} figyelmeztetés"
                                                               if b.figyelmeztetesek else ""))
    return Eredmeny(cel, jegyzek, list(b.figyelmeztetesek), jel)


def ellenoriz_app(app: Path, *, max_mb: int | None = None, naplo=print) -> bool:
    """Egy kész csomag: tartalom + integritás (a futtatókörnyezettel együtt)."""
    root = app / KOD_ALUT
    jel = csomag_tartalom.ellenoriz(app, max_bajt=max_mb * 2**20 if max_mb else None)
    for h in jel.hibak[:50]:
        naplo("HIBA: " + h)
    ell = epites.csomag_ellenoriz(root, runtime=True)
    if not ell["jegyzek"]:
        naplo("HIBA: nincs befagyasztott jegyzék (Contents/Resources/epites.json `csomag` kulcs)")
    for k in ("modositott", "hianyzik", "tobblet", "runtime_elteres"):
        if ell[k]:
            naplo(f"HIBA: {k}: {', '.join(ell[k][:10])}")
    naplo(f"tartalom: {len(jel.hibak)} hiba ({jel.fajlok} fájl); integritás: {'rendben' if ell['ok'] else 'ELTÉR'} "
          f"({ell['ellenorizve']} fájl)")
    return jel.ok and ell["ok"]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="build_app.py")
    al = ap.add_subparsers(dest="parancs", required=True)
    e = al.add_parser("epit")
    e.add_argument("--kimenet", type=Path, default=Beallitasok.kimenet)
    e.add_argument("--hej", type=Path, default=Beallitasok.hej_app)
    e.add_argument("--dist", type=Path, default=Beallitasok.dist)
    e.add_argument("--python", type=Path, default=Beallitasok.python)
    e.add_argument("--venv", choices=("epit", "masol"), default="epit")
    e.add_argument("--venv-forras", type=Path)
    e.add_argument("--git", type=Path, default=Beallitasok.git)
    e.add_argument("--git-nelkul", action="store_true")
    e.add_argument("--nincs-ffmpeg", action="store_true")
    e.add_argument("--nincs-node", action="store_true")
    e.add_argument("--elavult-ok", action="store_true")
    e.add_argument("--nincs-bajtkod", action="store_true")
    e.add_argument("--alairas", choices=alairas.MODOK, default="nincs")
    e.add_argument("--verzio")
    e.add_argument("--build")
    e.add_argument("--tartalom-max-mb", type=int)
    e.add_argument("--dmg", action="store_true")
    e.add_argument("--dmg-dry-run", action="store_true")
    e.add_argument("--notarizal", action="store_true")
    c = al.add_parser("ellenoriz")
    c.add_argument("app", type=Path)
    c.add_argument("--max-mb", type=int)
    d = al.add_parser("dmg")
    d.add_argument("app", type=Path)
    d.add_argument("--kimenet", type=Path)
    d.add_argument("--dry-run", action="store_true")
    s = al.add_parser("alair")
    s.add_argument("app", type=Path)
    s.add_argument("--mod", choices=("adhoc", "identitas"), required=True)
    n = al.add_parser("notarizal")
    n.add_argument("dmg", type=Path)
    a = ap.parse_args(argv)
    naplo = Naplo([])
    try:
        if a.parancs == "epit":
            b = Beallitasok(kimenet=a.kimenet, hej_app=a.hej, dist=a.dist, python=a.python, venv_mod=a.venv,
                            venv_forras=a.venv_forras, git=a.git, git_nelkul=a.git_nelkul,
                            ffmpeg=None if a.nincs_ffmpeg else Beallitasok.ffmpeg,
                            node=None if a.nincs_node else Beallitasok.node, elavult_ok=a.elavult_ok,
                            bajtkod=not a.nincs_bajtkod, alairas=a.alairas, verzio=a.verzio, build_szam=a.build,
                            tartalom_max_mb=a.tartalom_max_mb)
            r = epit(b, naplo=naplo)
            if a.dmg or a.dmg_dry_run:
                dmg = r.app.parent / f"Manifold-{r.epites['csomag']['termek_verzio']}.dmg"
                dmg_keszito.keszit(r.app, dmg, dry_run=a.dmg_dry_run, naplo=naplo)
                if a.notarizal and not a.dmg_dry_run:
                    alairas.notarizal(dmg, naplo=naplo)
            for f in r.figyelmeztetesek:
                naplo("figyelmeztetés: " + f)
        elif a.parancs == "ellenoriz":
            return 0 if ellenoriz_app(a.app, max_mb=a.max_mb, naplo=naplo) else 1
        elif a.parancs == "dmg":
            dmg_keszito.keszit(a.app, a.kimenet or a.app.parent / "Manifold.dmg", dry_run=a.dry_run, naplo=naplo)
        elif a.parancs == "alair":
            alairas.alair(a.app, a.mod, naplo=naplo)
        elif a.parancs == "notarizal":
            alairas.notarizal(a.dmg, naplo=naplo)
        return 0
    except CsomagHiba as e:
        naplo(f"HIBA ({e.kod}): {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
