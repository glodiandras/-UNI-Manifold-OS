"""CX-001: forrásujjlenyomat, a kiadott frontend és natív héj frissessége.

Az ujjlenyomat forrása (A-javító, 2026-10-14): a rész útjai alatt a git által látott fájlok (`git ls-files --cached --others
--exclude-standard`: a követett és a még nem követett, de nem kizárt fájlok). A `.gitignore` kizárja a `modulok/ytdlp/staging`
videóit (több tíz GB), az archívumot, a `__pycache__`-t és a `.DS_Store`-t. Ha a gyökér nem a git munkafájának gyökere, vagy a git
nem érhető el, a tartalék a fájlrendszer bejárása a `KIHAGY_MAPPAK` és a rejtett nevek nélkül; ott `FAJL_MAX_BAJT` fölött csak a
méret számít. A fájlok darabolva hashelődnek (nincs egész fájlos `read_bytes`).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

RESZEK = {
    "felulet": ("app/src", "app/index.html", "app/package.json", "app/package-lock.json", "app/vite.config.ts",
                "app/svelte.config.js", "app/tsconfig.json"),
    "mag": ("core", "modulok"),
    "hej": ("shell/Sources", "shell/Resources", "shell/Info.plist", "shell/build.sh"),
}

# A tartalék bejárás (git nélkül) ezeket a mappákat kihagyja: nem forrás, és lehet óriási (a staging videói)
KIHAGY_MAPPAK = frozenset({"staging", "archive", "logs", "__pycache__", ".pytest_cache", "node_modules", "dist"})
KIHAGY_KITERJESZTES = (".pyc", ".pyo")
FAJL_MAX_BAJT = 64 << 20        # a tartalék bejárásban e fölött a tartalom nem olvasódik, csak a méret számít
GIT_IDOKORLAT_MP = 30
HEJ_VALTOZATOK = ("fejlesztoi", "kiadasi")


def _git_fajlok(root: Path, utak: tuple[str, ...]) -> list[str] | None:
    """A rész útjai alatt a git által látott fájlok (gyökér-relatív, `/`-os utak), vagy None: nincs git, vagy a `root` nem a
    munkafa gyökere (pl. egy álgyökér egy másik tároló kizárt mappájában — ott az üres lista hamis volna)."""
    from .snapshot import hermetikus_env
    env = {**hermetikus_env(), "GIT_OPTIONAL_LOCKS": "0"}
    try:
        top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, env=env,
                             timeout=GIT_IDOKORLAT_MP)
        if top.returncode != 0 or Path(os.fsdecode(top.stdout.strip())).resolve() != root.resolve():
            return None
        p = subprocess.run(["git", "-C", str(root), "-c", "core.quotepath=false", "ls-files", "-z", "--cached", "--others",
                            "--exclude-standard", "--", *utak], capture_output=True, env=env, timeout=GIT_IDOKORLAT_MP)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    return sorted({os.fsdecode(x) for x in p.stdout.split(b"\0") if x})


def _bejart_fajlok(root: Path, utak: tuple[str, ...]) -> list[str]:
    """Tartalék (git nélkül): a rész útjai alatti fájlok, a `KIHAGY_MAPPAK`, a rejtett nevek és a bájtkód nélkül."""
    ki = []
    for nev in utak:
        p = root / nev
        if p.is_file():
            ki.append(nev)
            continue
        for dp, almappak, fajlok in os.walk(p):
            almappak[:] = [a for a in almappak if a not in KIHAGY_MAPPAK and not a.startswith(".")]
            for f in fajlok:
                if f.startswith(".") or f.endswith(KIHAGY_KITERJESZTES):
                    continue
                ki.append(Path(dp, f).relative_to(root).as_posix())
    return sorted(set(ki))


def ujjlenyomat(root: Path, resz: str) -> str:
    """A rész forrásainak ujjlenyomata (sha256): fájlonként a relatív út és a tartalom hash-e, az út szerint rendezve."""
    root = Path(root)
    utak = RESZEK[resz]
    fajlok = _git_fajlok(root, utak)
    tartalek = fajlok is None
    if tartalek:
        fajlok = _bejart_fajlok(root, utak)
    h = hashlib.sha256()
    for rel in fajlok:
        p = root / rel
        if "__pycache__" in p.parts or p.suffix in KIHAGY_KITERJESZTES:
            continue
        try:
            if not p.is_file():         # a követett, de törölt fájl, almodul-mappa
                continue
            meret = p.stat().st_size
            if tartalek and meret > FAJL_MAX_BAJT:
                tartalom = f"meret:{meret}".encode()
            else:
                with open(p, "rb") as fh:
                    tartalom = hashlib.file_digest(fh, "sha256").digest()
        except OSError:
            continue
        h.update(rel.encode() + b"\0")
        h.update(tartalom)
    return h.hexdigest()


def jegyzek(root: Path, *, hej_valtozat: str | None = None) -> dict:
    """A forrásujjlenyomatok és — csak natív héj építésekor — az explicit build-változat.

    A változat nem ujjlenyomat: azonos forrásból is lehet fejlesztői és kiadási bináris. A felület változatlanul a változat
    nélküli jegyzéket kapja, a héj beégetett JS-rekordja és lemezes jegyzéke ugyanazt az explicit értéket kapja.
    """
    if hej_valtozat is not None and hej_valtozat not in HEJ_VALTOZATOK:
        raise ValueError("Unknown native shell build variant")
    j = {"verzio": 1, **{r: ujjlenyomat(root, r) for r in RESZEK}}
    if hej_valtozat is not None:
        j["hej_valtozat"] = hej_valtozat
    return j


def _hej_valtozat(j: dict) -> dict:
    """Additív metaadat: a régi/hiányzó/ismeretlen változat nem állítható kiadásinak, és nem változtatja a hash-kaput."""
    v = j.get("hej_valtozat")
    return {"hej_valtozat": v} if v in HEJ_VALTOZATOK else {}


# ------------------------------------------------------------------ a csomag befagyasztott jegyzéke (F9)
#
# A termék-csomagban (`<X>.app/Contents/Resources/manifold`) nincs forrás (`app/src`, `shell/`) és nincs `.git`: a build
# jegyzéke a csomagolás pillanatában befagyasztva a `Contents/Resources/epites.json`-ban áll (a héj jegyzékének bővítése,
# `verzio: 1` marad, a `csomag` kulcs új). A `csomag` tartalma: a termék verziója, a forrás commitja (és hogy tiszta volt-e a
# munkafa), a build ideje (UTC), a kódfa fájljainak sha256-ja (`fajlok`) és a futtatókörnyezet mappáinak összesítő hash-e
# (`runtime`). A futó core ehhez méri a csomagot (`csomag_ellenoriz`): a `/api/rendszer/epites` és a Health `telepites` sora
# mutatja, ha a build után bármi megváltozott, hiányzik vagy többlet.

CSOMAG_FORMATUM = 1
CSOMAG_KOD_MAPPAK = ("bin", "core", "modulok", "config", "app/dist", "docs/user")   # fájlonkénti hash (gyors, minden ellenőrzéskor)
CSOMAG_RUNTIME = "runtime"                                                           # mappánkénti összesítő (lassú: csak kérésre)
_CSOMAG_KIHAGY_NEV = frozenset({"__pycache__", ".DS_Store"})


def _fajl_sha(p: Path) -> str:
    if p.is_symlink():
        return "link:" + os.readlink(p)
    with open(p, "rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def csomag_fajlok(root: Path, mappak: tuple[str, ...] = CSOMAG_KOD_MAPPAK) -> dict[str, str]:
    """A kódfa fájljai → sha256 (gyökér-relatív, `/`-os utak; a bájtkód és a `.DS_Store` nélkül; symlink: a célja)."""
    root = Path(root)
    ki: dict[str, str] = {}
    for nev in mappak:
        alap = root / nev
        if alap.is_file() or alap.is_symlink():
            ki[nev] = _fajl_sha(alap)
            continue
        for dp, almappak, fajlok in os.walk(alap):
            almappak[:] = sorted(a for a in almappak if a not in _CSOMAG_KIHAGY_NEV)
            for f in fajlok:
                if f in _CSOMAG_KIHAGY_NEV or f.endswith(KIHAGY_KITERJESZTES):
                    continue
                p = Path(dp, f)
                ki[p.relative_to(root).as_posix()] = _fajl_sha(p)
            for a in list(almappak):                  # a mappára mutató symlinket az os.walk nem járja be: a célja számít
                if Path(dp, a).is_symlink():
                    ki[Path(dp, a).relative_to(root).as_posix()] = _fajl_sha(Path(dp, a))
                    almappak.remove(a)
    return dict(sorted(ki.items()))


def runtime_osszesito(root: Path) -> dict[str, dict]:
    """A `runtime/` közvetlen almappái → {fajl: darab, sha256: összesítő} (az út és a tartalom hash-e, út szerint rendezve)."""
    rt = Path(root) / CSOMAG_RUNTIME
    ki: dict[str, dict] = {}
    if not rt.is_dir():
        return ki
    for d in sorted(x for x in rt.iterdir() if x.is_dir() and not x.is_symlink()):
        fajlok = csomag_fajlok(rt, (d.name,))
        h = hashlib.sha256()
        for rel, sha in fajlok.items():
            h.update(rel.encode() + b"\0" + sha.encode() + b"\n")
        ki[d.name] = {"fajl": len(fajlok), "sha256": h.hexdigest()}
    return ki


def fagyott_ut(root: Path) -> Path:
    """A befagyasztott jegyzék helye: a csomag `Contents/Resources/epites.json`-ja (a gyökér szülőmappájában)."""
    return Path(root).parent / "epites.json"


def fagyott(root: Path) -> dict | None:
    """A csomag befagyasztott jegyzéke, vagy None (nem csomag-gyökér, nincs, nem érvényes, vagy nincs benne `csomag`)."""
    from .gyoker_kereso import termek_gyoker
    if not termek_gyoker(root):
        return None
    try:
        d = json.loads(fagyott_ut(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not (isinstance(d, dict) and d.get("verzio") == 1 and all(isinstance(d.get(r), str) for r in RESZEK)
            and isinstance(d.get("csomag"), dict) and isinstance(d["csomag"].get("fajlok"), dict)):
        return None
    return d


def befagyaszt(root: Path, *, termek_verzio: str, build: str, commit: str, tiszta: bool, epitve: str, felulet: str,
               hej: str, runtime: bool = True, egyeb: dict | None = None, hej_valtozat: str | None = None) -> dict:
    """A csomag jegyzéke a KÉSZ kódfából (`root` = a csomag `manifold` mappája): a `mag` a csomagban újraszámolva (ugyanazzal
    a bejárással, amellyel a futó core méri), a `felulet` és a `hej` a forrás-buildek jegyzékéből."""
    if hej_valtozat is not None and hej_valtozat not in HEJ_VALTOZATOK:
        raise ValueError("Unknown native shell build variant")
    cs = {"formatum": CSOMAG_FORMATUM, "termek_verzio": termek_verzio, "build": build, "commit": commit, "tiszta": tiszta,
          "epitve": epitve, "fajlok": csomag_fajlok(root)}
    if runtime:
        cs["runtime"] = runtime_osszesito(root)
    if egyeb:
        cs.update(egyeb)
    return {"verzio": 1, "felulet": felulet, "mag": ujjlenyomat(root, "mag"), "hej": hej, "csomag": cs,
            **_hej_valtozat({"hej_valtozat": hej_valtozat})}


def csomag_ellenoriz(root: Path, jegyzek_: dict | None = None, *, runtime: bool = False) -> dict:
    """A csomag összevetése a befagyasztott jegyzékkel → `{ok, ellenorizve, hianyzik, modositott, tobblet, runtime_elteres}`.
    A `tobblet` a lefedett mappák (`CSOMAG_KOD_MAPPAK`) új fájljai; `runtime=True`: a futtatókörnyezet összesítője is."""
    j = jegyzek_ if jegyzek_ is not None else fagyott(root)
    if j is None:
        return {"ok": False, "jegyzek": False, "ellenorizve": 0, "hianyzik": [], "modositott": [], "tobblet": [],
                "runtime_elteres": []}
    vart: dict[str, str] = j["csomag"]["fajlok"]
    van = csomag_fajlok(root)
    hianyzik = sorted(k for k in vart if k not in van)
    modositott = sorted(k for k in vart if k in van and van[k] != vart[k])
    tobblet = sorted(k for k in van if k not in vart)
    rt_elteres: list[str] = []
    if runtime and isinstance(j["csomag"].get("runtime"), dict):
        most = runtime_osszesito(root)
        rt_elteres = sorted(k for k in set(most) | set(j["csomag"]["runtime"]) if most.get(k) != j["csomag"]["runtime"].get(k))
    return {"ok": not (hianyzik or modositott or tobblet or rt_elteres), "jegyzek": True, "ellenorizve": len(vart),
            "hianyzik": hianyzik, "modositott": modositott, "tobblet": tobblet, "runtime_elteres": rt_elteres}


def _csomag_allapot(root: Path, futo: dict | None) -> dict:
    """A termék-csomag frissessége: a befagyasztott jegyzékhez (forrás nincs a csomagban, újraszámolni nem lehet)."""
    j = fagyott(root)
    reszek = []
    if j is None:
        vart = {r: "" for r in RESZEK}
        reszek.append({"resz": "csomag", "friss": False, "azonosito": "", "elteres": ["csomag"]})
        cs_info = {"jegyzek": False}
    else:
        vart = {r: j[r] for r in RESZEK}
        try:
            dist = json.loads((Path(root) / "app" / "dist" / "epites.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            dist = {}
        felulet = dist.get("felulet") if isinstance(dist, dict) else None
        reszek.append({"resz": "felulet", "friss": felulet == vart["felulet"], "azonosito": str(felulet or "")[:12],
                       "elteres": [] if felulet == vart["felulet"] else ["felulet"]})
        reszek.append({"resz": "hej", "friss": True, "azonosito": vart["hej"][:12], "elteres": [], **_hej_valtozat(j)})
        ell = csomag_ellenoriz(root, j)
        cs = j["csomag"]
        reszek.append({"resz": "csomag", "friss": ell["ok"], "azonosito": str(cs.get("commit") or "")[:12],
                       "elteres": [] if ell["ok"] else ["csomag"]})
        cs_info = {"jegyzek": True, "termek_verzio": cs.get("termek_verzio"), "build": cs.get("build"),
                   "commit": cs.get("commit"), "tiszta": cs.get("tiszta"), "epitve": cs.get("epitve"),
                   "ellenorizve": ell["ellenorizve"], "hianyzik": ell["hianyzik"][:20], "modositott": ell["modositott"][:20],
                   "tobblet": ell["tobblet"][:20]}
    ismeretlen = []
    for resz, az in (futo or {}).items():
        if resz not in vart:
            continue
        if az is None:
            ismeretlen.append(resz)
            continue
        reszek.append({'resz': 'futó ' + resz, 'friss': az == vart[resz], 'azonosito': str(az or '')[:12],
                       'elteres': [] if az == vart[resz] else [resz]})
    ki = {"ok": all(r["friss"] for r in reszek), "mag": vart["mag"][:12], "reszek": reszek, "csomag": cs_info}
    if ismeretlen:
        ki["futo_ismeretlen"] = ismeretlen
    return ki


def allapot(root: Path, futo: dict | None = None) -> dict:
    """A lemezen álló buildek (és ha `futo` adott, a futó részek) frissessége. A `futo` None értékű része még nem ismert (a futó
    mag ujjlenyomata a kézfogás után, háttérben számolódik): az a sor kimarad, és a `futo_ismeretlen` felsorolja.
    Termék-csomagban (F9) a befagyasztott jegyzékhez mér (`_csomag_allapot`)."""
    from .gyoker_kereso import termek_gyoker
    if termek_gyoker(root):
        return _csomag_allapot(Path(root), futo)
    vart = jegyzek(root)
    reszek = []
    for resz, ut in (("felulet", "app/dist/epites.json"),
                     ("hej", "Manifold.app/Contents/Resources/epites.json")):
        try:
            epult = json.loads((root / ut).read_text())
            ervenyes = isinstance(epult, dict) and epult.get("verzio") == 1
        except (OSError, ValueError):
            epult, ervenyes = {}, False
        if not isinstance(epult, dict):
            epult = {}
        # Minden rész csak a SAJÁT forrásaihoz mérődik: a felület az `app/` forrásaihoz, a héj a `shell/` forrásaihoz. A mag
        # (core) változása nem teszi elavulttá a felület- vagy a héj-buildet; a mag elavultságát a futó core jelzi (`futo`).
        elteres = [resz] if epult.get(resz) != vart[resz] else []
        reszek.append({"resz": resz, "friss": ervenyes and not elteres,
                       "azonosito": str(epult.get(resz, ""))[:12], "elteres": elteres,
                       **(_hej_valtozat(epult) if resz == "hej" else {})})
    ismeretlen = []
    for resz, az in (futo or {}).items():
        if resz not in vart:
            continue
        if az is None:
            ismeretlen.append(resz)
            continue
        reszek.append({'resz': 'futó ' + resz, 'friss': az == vart[resz], 'azonosito': str(az or '')[:12],
                       'elteres': [] if az == vart[resz] else [resz]})
    ki = {"ok": all(r["friss"] for r in reszek), "mag": vart["mag"][:12], "reszek": reszek}
    if ismeretlen:
        ki["futo_ismeretlen"] = ismeretlen      # pl. ["mag"]: a futó core ujjlenyomata még számolódik
    return ki


def utvonalak(r):
    def epites(k):
        futo = None
        if k.q.get('futo') == '1':
            # a futó mag ujjlenyomata a kézfogás után, háttérszálon készül (`App.epites_mag`): addig None (= még nem ismert)
            futo = {'mag': getattr(k.app, 'epites_mag', None), 'felulet': k.q.get('felulet', ''), 'hej': k.q.get('hej', '')}
        return allapot(k.app.cfg.root, futo)
    r.get("/api/rendszer/epites", epites)


def fo(argv: list[str] | None = None) -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Generate Manifold source fingerprints and native shell build metadata.")
    parser.add_argument("--swift", action="store_true", help="Generate the native JavaScript build record as Swift source.")
    parser.add_argument("--hej-valtozat", choices=HEJ_VALTOZATOK, help="Native shell build variant (explicit, independent of source hashes).")
    args = parser.parse_args(argv)
    j = json.dumps(jegyzek(Path(__file__).resolve().parent.parent, hej_valtozat=args.hej_valtozat))
    print('enum EpitesAzonosito { static let js = ' + json.dumps('window.__manifoldHejEpites = ' + j) + ' }'
          if args.swift else j)


if __name__ == "__main__":
    fo()
