"""Közös segédek: ideiglenes álgyökér (álvault, ál-var/), a valódi vault és var/ nélkül."""
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

from tests import API_TITOK  # noqa: F401  (a tesztek innen is importálhatják)

REPO = Path(__file__).resolve().parent.parent


def alg_gyoker(tmp: str, mos_szkript: str | None = None) -> Path:
    """Álgyökér: `{tmp}/work/os` a gyökér, `{tmp}/work/Manifold` az álvault."""
    work = Path(tmp) / "work"
    root = work / "os"
    (root / "bin").mkdir(parents=True)
    (root / "config").mkdir()
    (work / "Manifold").mkdir()
    for d in ("var/state", "var/tmp", "var/cache", "runtime"):
        (root / d).mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / "config" / "os.toml", root / "config" / "os.toml")
    shutil.copy(REPO / "config" / "vault-sema.json", root / "config" / "vault-sema.json")     # C11b: a vault-séma
    mos = root / "bin" / "mos"
    mos.write_text(mos_szkript or "#!/bin/sh\nexit 0\n")
    mos.chmod(mos.stat().st_mode | stat.S_IXUSR)
    return root


def core_indito_szkript() -> str:
    """Álgyökér `bin/mos`-a, amely a repo core-ját indítja (a tesztfolyamat Pythonjával)."""
    return f"#!/bin/sh\nPYTHONPATH='{REPO}' exec '{sys.executable}' -B -m core \"$@\"\n"


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


def legacy_eszkozok(cfg=None) -> Path | None:
    """A legacy `modulok/eszkozok` mappája — csak olvasható referencia, kizárólag a C06 gráf-paritásának
    (a `mfd.obsidian_graf` futtatása `-B`-vel, bytecode-írás nélkül). A `{work}` alól számolva, a
    `MOS_LEGACY` (a legacy gyökere) felülírja. A config és a core nem hivatkozhat a legacyre (doctor)."""
    if os.environ.get("MOS_LEGACY"):
        gyoker = Path(os.environ["MOS_LEGACY"])
    else:
        from core import config
        gyoker = (cfg or config.load()).path("work") / "Manifold-OS legacy" / "Legacy"
    p = gyoker / "modulok" / "eszkozok"
    return p if (p / "mfd.py").is_file() else None


LEGACY_GRAF = """
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])
import mfd
from core.index.feloldas import graf_kanonikus
sys.stdout.buffer.write(graf_kanonikus(mfd.obsidian_graf(sys.argv[3])))
"""


def legacy_graf(eszkozok: Path, vault: Path) -> bytes:
    """A legacy `obsidian_graf` a `vault`-on, alfolyamatban (`-B`), a 2.0 kanonikus alakjában."""
    import subprocess
    p = subprocess.run([sys.executable, "-B", "-c", LEGACY_GRAF, str(eszkozok), str(REPO), str(vault)],
                       capture_output=True, env={**env(), "PYTHONDONTWRITEBYTECODE": "1"}, timeout=300)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[-2000:])
    return p.stdout
