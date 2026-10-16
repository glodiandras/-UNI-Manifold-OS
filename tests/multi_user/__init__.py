"""Több munkatér egy telepítésen (F3-DESIGN §4): termék-alakú álgyökér (`alg_bundle`), ál-HOME (az `{install}` ez alatt), és
munkaterenként egy álvault `.obsidian` + `.manifold/workspace.toml`-lal. A `test_zarak_telepites` is ezeket használja."""
import os
import select
import time
import uuid
from pathlib import Path

from tests.helpers import REPO, alg_bundle, env


def termek_telepites(tmp: str) -> tuple[Path, Path]:
    """→ (a termék-álgyökér, az ál-HOME). Az `{install}` a `<home>/Library/Application Support/Manifold`."""
    root = alg_bundle(tmp)
    return root, Path(tmp) / "home"


def install(home: Path) -> Path:
    return home / "Library" / "Application Support" / "Manifold"


def munkater(tmp: str, nev: str, *, id: str | None = None, olvaso_min: int = 1) -> tuple[Path, str]:
    """Egy kész munkatér (mint a `workspace letrehoz` commit-pontja után): `.obsidian/`, `.manifold/workspace.toml`."""
    v = Path(tmp) / nev
    (v / ".obsidian").mkdir(parents=True)
    (v / ".manifold").mkdir()
    id = id or uuid.uuid4().hex
    (v / ".manifold" / "workspace.toml").write_text(
        f'[workspace]\nid = "{id}"\nformatum = 1\nolvaso_min = {olvaso_min}\nnev = "{nev}"\n', encoding="utf-8")
    return v, id


def termek_cfg(root: Path, home: Path, vault: Path, **extra):
    """A termék konfigurációja egy vaulthoz (a telepítési réteg nélkül: `MOS_SETTINGS=`)."""
    from core import config
    return config.load({"MOS_ROOT": str(root), "HOME": str(home), "MOS_VAULT": str(vault), "MOS_SETTINGS": "", **extra})


def termek_env(root: Path, home: Path, vault: Path, **extra) -> dict:
    """Hermetikus gyermek-környezet egy termék-core-hoz: a mentés a termék alapértéke (`{backup_gyoker}/{workspace_id}`)."""
    e = env(MOS_ROOT=str(root), HOME=str(home), MOS_VAULT=str(vault), PYTHONPATH=str(REPO), **extra)
    e.pop("MOS_BACKUP", None)
    return e


def elso_sor(p, hatarido_mp: float = 60) -> bytes:
    """A gyermek első stdout-sora határidővel (`select`): egy elakadó core ne akassza meg a tesztet."""
    fd = p.stdout.fileno()
    buf = b""
    vege = time.monotonic() + hatarido_mp
    while b"\n" not in buf:
        marad = vege - time.monotonic()
        if marad <= 0:
            break
        r, _, _ = select.select([fd], [], [], marad)
        if not r:
            break
        darab = os.read(fd, 4096)
        if not darab:
            break
        buf += darab
    return buf.split(b"\n", 1)[0]
