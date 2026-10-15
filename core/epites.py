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
import sys
from pathlib import Path

RESZEK = {
    "felulet": ("app/src", "app/index.html", "app/package.json", "app/package-lock.json", "app/vite.config.ts",
                "app/svelte.config.js", "app/tsconfig.json"),
    "mag": ("core", "modulok"),
    "hej": ("shell/Sources", "shell/Info.plist", "shell/build.sh"),
}

# A tartalék bejárás (git nélkül) ezeket a mappákat kihagyja: nem forrás, és lehet óriási (a staging videói)
KIHAGY_MAPPAK = frozenset({"staging", "archive", "logs", "__pycache__", ".pytest_cache", "node_modules", "dist"})
KIHAGY_KITERJESZTES = (".pyc", ".pyo")
FAJL_MAX_BAJT = 64 << 20        # a tartalék bejárásban e fölött a tartalom nem olvasódik, csak a méret számít
GIT_IDOKORLAT_MP = 30


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


def jegyzek(root: Path) -> dict:
    return {"verzio": 1, **{r: ujjlenyomat(root, r) for r in RESZEK}}


def allapot(root: Path, futo: dict | None = None) -> dict:
    """A lemezen álló buildek (és ha `futo` adott, a futó részek) frissessége. A `futo` None értékű része még nem ismert (a futó
    mag ujjlenyomata a kézfogás után, háttérben számolódik): az a sor kimarad, és a `futo_ismeretlen` felsorolja."""
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
                       "azonosito": str(epult.get(resz, ""))[:12], "elteres": elteres})
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


if __name__ == "__main__":
    j = json.dumps(jegyzek(Path(__file__).resolve().parent.parent))
    print('enum EpitesAzonosito { static let js = ' + json.dumps('window.__manifoldHejEpites = ' + j) + ' }'
          if '--swift' in sys.argv else j)
