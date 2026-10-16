"""A csomagoló (F9) közös segédei: utak, parancsfuttató, Mach-O felismerés, fájlmásolás (APFS-klón), kizárási minták.

FONTOS: a `packaging/` mappában SZÁNDÉKOSAN nincs `__init__.py`. A repo gyökere a `PYTHONPATH`-on van (`bin/mos`), és egy
`packaging` nevű csomag elfedné a PyPI `packaging` könyvtárát (a transformers, a huggingface_hub és a pip is importálja).
Kezdőfájl nélkül a mappa csak névtér-rész, amelyet a site-packages valódi csomagja megelőz. A modulok ezért szkriptként
futnak (`python packaging/build_app.py …`), és egymást a saját mappájukból importálják (`csomag_kozos.utvonal_beallit()`).

Semmi nincs beégetve: a repo gyökere e fájl helyéből, minden más paraméterből vagy a rétegzett konfigurációból jön.
"""
from __future__ import annotations

import fnmatch
import hashlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

CSOMAG_MAPPA = Path(__file__).resolve().parent
REPO = CSOMAG_MAPPA.parent
APP_NEV = "Manifold.app"
KOD_ALUT = Path("Contents") / "Resources" / "manifold"      # a kódfa a csomagon belül (core/config.py termék-elrendezése)


def utvonal_beallit() -> None:
    """A repo gyökere (a `core` importjához) és a `packaging/` mappa (a testvérmodulokhoz) a `sys.path`-on."""
    for p in (str(REPO), str(CSOMAG_MAPPA)):
        if p not in sys.path:
            sys.path.insert(0, p)


class CsomagHiba(Exception):
    """A csomagolás érthető, javítható hibája: `kod` (gépi) + üzenet (mit tegyen a fejlesztő)."""

    def __init__(self, kod: str, uzenet: str):
        super().__init__(uzenet)
        self.kod = kod


# ------------------------------------------------------------------ parancsok

Futtato = Callable[..., subprocess.CompletedProcess]


def futtat(cmd: Sequence[str], *, cwd: Path | None = None, env: dict | None = None, check: bool = True,
           timeout: float | None = None, bemenet: bytes | None = None) -> subprocess.CompletedProcess:
    """Egy külső parancs (szöveges kimenettel). Hibánál `CsomagHiba(kod="parancs")` a parancs és a stderr végével."""
    try:
        p = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, capture_output=True, timeout=timeout, input=bemenet)
    except FileNotFoundError as e:
        raise CsomagHiba("parancs_hianyzik", f"a parancs nem található: {cmd[0]} ({e})") from e
    except subprocess.TimeoutExpired as e:
        raise CsomagHiba("parancs_idotullepes", f"időtúllépés: {' '.join(map(str, cmd))}") from e
    p.stdout = p.stdout.decode("utf-8", "replace")
    p.stderr = p.stderr.decode("utf-8", "replace")
    if check and p.returncode != 0:
        raise CsomagHiba("parancs", f"a parancs hibával állt le ({p.returncode}): {' '.join(map(str, cmd))}\n"
                                    f"{p.stderr.strip()[-2000:]}")
    return p


def van_parancs(nev: str) -> bool:
    return shutil.which(nev) is not None


# ------------------------------------------------------------------ fájlok

