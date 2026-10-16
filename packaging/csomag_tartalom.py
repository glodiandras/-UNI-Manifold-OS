"""A csomag tartalmának ellenőrzése (F9): semmi személyes vagy fejlesztői anyag nem kerülhet a kiadott `Manifold.app`-ba.

Három szint:
  1. szerkezet — a `Contents/Resources/manifold` felső szintjén csak a termék részei (bin, core, modulok, config, app/dist,
     docs/user, runtime/{python,venv,ffmpeg,git,node}); fejlesztői mappa (tests, tools, packaging, shell, app/src, var,
     node_modules, docs/plan|dev) nincs;
  2. tiltott utak — a `.gitattributes` `export-ignore` mintái és a csomagoló kizárásai (presetek, `tests/kezi`, privát
     fixture-ök, `var/`), továbbá személyes állapotfájl (`settings.toml`, `workspace.toml`, `.obsidian`, `.manifold`, `*.sqlite`)
     sehol, a runtime alatt sem;
  3. tiltott bájtsorok — a fejlesztői gép útjai (a repo, a `HOME`, a build kimenete, a `runtime` symlink célja, a beállított
     vault) NFC- és NFD-alakban egyetlen fájlban sem fordulhatnak elő (a bináris fájlokban sem).

`python packaging/csomag_tartalom.py <Manifold.app> [--tiltott <szöveg>]… [--max-mb N]` → 0 = tiszta, 1 = hibák.
"""
from __future__ import annotations

import mmap
import os
import sys
import tomllib
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from csomag_kozos import KIZART_MINTAK, KOD_ALUT, REPO, export_ignore_mintak, kizart

FELSO_ENGEDELY = {"bin", "core", "modulok", "config", "app", "docs", "runtime"}
AL_ENGEDELY = {"app": {"dist"}, "docs": {"user"}, "runtime": {"python", "venv", "ffmpeg", "git", "node"}, "bin": {"mos"}}
# Személyes állapot és fejlesztői maradék: a csomag BÁRMELY pontján tilos (a runtime alatt is)
TILTOTT_NEVEK = {"settings.toml", "settings.local.toml", "workspace.toml", "workspaces.json", ".obsidian", ".manifold",
                 ".git", "node_modules", ".pytest_cache", ".venv", "kezi"}
TILTOTT_KITERJESZTES = (".sqlite", ".sqlite-wal", ".sqlite-shm", ".dmg")
# A kódfában (a runtime-on kívül) tilos mappanevek
KOD_TILTOTT_MAPPA = {"tests", "tools", "packaging", "shell", "var", "preset_v2", "presets", "node_modules",
                     "staging", "archive", "logs"}


@dataclass
class Jelentes:
    hibak: list[str] = field(default_factory=list)
    fajlok: int = 0
    bajt: int = 0
    kihagyott_nagy: int = 0

    @property
    def ok(self) -> bool:
        return not self.hibak


def alap_tiltott_szovegek(repo: Path = REPO, *, extra: Iterable[str] = ()) -> list[str]:
    """A fejlesztői gép útjai, amelyek nem szivároghatnak a csomagba: a repo (és a feloldott alakja), a `HOME`, a `runtime`
    symlink célja (pl. egy másik checkout), és a hordozható telepítési réteg vaultja (ha be van állítva)."""
    ki = {str(repo), os.path.realpath(repo), os.path.expanduser("~")}
    rt = repo / "runtime"
    if rt.is_symlink():
        ki.add(os.path.dirname(os.path.realpath(rt)))
    try:
        s = tomllib.loads((repo / "var" / "settings.toml").read_text(encoding="utf-8"))
        v = (s.get("utak") or {}).get("vault")
        if isinstance(v, str) and v.startswith("/"):
            ki.add(os.path.realpath(v))
    except (OSError, ValueError):
        pass
    ki.update(x for x in extra if x)
    # túl rövid (pl. "/") vagy általános szöveg hamis találatot adna
    return sorted(x for x in ki if len(x) >= 8 and x not in ("/Users", "/Volumes", "/private"))


def _valtozatok(szovegek: Sequence[str]) -> list[bytes]:
    ki = set()
    for s in szovegek:
        for forma in ("NFC", "NFD"):
            ki.add(unicodedata.normalize(forma, s).encode("utf-8"))
    return sorted(ki)


def _szerkezet(root: Path, j: Jelentes) -> None:
    if not root.is_dir():
        j.hibak.append(f"hiányzik a kódfa: {root}")
        return
    for p in root.iterdir():
        if p.name not in FELSO_ENGEDELY:
            j.hibak.append(f"nem termék-rész a csomag gyökerében: {p.name}")
    for felso, engedely in AL_ENGEDELY.items():
        d = root / felso
        if d.is_dir():
            for p in d.iterdir():
                if p.name not in engedely:
                    j.hibak.append(f"nem termék-rész: {felso}/{p.name}")
    for kell in ("bin/mos", "config/os.toml", "core/__main__.py", "app/dist/index.html"):
        if not (root / kell).exists():
            j.hibak.append(f"hiányzik: {kell}")


