"""Relokálható venv a csomagba (F9): a bundle bárhová másolható, az értelmező útja sehol nincs beégetve.

Elrendezés a csomagban: `runtime/python` (python-build-standalone, magától relokálható) és `runtime/venv`, ahol
  - `bin/python*` RELATÍV symlink a `../../python/bin/python3.X`-re;
  - a `pyvenv.cfg` `home` kulcsa relatív (`../python/bin`; a CPython 3.14 a symlink feloldásával találja meg az alapot, a
    relatív `home` a `pyvenv.cfg` mappájához képest érvényes), és `relocatable = true`;
  - a `bin/` szkriptjeinek shebangje a `/bin/sh`-trambulin, amely a szkript saját mappájának `python`-ját hívja (ugyanaz az
    alak, amelyet a `uv venv --relocatable` ír);
  - az `activate*` szkriptek (abszolút `VIRTUAL_ENV`-et hordoznak, a termék nem használja őket) kimaradnak;
  - a fejlesztői bájtkód (`__pycache__`, abszolút forrásutakkal) kimarad; a `direct_url.json` `file://` útja is.

Két építési mód: `epit` (a `uv` offline, a rögzített `requirements.lock` hash-ei szerint a helyi wheelhouse-ból — a kiadási út)
és `masol` (egy meglévő, ugyanarra a Pythonra épült venv másolata — fejlesztői/teszt-út). Mindkettő után `relokal` + `ellenoriz`.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from csomag_kozos import CsomagHiba, Futtato, bajtkod_torles, futtat, klonoz

TRAMBULIN = "#!/bin/sh\n'''exec' \"$(dirname -- \"$(realpath -- \"$0\")\")\"/'python' \"$0\" \"$@\"\n' '''\n"
_ABSZOLUT_TRAMBULIN = re.compile(r"\A#!/bin/sh\n'''exec' '(/[^']*)/python[0-9.]*' \"\$0\" \"\$@\"\n' '''\n")


def python_verzio_nev(python_mappa: Path) -> str:
    """A `python3.X` futtatható neve a hordozható Python `bin/`-jében (pl. `python3.14`)."""
    jeloltek = sorted(p.name for p in (python_mappa / "bin").glob("python3.*")
                      if re.fullmatch(r"python3\.\d+", p.name) and os.access(p, os.X_OK))
    if not jeloltek:
        raise CsomagHiba("python_hianyzik", f"nincs python3.X a hordozható Pythonban: {python_mappa / 'bin'}")
    return jeloltek[-1]


def venv_epit(*, uv: Path, python_mappa: Path, cel: Path, wheels: Path, lock: Path, cache: Path,
              futtato: Futtato = futtat) -> None:
    """A kiadási út: `uv venv --relocatable` + `uv pip install` hálózat nélkül, csak a helyi wheelhouse-ból, hash-ellenőrzéssel."""
    for ut, mit in ((uv, "uv"), (wheels, "wheelhouse (runtime/wheels)"), (lock, "requirements.lock")):
        if not ut.exists():
            raise CsomagHiba("venv_forras_hianyzik", f"hiányzik a venv építéséhez: {mit} ({ut}); "
                                                     "futtasd: bin/mos runtime fetch (D3: egyszeri, jóváhagyott letöltés)")
    env = {**os.environ, "UV_CACHE_DIR": str(cache), "UV_PYTHON_DOWNLOADS": "never", "UV_NO_CONFIG": "1",
           "UV_LINK_MODE": "clone"}
    for k in ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME"):
        env.pop(k, None)
    futtato([uv, "venv", "--relocatable", "--offline", "--no-config", "--python", python_mappa / "bin" / "python3", cel], env=env)
    futtato([uv, "pip", "install", "--python", cel / "bin" / "python", "--offline", "--no-index", "--find-links", wheels,
             "--require-hashes", "--no-config", "-r", lock], env=env)


def venv_masol(forras: Path, cel: Path) -> None:
    """Fejlesztői/teszt-út: egy meglévő venv másolata (APFS-klón); a relokáció ezután teszi hordozhatóvá."""
    if not (forras / "pyvenv.cfg").is_file():
        raise CsomagHiba("venv_forras_hianyzik", f"nem venv (nincs pyvenv.cfg): {forras}")
    klonoz(forras, cel)


def relokal(venv: Path, python_mappa: Path) -> list[str]:
    """A venv átírása relokálhatóvá (lásd a modul leírását) → a változtatások listája."""
    valtozas: list[str] = []
    nev = python_verzio_nev(python_mappa)
    binm = venv / "bin"
    cel = os.path.relpath(python_mappa / "bin" / nev, binm)
    for n in ("python", "python3", nev):
        p = binm / n
        if p.is_symlink() or p.exists():
            p.unlink()
        p.symlink_to(cel)
        valtozas.append(f"bin/{n} -> {cel}")
    # pyvenv.cfg: relatív home, relocatable
    cfg = venv / "pyvenv.cfg"
    sorok = []
    for s in cfg.read_text(encoding="utf-8").splitlines():
        k = s.split("=", 1)[0].strip()
        if k == "home":
            s = f"home = {os.path.relpath(python_mappa / 'bin', venv)}"
        elif k in ("relocatable", "base-executable", "executable", "command", "prompt"):
            continue                                # az abszolút utat hordozó (vagy újraírt) kulcsok
        sorok.append(s)
    sorok.append("relocatable = true")
    cfg.write_text("\n".join(sorok) + "\n", encoding="utf-8")
    valtozas.append("pyvenv.cfg: relatív home, relocatable = true")
    # bin/: activate* ki, shebangek a trambulinra
    for p in sorted(binm.iterdir()):
        if p.name.startswith(("activate", "deactivate")) or p.name == "activate_this.py":
            p.unlink()
            valtozas.append(f"bin/{p.name}: törölve (abszolút VIRTUAL_ENV)")
            continue
        if p.is_symlink() or not p.is_file():
            continue
        with open(p, "rb") as fh:
            fej = fh.read(4096)
        if not fej.startswith(b"#!"):
            continue
        szoveg = p.read_text(encoding="utf-8", errors="surrogateescape")
        elso, _, maradek = szoveg.partition("\n")
        m = _ABSZOLUT_TRAMBULIN.match(szoveg)
        if m:
            p.write_text(TRAMBULIN + szoveg[m.end():], encoding="utf-8", errors="surrogateescape")
            valtozas.append(f"bin/{p.name}: trambulin (relatív)")
        elif re.match(r"#![ \t]*/.*python[0-9.]*[ \t]*$", elso):
            p.write_text(TRAMBULIN + maradek, encoding="utf-8", errors="surrogateescape")
            valtozas.append(f"bin/{p.name}: shebang → trambulin")
    # bájtkód és a telepítési forrás abszolút útja
    if bajtkod_torles(venv):
        valtozas.append("__pycache__: törölve")
    for d in venv.glob("lib/python3.*/site-packages/*.dist-info/direct_url.json"):
        if '"file://' in d.read_text(encoding="utf-8", errors="replace"):
            d.unlink()
            valtozas.append(f"{d.parent.name}/direct_url.json: törölve (helyi út)")
    return valtozas


def ellenoriz(venv: Path, python_mappa: Path | None = None) -> list[str]:
    """A relokálhatóság ellenőrzése → a hibák listája (üres: rendben). Abszolút symlink, abszolút `home`, abszolút shebang,
    szerkeszthető (`__editable__`) telepítés és abszolút utat hordozó `.pth` hiba."""
    hibak: list[str] = []
    binm = venv / "bin"
    for n in ("python", "python3"):
        p = binm / n
        if not p.is_symlink():
            hibak.append(f"bin/{n}: nem symlink")
        elif os.path.isabs(os.readlink(p)):
            hibak.append(f"bin/{n}: abszolút symlink ({os.readlink(p)})")
        elif not p.exists():
            hibak.append(f"bin/{n}: törött symlink ({os.readlink(p)})")
        elif python_mappa is not None and not Path(os.path.realpath(p)).is_relative_to(os.path.realpath(python_mappa)):
            hibak.append(f"bin/{n}: nem a csomag Pythonjára mutat ({os.path.realpath(p)})")
    try:
        home = next((s.split("=", 1)[1].strip() for s in (venv / "pyvenv.cfg").read_text(encoding="utf-8").splitlines()
                     if s.split("=", 1)[0].strip() == "home"), None)
    except OSError:
        home = None
        hibak.append("nincs pyvenv.cfg")
    if home is not None and os.path.isabs(home):
        hibak.append(f"pyvenv.cfg: abszolút home ({home})")
    for p in sorted(binm.iterdir()) if binm.is_dir() else ():
        if p.is_symlink() or not p.is_file():
            continue
        with open(p, "rb") as fh:
            fej = fh.read(512)
        if fej.startswith(b"#!") and (re.match(rb"#![ \t]*/[^\n]*python", fej) or b"'''exec' '/" in fej):
            hibak.append(f"bin/{p.name}: abszolút shebang")
    for pth in venv.glob("lib/python3.*/site-packages/*.pth"):
        t = pth.read_text(encoding="utf-8", errors="replace")
        if pth.name.startswith("__editable__"):
            hibak.append(f"{pth.name}: szerkeszthető (fejlesztői) telepítés")
        elif any(s.strip().startswith("/") for s in t.splitlines()):
            hibak.append(f"{pth.name}: abszolút út")
    return hibak


def futtathato_proba(venv: Path, futtato: Futtato = futtat) -> str:
    """A venv Pythonja elindul-e, és a saját prefixét látja-e (a relokáció füstpróbája) → `sys.prefix`."""
    p = futtato([venv / "bin" / "python", "-I", "-B", "-c", "import sys; print(sys.prefix)"],
                env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"})
    prefix = p.stdout.strip()
    if os.path.realpath(prefix) != os.path.realpath(venv):
        raise CsomagHiba("venv_relokacio", f"a venv Pythonja más prefixet lát: {prefix} (várt: {venv})")
    return prefix


def tisztit(venv: Path) -> None:
    """A csomagolás alatti venv eltávolítása (csak a build saját staging-mappájában hívható)."""
    shutil.rmtree(venv, ignore_errors=True)
