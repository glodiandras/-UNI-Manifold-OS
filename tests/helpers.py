"""Közös segédek: ideiglenes álgyökér (álvault, ál-var/), a valódi vault és var/ nélkül."""
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

from tests import API_TITOK  # noqa: F401  (a tesztek innen is importálhatják)

REPO = Path(__file__).resolve().parent.parent


def _konfig_masol(root: Path) -> None:
    """A szállított konfiguráció az álgyökérbe: `os.toml`, a sémafájlok (`config/*.json`) és a presetek."""
    (root / "config").mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / "config" / "os.toml", root / "config" / "os.toml")
    shutil.copy(REPO / "config" / "models.toml", root / "config" / "models.toml")    # F6: a modell-manifeszt
    for f in (REPO / "config").glob("*.json"):                                # C11b: a vault-séma (és a semleges alap)
        shutil.copy(f, root / "config" / f.name)
    if (REPO / "config" / "presets").is_dir():
        shutil.copytree(REPO / "config" / "presets", root / "config" / "presets", dirs_exist_ok=True)


def alg_gyoker(tmp: str, mos_szkript: str | None = None, *, preset: str | None = "v2-kompat", vault: bool = True) -> Path:
    """Álgyökér: `{tmp}/work/os` a gyökér, `{tmp}/work/Manifold` az álvault (hordozható elrendezés, F3-DESIGN §7.1).

    A vaultot (a `{work}/Manifold`-ot) és a presetet az ál-telepítési réteg (`var/settings.toml`) adja, mint egy
    `bin/mos portable init` után: alapból a `v2-kompat` preset (a fejlesztő v2-konvenciói), így a tesztek a v2-értékeket
    látják akkor is, ha az `os.toml` semleges. `preset=None`: preset nélkül; `vault=False`: nincs megadott vault."""
    work = Path(tmp) / "work"
    root = work / "os"
    (root / "bin").mkdir(parents=True)
    (work / "Manifold").mkdir()
    for d in ("var/state", "var/tmp", "var/cache", "runtime"):
        (root / d).mkdir(parents=True, exist_ok=True)
    _konfig_masol(root)
    sorok = []
    if vault:
        sorok += ["[utak]", 'vault = "{work}/Manifold"', ""]
    if preset:
        sorok += ["[telepites]", f"presetek = [{json.dumps(preset)}]", ""]
    if sorok:
        (root / "var" / "settings.toml").write_text("\n".join(sorok), encoding="utf-8")
    mos = root / "bin" / "mos"
    mos.write_text(mos_szkript or "#!/bin/sh\nexit 0\n")
    mos.chmod(mos.stat().st_mode | stat.S_IXUSR)
    return root


def alg_bundle(tmp: str) -> Path:
    """Termék-alakú álgyökér: `{tmp}/X.app/Contents/Resources/manifold` (a `config/` szállított tartalmával, `bin/mos`
    nélkül), az ál-HOME a `{tmp}/home` (a `{install}` ez alatt: `Library/Application Support/Manifold`). Nincs `var/`."""
    root = Path(tmp) / "X.app" / "Contents" / "Resources" / "manifold"
    root.mkdir(parents=True)
    (Path(tmp) / "X.app" / "Contents" / "MacOS").mkdir()
    _konfig_masol(root)
    (Path(tmp) / "home").mkdir(exist_ok=True)
    return root


def core_indito_szkript() -> str:
    """Álgyökér `bin/mos`-a, amely a repo core-ját indítja (a tesztfolyamat Pythonjával)."""
    return f"#!/bin/sh\nPYTHONPATH='{REPO}' exec '{sys.executable}' -B -m core \"$@\"\n"


def vault_sema() -> dict:
    """A `v2-kompat` preset sémája (`config/presets/v2-kompat.schema.json`; F3-ban ez a régi `config/vault-sema.json`): a tesztek a
    kivételútvonalakat, a sémán kívüli fájlokat és a kivételosztályokat innen veszik, nem beégetett mappanevekből."""
    return json.loads((REPO / "config" / "presets" / "v2-kompat.schema.json").read_text(encoding="utf-8"))


def tmpdir():
    return tempfile.TemporaryDirectory(prefix="mos-teszt-")


def env(*, home: bool = True, **extra):
    """Hermetikus gyermek-környezet: a hívó MOS_/UV_/PIP_/XDG_/MANIFOLD_ változói nélkül, ÁL-HOME-mal (T011: a `{home}` —
    a belső lemezes mentés, a ~/.cache — a valódi HOME-hoz nem érhet). Álgyökér (`MOS_ROOT=…/work/os`) mellett a HOME a
    teszt-mappa `home/`-ja (mint az `alg_core`-é), különben egy közös üres mappa a `{tmp}` alatt. `home=False`: a valódi
    HOME marad (a `Manifold.app` WebKitje és engedélyei valódi HOME-ot kérnek); kifejezett `HOME=` mindig nyer.
    **A belső lemezes mentés útja (`MOS_BACKUP`) valódi HOME mellett is álgyökér-lokális** (C29.6): a core leállásakor az
    állapotfájlok másolata (`mos-allapot-*`) és a bundle-ök a `{backup}`-ra kerülnek, és egy `--selftest`-ben indított core
    a valódi `~/Manifold-backup` rotációját és tartalmát nem érintheti."""
    e = {k: v for k, v in os.environ.items() if not k.startswith(("MOS_", "UV_", "PIP_", "XDG_", "MANIFOLD_"))}
    e["MOS_FEJLESZTO"] = "1"          # a tesztek Developer módban futnak (a teszt-horgok csak így élnek: core/fejleszto.py)
    e["MOS_SETTINGS"] = ""            # a valódi checkout telepítési rétege (a fejlesztő `var/settings.toml`-ja) nem látszik;
    # az álgyökerek a sajátjukat olvassák (az üres érték csak a kódot hordozó checkoutra hat: core/config._settings_ut)
    gyoker = extra.get("MOS_ROOT")
    if home and "HOME" not in extra:   # a kifejezett HOME= nyer: ál-HOME-ot sem hoz létre (a fő checkoutban a
        # `MOS_ROOT` két szülője a `/Volumes`, oda nem írhat)
        h = Path(gyoker).parent.parent / "home" if gyoker else Path(tempfile.gettempdir()) / "mos-teszt-home"
        h.mkdir(parents=True, exist_ok=True)
        e["HOME"] = str(h)
    elif gyoker:
        e["MOS_BACKUP"] = str(Path(gyoker).parent.parent / "home" / "Manifold-backup")
    e.setdefault("MOS_API_TITOK", API_TITOK)       # a gyermek-core is a teszt-titkot használja (a `MOS_*` szűrő kivette)
    e.update(extra)
    return e


def alg_core(tmp: str, **env_extra):
    """Álgyökér álvaulttal (`.obsidian`) és a saját pillanatkép-tárolójával → (config, gyökér, álvault).
    A tároló az ál-`var/vault.git`: a valódi vaulthoz és var/-hoz a teszt nem nyúl."""
    from core import config
    root = alg_gyoker(tmp)
    vault = root.parent / "Manifold"
    (vault / ".obsidian").mkdir()
    cfg = config.load({"MOS_ROOT": str(root), "HOME": str(Path(tmp) / "home"), **env_extra})
    return cfg, root, vault


def ir(vault: Path, rp: str, t, mod: str = "w") -> Path:
    f = vault / rp
    f.parent.mkdir(parents=True, exist_ok=True)
    if mod == "wb":
        f.write_bytes(t)
    else:
        f.write_text(t, encoding="utf-8")
    return f