def sha256(p: Path) -> str:
    with open(p, "rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


_MACHO = {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xfe\xed\xfa\xce"}
_FAT = {b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"\xca\xfe\xba\xbf"}


def macho(p: Path) -> bool:
    """Mach-O (vékony vagy fat) bináris-e (a varázsszám alapján; a Java `.class` CAFEBABE-jét az architektúraszám zárja ki)."""
    try:
        if p.is_symlink() or not p.is_file():
            return False
        with open(p, "rb") as fh:
            fej = fh.read(8)
    except OSError:
        return False
    if fej[:4] in _MACHO:
        return True
    if fej[:4] in _FAT and len(fej) == 8:
        n = int.from_bytes(fej[4:8], "big")
        return 0 < n < 20
    return False


def klonoz(forras: Path, cel: Path) -> None:
    """Mappa vagy fájl másolása a jogokkal és az időbélyegekkel, a symlinkeket NEM követve. APFS-en klón (`cp -c`: azonnali,
    helyet nem foglal), máshol közönséges másolás."""
    cel.parent.mkdir(parents=True, exist_ok=True)
    if cel.exists() or cel.is_symlink():
        raise CsomagHiba("cel_letezik", f"a cél már létezik: {cel}")
    for kapcsolok in (["-c", "-pPR"], ["-pPR"]):
        p = subprocess.run(["cp", *kapcsolok, str(forras), str(cel)], capture_output=True)
        if p.returncode == 0:
            return
        if cel.exists():
            shutil.rmtree(cel) if cel.is_dir() and not cel.is_symlink() else cel.unlink()
    raise CsomagHiba("masolas", f"a másolás sikertelen: {forras} → {cel}: {p.stderr.decode('utf-8', 'replace').strip()}")


def bajtkod_torles(gyoker: Path) -> int:
    """A `__pycache__` mappák eltávolítása a (csomagolás alatti, saját) fából: a fejlesztői futások bájtkódja abszolút utakat
    hordozhat. Csak a build saját másolatán fut."""
    n = 0
    for dp, almappak, _ in os.walk(gyoker):
        for a in list(almappak):
            if a == "__pycache__":
                shutil.rmtree(Path(dp, a))
                almappak.remove(a)
                n += 1
    return n


# ------------------------------------------------------------------ mi kerül a csomagba

# A `.gitattributes` `export-ignore` mintái (a kiadásból kizárt belső anyag) — egy forrás: a csomagoló ezeket is kizárja.
def export_ignore_mintak(repo: Path = REPO) -> list[str]:
    ki = []
    try:
        sorok = (repo / ".gitattributes").read_text(encoding="utf-8").splitlines()
    except OSError:
        return ki
    for s in sorok:
        s = s.strip()
        if not s or s.startswith("#"):
            continue
        reszek = s.split()
        if "export-ignore" in reszek[1:]:
            ki.append(reszek[0])
    return ki


# A kódfa részei, amelyek a csomagba kerülnek (a forrás-checkout gyökeréhez képest)
KOD_RESZEK = ("bin/mos", "core", "modulok", "config", "docs/user")
# A csomagoló saját kizárásai (fnmatch a gyökér-relatív, `/`-os útra): fejlesztői és személyes anyag sosem kerül be
KIZART_MINTAK = (
    "*/__pycache__/*", "*.pyc", "*.pyo", "*/.DS_Store", ".DS_Store", "*/._*",
    "config/presets/*", "config/*.local.toml", "config/settings.toml",
    "modulok/*/tests/*", "modulok/*/test_*.py", "modulok/ytdlp/staging/*", "modulok/ytdlp/archive/*",
    "modulok/ytdlp/logs/*", "modulok/ytdlp/.venv*", "*/.pytest_cache/*",
)


def kizart(rel: str, mintak: Sequence[str]) -> bool:
    """A gyökér-relatív út kizárt-e: bármely minta illik rá, vagy (a `dir/**` alakú mintánál) a mappa alatt van; rejtett
    fájl vagy mappa (`.` kezdetű szegmens) sosem kerül be."""
    if any(sz.startswith(".") for sz in rel.split("/")):
        return True
    for m in mintak:
        if m.endswith("/**"):
            alap = m[:-3]
            if rel == alap or rel.startswith(alap + "/"):
                return True
        elif fnmatch.fnmatchcase(rel, m):
            return True
    return False


def forras_fajlok(repo: Path, reszek: Sequence[str] = KOD_RESZEK) -> list[str]:
    """A csomagolandó forrásfájlok: a git által látott (követett + nem kizárt új) fájlok a részek alatt; git nélkül bejárás. A
    `.gitignore`-olt anyag (videók, staging, gyorsítótár) így eleve kimarad."""
    utvonal_beallit()
    from core.epites import _bejart_fajlok, _git_fajlok
    fajlok = _git_fajlok(repo, tuple(reszek))
    if fajlok is None:
        fajlok = _bejart_fajlok(repo, tuple(reszek))
    mintak = list(KIZART_MINTAK) + export_ignore_mintak(repo)
    return [f for f in fajlok if (repo / f).is_file() and not kizart(f, mintak)]


@dataclass
class Naplo:
    """Egyszerű lépésnapló (a CLI kiírja; a tesztek gyűjtik)."""
    sorok: list[str]

    def __call__(self, s: str) -> None:
        self.sorok.append(s)
        print(s, flush=True)