def _utak(app: Path, root: Path, j: Jelentes, mintak: Sequence[str]) -> list[Path]:
    fajlok: list[Path] = []
    for dp, almappak, nevek in os.walk(app):
        d = Path(dp)
        rel_d = d.relative_to(root).as_posix() if d.is_relative_to(root) else None
        kodban = rel_d is not None and not (rel_d == "runtime" or rel_d.startswith("runtime/"))
        for a in list(almappak):
            if a in TILTOTT_NEVEK:
                j.hibak.append(f"tiltott mappa: {(d / a).relative_to(app)}")
            elif kodban and a in KOD_TILTOTT_MAPPA and not (rel_d == "app" and a == "dist"):
                j.hibak.append(f"fejlesztői mappa a kódfában: {(d / a).relative_to(app)}")
        for n in nevek:
            p = d / n
            if n in TILTOTT_NEVEK or n.endswith(TILTOTT_KITERJESZTES):
                j.hibak.append(f"tiltott fájl: {p.relative_to(app)}")
            if kodban:
                rel = p.relative_to(root).as_posix()
                if kizart(rel, mintak) and "__pycache__" not in rel:
                    j.hibak.append(f"kizárt (export-ignore / fejlesztői) fájl: {rel}")
            fajlok.append(p)
        for a in almappak:
            if (d / a).is_symlink():
                fajlok.append(d / a)
    return fajlok


def _bajtok(app: Path, fajlok: list[Path], tiltott: list[bytes], j: Jelentes, max_bajt: int | None) -> None:
    for p in fajlok:
        try:
            if p.is_symlink():
                cel = os.readlink(p).encode()
                if os.path.isabs(cel) and not cel.startswith((b"/usr/", b"/System/", b"/Applications", b"/bin/", b"/dev/")):
                    j.hibak.append(f"abszolút symlink a csomagon kívülre: {p.relative_to(app)} -> {cel.decode(errors='replace')}")
                for t in tiltott:
                    if t in cel:
                        j.hibak.append(f"fejlesztői út symlinkben: {p.relative_to(app)}")
                continue
            meret = p.stat().st_size
            j.fajlok += 1
            j.bajt += meret
            if meret == 0:
                continue
            if max_bajt is not None and meret > max_bajt:
                j.kihagyott_nagy += 1
                continue
            with open(p, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as m:
                for t in tiltott:
                    if m.find(t) != -1:
                        j.hibak.append(f"fejlesztői út ({t.decode(errors='replace')}) a fájlban: {p.relative_to(app)}")
                        break
        except (OSError, ValueError) as e:
            j.hibak.append(f"nem olvasható: {p.relative_to(app)} ({e})")


def ellenoriz(app: Path, *, tiltott_szovegek: Sequence[str] | None = None, repo: Path = REPO,
              max_bajt: int | None = None) -> Jelentes:
    """A teljes ellenőrzés egy kész `Manifold.app`-on. `max_bajt`: e fölötti fájlok bájtkeresése kimarad (gyors mód)."""
    app = Path(app)
    root = app / KOD_ALUT
    j = Jelentes()
    _szerkezet(root, j)
    mintak = list(KIZART_MINTAK) + export_ignore_mintak(repo)
    fajlok = _utak(app, root, j, mintak)
    tiltott = _valtozatok(alap_tiltott_szovegek(repo) if tiltott_szovegek is None else list(tiltott_szovegek))
    _bajtok(app, fajlok, tiltott, j, max_bajt)
    return j


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("használat: csomag_tartalom.py <Manifold.app> [--tiltott <szöveg>]… [--max-mb N]", file=sys.stderr)
        raise SystemExit(2)
    extra, max_mb = [], None
    i = 1
    while i < len(args):
        if args[i] == "--tiltott":
            extra.append(args[i + 1])
            i += 2
        elif args[i] == "--max-mb":
            max_mb = int(args[i + 1])
            i += 2
        else:
            raise SystemExit(f"ismeretlen kapcsoló: {args[i]}")
    jel = ellenoriz(Path(args[0]), tiltott_szovegek=alap_tiltott_szovegek(extra=extra),
                    max_bajt=max_mb * 2**20 if max_mb else None)
    for h in jel.hibak[:200]:
        print("HIBA:", h)
    print(f"{jel.fajlok} fájl, {jel.bajt / 2**20:.0f} MB átnézve; hibák: {len(jel.hibak)}"
          + (f"; {jel.kihagyott_nagy} nagy fájl bájtkeresése kihagyva" if jel.kihagyott_nagy else ""))
    raise SystemExit(0 if jel.ok else 1)
