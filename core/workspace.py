"""Munkaterek (F3-DESIGN §3): egy Markdown-mappa (vault) Manifold-munkatérré tétele, megnyitása, eltávolítása, és a gép
regisztere (`{install}/workspaces.json`).

A lemezen (§3.1): `<vault>/.obsidian/` (ha hiányzott, üresen jön létre, mint az Obsidianban; utána nem írunk bele),
`<vault>/.manifold/workspace.toml` (a W réteg; a létrehozás UTOLSÓ lépése, a véglegesítési pont), `.gitignore` (`var/`),
`README.txt`, és a `{var}` (`.manifold/var/`; szinkronizált mappában `{install}/workspaces/<id>/var`). A `.manifold` minden
vault-bejárónak láthatatlan (I6, `core/rejtett.py`), a pillanatkép kizárja (`[pillanat.vault] kizar`).

A létrehozás minden lépése idempotens (§3.3): a félbemaradt létrehozást a `felmer` `reszleges`-nek jelzi, a `letrehoz` folytatja
(ugyanazzal az azonosítóval, a `letrehozas.json` jelölőből). A `.manifold` törlése bájtra azonos Obsidian-vaultot hagy (I7).

A regiszter csak index (a legutóbbiak listája és az állapot helye): az egyetlen író a Python (`tartos.atomi_ir` a
`{install_run}/workspaces.lock` alatt), a Swift-héj csak olvassa. Az `elfelejt` soha nem töröl fájlt.

CLI: `python -m core.workspace felmer|letrehoz|lista|elfelejt|eltavolit <vault> [--json] [--igen]` (alap: `felmer`)."""
from __future__ import annotations

import contextlib
import ctypes
import errno
import fcntl
import json
import os
import plistlib
import re
import secrets
import shutil
import subprocess
import sys
import time
import tomllib
import unicodedata
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from . import config, frame, rejtett, snapshot, tartos
from .config import Config, ConfigError

FORMATUM = 1                    # a `workspace.toml` és az állapot formátuma, amelyre ez a kód migrál
FORMATUM_MAX = 1                # a legújabb formátum, amelyet ez a kód olvasni tud (`olvaso_min` > ennél: `workspace_ujabb`)

MAPPA = ".manifold"
OBSIDIAN = ".obsidian"
WS_TOML = "workspace.toml"
LETREHOZAS = "letrehozas.json"  # a félbemaradt létrehozás jelölője (az azonosítóval): a folytatás ugyanazt használja
REGISZTER = "workspaces.json"
REGISZTER_ZAR = "workspaces.lock"
VAR_ALMAPPAK = ("state", "tmp", "run", "runs", "cache", "index")
TM_KIZART = ("tmp", "cache", "index")       # Time Machine-kizárás csak ezekre (újraépíthető / átmeneti)
SPOTLIGHT_JELOLO = ".metadata_never_index"
GITIGNORE = "var/\n"            # a felhasználó saját gitje / Obsidian-Gitje a beállításokat követheti, az állapotot soha
README = "Manifold's settings and data for this folder. Delete it to remove Manifold; notes are untouched.\n"

KEVES_HELY_BAJT = 1 << 30       # ennél kevesebb szabad hely: figyelmeztetés
NAGY_VAULT_DB = 20_000          # ennél több fájl (vagy NAGY_VAULT_BAJT-nál több) — az első pillanatkép időbe telik
NAGY_VAULT_BAJT = 2 << 30
_MNT_LOCAL = 0x00001000
_PC_CASE_SENSITIVE = 11         # macOS `pathconf` név (a Python `os.pathconf_names` nem ismeri)
_ID_SOR = re.compile(r'(?m)^(\s*id\s*=\s*)(["\'])([0-9a-f]{32})\2')

# A munkatértől függő [utak] gyökerek: az ezekből számolt kulcsok egy MÁSIK munkatér rögzített (`MOS_*`) értékét nem vehetik át.
_MUNKATER_GYOKEREK = frozenset({"vault", "workspace", "workspace_id"})


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _most() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------ fájlrendszer-adatok


class _Statfs(ctypes.Structure):
    _fields_ = [("f_bsize", ctypes.c_uint32), ("f_iosize", ctypes.c_int32), ("f_blocks", ctypes.c_uint64),
                ("f_bfree", ctypes.c_uint64), ("f_bavail", ctypes.c_uint64), ("f_files", ctypes.c_uint64),
                ("f_ffree", ctypes.c_uint64), ("f_fsid", ctypes.c_int32 * 2), ("f_owner", ctypes.c_uint32),
                ("f_type", ctypes.c_uint32), ("f_flags", ctypes.c_uint32), ("f_fssubtype", ctypes.c_uint32),
                ("f_fstypename", ctypes.c_char * 16), ("f_mntonname", ctypes.c_char * 1024),
                ("f_mntfromname", ctypes.c_char * 1024), ("f_flags_ext", ctypes.c_uint32), ("f_reserved", ctypes.c_uint32 * 7)]


def _statfs(p: Path) -> tuple[str, bool, str] | None:
    """`statfs(2)` (macOS, 64 bites inode-os alak): → (fájlrendszer-típus, helyi kötet-e (`MNT_LOCAL`), csatolási pont)."""
    if sys.platform != "darwin":
        return None
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        s = _Statfs()
        if libc.statfs(os.fsencode(str(p)), ctypes.byref(s)) != 0:
            return None
        return (s.f_fstypename.decode("utf-8", "replace"), bool(s.f_flags & _MNT_LOCAL),
                os.fsdecode(s.f_mntonname))
    except (OSError, AttributeError, ValueError):
        return None


_KOTET_UUID: dict[str, str | None] = {}


def _kotet_uuid(csatolas: str | None) -> str | None:
    """A kötet UUID-je (`diskutil info -plist`, helyi parancs; folyamatonként egyszer kötetenként). Hiba: None."""
    if not csatolas:
        return None
    if csatolas not in _KOTET_UUID:
        ertek = None
        try:
            p = subprocess.run(["diskutil", "info", "-plist", csatolas], capture_output=True, timeout=10)
            if p.returncode == 0:
                ertek = plistlib.loads(p.stdout).get("VolumeUUID") or None
        except (OSError, subprocess.TimeoutExpired, plistlib.InvalidFileException, ValueError):
            ertek = None
        _KOTET_UUID[csatolas] = ertek
    return _KOTET_UUID[csatolas]


def kanonikus(p: Path) -> str:
    """A mappa kanonikus útja: a lemezen álló kis-nagybetűs alak (`F_GETPATH`, minden symlink feloldva). Hiba: `realpath`."""
    try:
        fd = os.open(str(p), os.O_RDONLY)
    except OSError:
        return os.path.realpath(p)
    try:
        return os.fsdecode(fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024)).split(b"\0", 1)[0])
    except (OSError, AttributeError, ValueError):
        return os.path.realpath(p)
    finally:
        os.close(fd)


def _kis_nagy_erzekeny(p: Path) -> bool:
    try:
        return os.pathconf(str(p), _PC_CASE_SENSITIVE) == 1
    except (OSError, ValueError):
        s = str(p)
        return s.swapcase() != s and not os.path.exists(s.swapcase())


def _szinkron(p: Path, home: Path) -> str | None:
    """Szinkronizált mappa-e: iCloud Drive (`~/Library/Mobile Documents`), `~/Library/CloudStorage`, Dropbox."""
    r = Path(os.path.realpath(p))
    for gyoker, nev in ((home / "Library" / "Mobile Documents", "icloud"), (home / "Library" / "CloudStorage", "cloudstorage")):
        g = Path(os.path.realpath(gyoker))
        if r == g or g in r.parents:
            return nev
    for a in (r, *r.parents):
        if a.name.casefold() == "dropbox" or a.name.casefold().startswith("dropbox (") or (a / ".dropbox").is_file():
            return "dropbox"
    return None


def _alatt(p: Path, gyoker: Path | None) -> bool:
    """A `p` a `gyoker` maga vagy alatta van-e (feloldott utakon, kis-nagybetű-érzéketlenül, és fájlrendszer-azonosság
    szerint a létező ősökön). A nem létező gyökér alatt semmi sincs."""
    if gyoker is None:
        return False
    g = Path(os.path.realpath(gyoker))
    r = Path(os.path.realpath(p))
    gs, rs = str(g).casefold(), str(r).casefold()
    if rs == gs or rs.startswith(gs.rstrip("/") + "/"):
        return True
    if not g.exists():
        return False
    for a in (r, *r.parents):
        try:
            if os.path.samefile(a, g):
                return True
        except OSError:
            continue
    return False


def _eszkoz(p: Path) -> int | None:
    """A legközelebbi létező ős kötete (`st_dev`, a symlinkeket követve); semmi sem létezik: None."""
    q = Path(p)
    while True:
        try:
            return os.stat(q).st_dev
        except OSError:
            if q.parent == q:
                return None
            q = q.parent


def _tm_kizar(d: Path) -> None:
    """Time Machine-kizárás (a `tmutil addexclusion` ragadós jelölője, közvetlenül: a `tmutil` percekig is futhat)."""
    if sys.platform != "darwin":
        return
    with contextlib.suppress(OSError, AttributeError, ValueError):
        libc = ctypes.CDLL(None, use_errno=True)
        ertek = plistlib.dumps("com.apple.backupd", fmt=plistlib.FMT_BINARY)
        libc.setxattr(os.fsencode(str(d)), b"com.apple.metadata:com_apple_backup_excludeItem", ertek,
                      ctypes.c_size_t(len(ertek)), ctypes.c_uint32(0), ctypes.c_int(0))


# ------------------------------------------------------------------ a workspace.toml


def _ws_tabla(toml: Path) -> dict | None:
    """A `workspace.toml` `[workspace]` táblája; hiányzó fájl: None. Szintaktikai hiba, túl nagy vagy túl mélyen beágyazott fájl:
    `ConfigError(kod="workspace_toml_hibas")` (megbízhatatlan réteg: `config.toml_megbizhatatlan`)."""
    try:
        d = config.toml_megbizhatatlan(toml, "workspace_toml_hibas")
    except (FileNotFoundError, NotADirectoryError):
        return None
    w = d.get("workspace")
    return w if isinstance(w, dict) else {}


# A `.manifold` mappába író, `O_NOFOLLOW` könyvtár-leíróval dolgozó atomi írás: a vizsgálat (`config.munkater_mappa_ellenoriz`) és az
# írás között sem követhető szimbolikus link, ezért egy `.manifold -> más-vault/.manifold` csere a más munkatér fájlját nem írja át
munkater_mappa_ellenoriz = config.munkater_mappa_ellenoriz


def _atomi_ir_nofollow(mappa: Path, nev: str, adat: bytes) -> None:
    """`mappa/nev` atomi, tartós írása: egyedi tmp + `F_FULLFSYNC` + `renameat` ugyanabban a mappában, a mappa `O_NOFOLLOW |
    O_DIRECTORY` leírójával (a mappa maga nem lehet szimbolikus link: `ConfigError(kod="munkater_symlink")`). A cél bejegyzése
    cserélődik, nem követődik."""
    try:
        dfd = os.open(mappa, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as e:
        if e.errno in (errno.ELOOP, errno.ENOTDIR):
            raise ConfigError(f"a munkatér-mappa nem lehet szimbolikus link: {mappa}", kod="munkater_symlink",
                              param={"ut": str(mappa), "ok": "szimbolikus link"}) from e
        raise
    tmp: str | None = f".{nev}.{secrets.token_hex(4)}{tartos.TMP_UTOTAG}"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o666, dir_fd=dfd)
        with os.fdopen(fd, "wb") as fh:
            fh.write(adat)
            fh.flush()
            tartos.fsync_teljes(fh.fileno())
        os.replace(tmp, nev, src_dir_fd=dfd, dst_dir_fd=dfd)
        tmp = None
        tartos.fsync_teljes(dfd)
    finally:
        if tmp is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp, dir_fd=dfd)
        os.close(dfd)


def azonosit(vault: Path) -> str | None:
    """A vault munkatér-azonosítója a `.manifold/workspace.toml`-ból; nincs (vagy hibás, vagy szimbolikus linken át elérhető) munkatér:
    None — a link mögötti azonosító egy másik munkatéré."""
    try:
        config.munkater_mappa_ellenoriz(Path(vault))
    except ConfigError:
        return None
    return toml_azonosito(Path(vault) / MAPPA / WS_TOML)


def toml_azonosito(toml: Path) -> str | None:
    try:
        w = _ws_tabla(Path(toml))
    except (ConfigError, OSError):
        return None
    i = (w or {}).get("id")
    return i if isinstance(i, str) and config.ID_MINTA.match(i) else None


def _toml_ertek(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)          # a JSON-szöveg érvényes TOML alapszöveg
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_toml_ertek(x) for x in v) + "]"
    raise TypeError(type(v))


def _toml_ir(d: dict) -> str:
    sorok = ["# Manifold munkatér-beállítások (F3). A mappával utazik; a `var/` állapot nem.", ""]
    for tabla, ertekek in d.items():
        sorok.append(f"[{tabla}]")
        sorok += [f"{k} = {_toml_ertek(v)}" for k, v in ertekek.items()]
        sorok.append("")
    return "\n".join(sorok)


def _obsidian_beallitasok(vault: Path) -> dict:
    """Az `.obsidian/{app,templates,daily-notes}.json` néhány értéke (csak olvasva; a hiányzó/hibás fájl üres)."""
    ki: dict = {}
    for nev, kulcsok in (("app", ("attachmentFolderPath", "newFileLocation", "newFileFolderPath")),
                         ("templates", ("folder", "dateFormat", "timeFormat")),
                         ("daily-notes", ("folder", "format", "template"))):
        try:
            d = json.loads((vault / OBSIDIAN / f"{nev}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict):
            ki[nev] = {k: d[k] for k in kulcsok if isinstance(d.get(k), str)}
    return ki


def _w_mag(obsidian: dict, alap: Config) -> dict:
    """A W réteg magja az Obsidian beállításaiból (§3.3/5): sablonmappa és a napi jegyzet útja. Csak a réteg-ellenőrzésen
    (`config.reteg_ellenoriz`) átmenő érték kerül be."""
    w: dict = {}
    sablon = (obsidian.get("templates") or {}).get("folder", "").strip().strip("/")
    if sablon:
        w.setdefault("sablon", {})["mappa"] = _nfc(sablon)
    nap = obsidian.get("daily-notes") or {}
    mappa, forma = nap.get("folder", "").strip().strip("/"), (nap.get("format") or "YYYY-MM-DD").strip()
    if mappa and forma and "[" not in mappa and "]" not in mappa:
        w.setdefault("naplo", {})["ut"] = _nfc("/".join(f"[{r}]" for r in mappa.split("/") if r) + "/" + forma)
        tmpl = Path(nap.get("template", "").strip()).name
        if tmpl:
            w["naplo"]["sablon"] = _nfc(tmpl[:-3] if tmpl.lower().endswith(".md") else tmpl)
    if not w:
        return w
    rossz = {k for k, _ in config.reteg_ellenoriz("munkater", w, alap.data)}
    for tabla in list(w):
        for k in list(w[tabla]):
            if f"{tabla}.{k}" in rossz:
                del w[tabla][k]
        if not w[tabla]:
            del w[tabla]
    return w


# ------------------------------------------------------------------ regiszter


class Regiszter:
    """A gép munkatér-regisztere: `{install}/workspaces.json` = `{"formatum":1,"utolso":"<id>","munkaterek":{"<id>":{…}}}`.
    Írás csak a `{install}/run/workspaces.lock` alatt, atomi cserével; a sérült fájl félre kerül (`.serult-<idő>`), nem törlődik."""

    def __init__(self, install: Path):
        self.install = Path(install)
        self.ut = self.install / REGISZTER
        self.zar_ut = self.install / "run" / REGISZTER_ZAR

    @staticmethod
    def _ures() -> dict:
        return {"formatum": 1, "utolso": None, "munkaterek": {}}

    def _beolvas(self) -> tuple[dict, bool]:
        try:
            r = json.loads(self.ut.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return self._ures(), False
        except (OSError, ValueError):
            return self._ures(), True
        if not isinstance(r, dict) or not isinstance(r.get("munkaterek"), dict):
            return self._ures(), True
        r.setdefault("formatum", 1)
        r.setdefault("utolso", None)
        return r, False

    def olvas(self) -> dict:
        return self._beolvas()[0]

    @contextlib.contextmanager
    def _zarolva(self):
        self.zar_ut.parent.mkdir(parents=True, exist_ok=True)
        with open(self.zar_ut, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                r, serult = self._beolvas()
                yield r
                if serult and self.ut.exists():
                    with contextlib.suppress(OSError):
                        os.replace(self.ut, self.ut.with_name(f"{REGISZTER}.serult-{time.strftime('%Y%m%d-%H%M%S')}"))
                tartos.atomi_ir(self.ut, (json.dumps(r, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def felvesz(self, **e) -> dict:
        """Új (vagy meglévő, összefésült) bejegyzés; a legutóbbi munkatér ez lesz."""
        i = e.get("id")
        if not isinstance(i, str) or not config.ID_MINTA.match(i):
            raise ValueError(f"hibás munkatér-azonosító: {i!r}")
        with self._zarolva() as r:
            r["munkaterek"][i] = {**(r["munkaterek"].get(i) or {}), **e}
            r["utolso"] = i
            return dict(r["munkaterek"][i])

    def frissit(self, id: str, **e) -> dict:
        with self._zarolva() as r:
            if id not in r["munkaterek"]:
                raise KeyError(id)
            r["munkaterek"][id].update(e)
            return dict(r["munkaterek"][id])

    def elfelejt(self, id: str) -> bool:
        """A bejegyzés törlése a regiszterből (fájlt nem töröl). → volt-e ilyen."""
        with self._zarolva() as r:
            volt = r["munkaterek"].pop(id, None) is not None
            if r.get("utolso") == id:
                r["utolso"] = max(r["munkaterek"], key=lambda k: str(r["munkaterek"][k].get("megnyitva") or ""),
                                  default=None)
            return volt

    def keres(self, vault: Path) -> tuple[str, dict] | None:
        """A vault (kanonikus út vagy fájlrendszer-azonosság szerint) bejegyzése."""
        kan = kanonikus(vault)
        for i, e in self.olvas()["munkaterek"].items():
            if e.get("kanonikus") == kan:
                return i, e
        for i, e in self.olvas()["munkaterek"].items():
            with contextlib.suppress(OSError, TypeError):
                if os.path.samefile(e.get("vault"), vault):
                    return i, e
        return None

    def keresek(self, vault: Path) -> list[tuple[str, dict]]:
        """A vaulthoz tartozó MINDEN bejegyzés (kanonikus út vagy fájlrendszer-azonosság): egy vaulthoz több azonosító is kerülhetett
        (pl. a `workspace.toml` azonosítója megváltozott). Az eltávolítás csak ezeket felejti el, és csak ezek állapotmappájához nyúl."""
        kan = kanonikus(vault)
        ki = []
        for i, e in self.olvas()["munkaterek"].items():
            if not isinstance(e, dict):
                continue
            egyezik = e.get("kanonikus") == kan
            if not egyezik:
                with contextlib.suppress(OSError, TypeError):
                    egyezik = os.path.samefile(e.get("vault"), vault)
            if egyezik:
                ki.append((i, e))
        return ki


def _bejegyzes(vault: Path, *, id: str, allapot: str, nev: str, demo: bool, letrehozva: str | None = None) -> dict:
    ws = vault / MAPPA
    st = _statfs(vault)
    try:
        inode = os.stat(ws).st_ino
    except OSError:
        inode = None
    return {"id": id, "vault": str(vault), "kanonikus": kanonikus(vault), "kotet_uuid": _kotet_uuid(st[2] if st else None),
            "inode": inode, "allapot": allapot, "nev": nev, "letrehozva": letrehozva or _most(), "megnyitva": _most(),
            "demo": bool(demo)}


# ------------------------------------------------------------------ felmérés


@dataclass(frozen=True)
class Felmeres:
    """A launcher szárazfuttatása (JSON). Az `akadaly`, `figyelmeztetes` és `letrehozando` stabil `kod`-ok listája."""
    vault: str
    letezik: bool
    ures: bool
    irhato: bool
    fajlrendszer: str
    helyi: bool                      # statfs f_fstypename, MNT_LOCAL
    szinkron: str | None             # "icloud" | "cloudstorage" | "dropbox" | None
    kis_nagy_erzekeny: bool
    szabad_bajt: int
    md_db: int
    obsidian: dict                   # app / templates / daily-notes értékei
    meglevo_id: str | None
    reszleges: bool
    formatum: int | None
    eredmeny: str                    # "mehet" | "figyelmeztet" | "tilos"
    akadaly: list
    figyelmeztetes: list
    letrehozando: list

    def json(self) -> dict:
        return asdict(self)


def _abs(vault) -> Path:
    return Path(os.path.abspath(os.path.expanduser(os.fspath(vault))))


def _bejar(v: Path) -> tuple[int, int, int, bool]:
    """(md-fájlok, összes fájl, bájtok, van-e beágyazott munkatér) — a rejtett mappák (I6) és minden pontos mappa nélkül."""
    md = db = bajt = 0
    beagyazott = False
    for dp, dn, fn in os.walk(v):
        if dp != str(v) and MAPPA in dn and (Path(dp) / MAPPA / WS_TOML).is_file():
            beagyazott = True
        dn[:] = [d for d in rejtett.metsz(dn) if not d.startswith(".")]
        for f in fn:
            if f.startswith("."):
                continue
            db += 1
            md += f.lower().endswith(".md")
            with contextlib.suppress(OSError):
                bajt += os.lstat(os.path.join(dp, f)).st_size
    return md, db, bajt, beagyazott


def _core_zar_fut(zar: Path) -> bool:
    """Egy `core.lock` foglalt-e — csak olvasva (`O_RDONLY`, `LOCK_SH|LOCK_NB`, azonnal elengedve)."""
    try:
        fd = os.open(str(zar), os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    except OSError:
        return False
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def _masik_core_fut(v: Path) -> bool:
    """Legjobb igyekezettel (§3.2): egy szomszédos telepítés (`<vault szülője>/*/var/run/core.lock`) core-ja fut-e ezen a
    vaulton — a zár tartalma (`pid … · <vault>`) megnevezi, és a `flock`-ja foglalt."""
    nevek = {str(v).casefold(), os.path.realpath(v).casefold()}
    try:
        jeloltek = list(v.parent.glob("*/var/run/core.lock"))
    except OSError:
        return False
    for zar in jeloltek:
        try:
            with open(zar, encoding="utf-8", errors="replace") as fh:
                tartalom = fh.read(8192)
        except OSError:
            continue
        utolso = tartalom.strip().rsplit(" · ", 1)[-1].strip().casefold()
        if utolso in nevek and _core_zar_fut(zar):
            return True
    return False


def felmer(vault: Path, alap: Config, *, uj: bool = False, demo: bool = False) -> Felmeres:
    """A vault felmérése létrehozás vagy megnyitás előtt (csak olvas). `uj`: a mappa még nem létezik, a létrehozás készíti
    (a szülőnek léteznie kell: leválasztott `/Volumes/X` alá soha). `demo`: a `{install}/demo` alatti bemutató-munkatér."""
    v = _abs(vault)
    akadaly: list[str] = []
    figy: list[str] = []
    letre: list[str] = []
    letezik = v.is_dir()
    if alap.elrendezes != "termek":
        akadaly.append("hordozhato_elrendezes")        # hordozható core soha nem hoz létre `.manifold`-ot (§2.1, K7)
    if v.exists() and not letezik:
        akadaly.append("nem_mappa")
    elif not letezik:
        if not uj:
            akadaly.append("nem_letezik")
        elif not v.parent.is_dir():
            akadaly.append("szulo_hianyzik")
        else:
            letre.append("mappa")
    probe = v if letezik else (v.parent if v.parent.is_dir() else None)
    irhato = bool(probe) and os.access(probe, os.W_OK | os.X_OK)
    if probe is not None and not irhato:
        akadaly.append("nem_irhato")
    install = alap.utak.get("install")
    if _alatt(v, alap.root):
        akadaly.append("kodfaban")
    if _alatt(v, install) and not (demo and install is not None and _alatt(v, install / "demo")):
        akadaly.append("telepitesben")
    if _alatt(alap.root, v):
        akadaly.append("kodfat_tartalmaz")
    if install is not None and _alatt(install, v):
        akadaly.append("telepitest_tartalmaz")
    if any((a / MAPPA / WS_TOML).is_file() for a in v.parents):
        akadaly.append("munkateren_belul")

    meglevo_id = formatum = None
    reszleges = False
    ws = v / MAPPA
    szimlink = False
    try:
        munkater_mappa_ellenoriz(v)                      # a `.manifold` (és a `var`, a `workspace.toml`) link soha nem lehet (K3)
    except ConfigError:
        akadaly.insert(0, "munkater_symlink")
        szimlink = True
    try:
        w = None if szimlink else _ws_tabla(ws / WS_TOML)         # link mögül nem olvasunk
    except ConfigError:
        w = None
        akadaly.append("workspace_toml_hibas")
    if w is not None:
        i = w.get("id")
        meglevo_id = i if isinstance(i, str) and config.ID_MINTA.match(i) else None
        if meglevo_id is None:
            akadaly.append("workspace_id_hibas")
        formatum = w.get("formatum") if isinstance(w.get("formatum"), int) else FORMATUM
        olvaso_min = w.get("olvaso_min") if isinstance(w.get("olvaso_min"), int) else 1
        if olvaso_min > FORMATUM_MAX:
            akadaly.append("workspace_ujabb")
    elif ws.is_dir() and not szimlink:
        reszleges = True

    md_db = 0
    ures = False
    if letezik:
        try:
            ures = not [n for n in os.listdir(v) if n != ".DS_Store"]
        except OSError:
            ures = False
        md_db, db, bajt, beagyazott = _bejar(v)
        if beagyazott:
            akadaly.append("munkateret_tartalmaz")
        if db > NAGY_VAULT_DB or bajt > NAGY_VAULT_BAJT:
            figy.append("nagy_vault")
        if _masik_core_fut(v):
            akadaly.append("masik_telepites_fut")

    st = _statfs(probe) if probe is not None else None
    fajlrendszer, helyi = (st[0], st[1]) if st else ("", True)
    if not helyi:
        akadaly.append("halozati_kotet")
    if st and fajlrendszer != "apfs":
        figy.append("nem_apfs")                          # csökkentett mód: nincs D9-próbaklón (503)
    szinkron = _szinkron(v, Path(alap.table["home"]))
    if szinkron:
        figy.append("szinkron_mappa")                    # az állapot a telepítés alatt; a történet gépenként (§3.7)
    if probe is not None:                                # §3.7: a `{var}` a vault kötetén (klón, atomi csere), különben csökkentett mód
        hely = install / "workspaces" if szinkron and install is not None else v / MAPPA
        e1, e2 = _eszkoz(probe), _eszkoz(hely)
        if e1 is not None and e2 is not None and e1 != e2:
            figy.append("allapot_mas_koteten")
    try:
        szabad = shutil.disk_usage(probe).free if probe is not None else 0
    except OSError:
        szabad = 0
    if probe is not None and szabad < KEVES_HELY_BAJT:
        figy.append("keves_hely")
    if meglevo_id is None:
        if not (v / OBSIDIAN).is_dir():
            letre.append("obsidian")
        letre += ["manifold", "allapot_telepitesben" if szinkron else "allapot", "pillanatkep"]
    eredmeny = "tilos" if akadaly else ("figyelmeztet" if figy else "mehet")
    return Felmeres(vault=str(v), letezik=letezik, ures=ures, irhato=irhato, fajlrendszer=fajlrendszer, helyi=helyi,
                    szinkron=szinkron, kis_nagy_erzekeny=_kis_nagy_erzekeny(probe) if probe is not None else False,
                    szabad_bajt=int(szabad), md_db=md_db, obsidian=_obsidian_beallitasok(v) if letezik else {},
                    meglevo_id=meglevo_id, reszleges=reszleges, formatum=formatum, eredmeny=eredmeny,
                    akadaly=akadaly, figyelmeztetes=figy, letrehozando=letre)


# ------------------------------------------------------------------ környezet


def _munkater_fuggo(utak: dict) -> set[str]:
    """Az [utak] kulcsai, amelyek (közvetve) a vaultból / munkatérből számolódnak (a sablonok helyőrzői szerint)."""
    fuggo = set(_MUNKATER_GYOKEREK)
    valtozott = True
    while valtozott:
        valtozott = False
        for k, t in utak.items():
            if k not in fuggo and isinstance(t, str) and any(h in fuggo for h in config._HELYORZO.findall(t)):
                fuggo.add(k)
                valtozott = True
    return fuggo


def _env(alap: Config, **extra: str) -> dict[str, str]:
    """A `config.load` környezete az alap-konfigurációból: gyökér, HOME, elrendezés, a telepítési réteg fájlja, és a
    környezetből jött, munkatértől FÜGGETLEN `MOS_<KULCS>` értékek (egy másik munkatér rögzített `{var}`-ja nem öröklődik)."""
    env = {"MOS_ROOT": str(alap.root), "HOME": alap.table["home"], "MOS_ELRENDEZES": alap.elrendezes}
    if alap.source is not None and Path(alap.source) != Path(alap.root) / "config" / "os.toml":
        env["MOS_CONFIG"] = str(alap.source)
    settings = (alap.data.get("_meta") or {}).get("settings")
    if settings:
        env["MOS_SETTINGS"] = settings
    fuggo = _munkater_fuggo(alap.data.get("utak") or {})
    for kulcs, reteg in alap.retegek.items():
        k = kulcs.removeprefix("utak.")
        if reteg == "env" and kulcs.startswith("utak.") and k not in fuggo and k in alap.table:
            env[f"MOS_{k.upper()}"] = alap.table[k]
    env.update(extra)
    return env


def munkater_cfg(alap: Config, vault: Path, id: str, var: Path | None = None) -> Config:
    """A vault munkatér-konfigurációja a `workspace.toml` megléte NÉLKÜL is (a létrehozás közben; §3.3/4)."""
    extra = {"MOS_VAULT": str(vault), "MOS_WORKSPACE_ID": id}
    if var is not None:
        extra["MOS_VAR"] = str(var)
    return config.load(_env(alap, **extra))


# ------------------------------------------------------------------ létrehozás


def _jelolo_olvas(ws: Path) -> dict | None:
    for p in (ws / "var" / LETREHOZAS, ws / LETREHOZAS):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and isinstance(d.get("id"), str) and config.ID_MINTA.match(d["id"]):
            return d
    return None


def _ir_ha_mas(p: Path, szoveg: str) -> None:
    """Egy `.manifold`-beli kis fájl (`.gitignore`, `README.txt`) írása, ha a tartalma más; link nem követhető."""
    try:
        if not p.is_symlink() and p.read_text(encoding="utf-8") == szoveg:
            return
    except (OSError, UnicodeDecodeError):
        pass
    _atomi_ir_nofollow(p.parent, p.name, szoveg.encode("utf-8"))


def _var_keszit(var: Path) -> None:
    for d in VAR_ALMAPPAK:
        (var / d).mkdir(parents=True, exist_ok=True)
    if not (var / SPOTLIGHT_JELOLO).exists():
        (var / SPOTLIGHT_JELOLO).touch()
    for d in TM_KIZART:
        _tm_kizar(var / d)


def letrehoz(vault: Path, alap: Config, *, nev=None, nyelv="en", presetek=(), uj_mappa=False, demo=False,
             haladas=lambda d: None) -> dict:
    """Munkatér létrehozása (§3.3; minden lépés idempotens, a véglegesítési pont a `workspace.toml`). A már munkatér vault:
    a meglévő azonosító (és a hiányzó regiszter-bejegyzés pótlása). Tiltó akadálynál `ConfigError(kod=<az első akadály>)`.
    `haladas(d)`: `{"lepes": "felmeres"|"mappak"|"tarolo"|"pillanatkep"|"beallitasok"|"regiszter"|"kesz", …}`."""
    v = _abs(vault)
    install = alap.utak.get("install")
    if install is None:
        raise ConfigError("nincs telepítési mappa", kod="nincs_install")
    if demo and _alatt(v, install / "demo"):
        v.parent.mkdir(parents=True, exist_ok=True)
        uj_mappa = True
    f = felmer(v, alap, uj=uj_mappa and not v.exists(), demo=demo)
    haladas({"lepes": "felmeres", "eredmeny": f.eredmeny, "akadaly": f.akadaly, "figyelmeztetes": f.figyelmeztetes})
    if f.eredmeny == "tilos":
        raise ConfigError(f"a mappa nem tehető munkatérré: {v} ({', '.join(f.akadaly)})", kod=f.akadaly[0],
                          param={"vault": str(v), "akadaly": list(f.akadaly)})
    reg = Regiszter(install)
    allapot = "telepites" if f.szinkron else "vault"
    ws_tabla = {"formatum": FORMATUM, "olvaso_min": 1, "nev": _nfc(str(nev or v.name)), "nyelv": str(nyelv),
                "presetek": [str(p) for p in presetek]}
    rossz = config.reteg_ellenoriz("munkater", {"workspace": {"id": "0" * 32, **ws_tabla}}, alap.data, alap.root)
    if rossz:                                            # mielőtt bármi létrejönne (pl. ismeretlen preset)
        raise ConfigError(f"érvénytelen munkatér-beállítás: {rossz}", kod="workspace_beallitas_hibas",
                          param={"elutasitott": [list(x) for x in rossz]})
    if f.meglevo_id:
        megvan = reg.olvas()["munkaterek"].get(f.meglevo_id)
        if megvan is None:
            w = _ws_tabla(v / MAPPA / WS_TOML) or {}
            reg.felvesz(**_bejegyzes(v, id=f.meglevo_id, allapot=allapot, nev=str(w.get("nev") or v.name), demo=demo))
        with contextlib.suppress(OSError):
            (v / MAPPA / LETREHOZAS).unlink()            # a szinkronizált mappa jelölője (a regiszterig élt)
        haladas({"lepes": "kesz", "id": f.meglevo_id})
        return {"id": f.meglevo_id, "vault": str(v), "uj": False, "allapot": (megvan or {}).get("allapot", allapot)}

    # 2–3. mappák (a jelölő a `.obsidian` előtt: a visszavonás tudja, hogy mi hoztuk-e létre)
    haladas({"lepes": "mappak"})
    munkater_mappa_ellenoriz(v)
    if uj_mappa and not v.exists():
        v.mkdir()
    ws = v / MAPPA
    jel = _jelolo_olvas(ws) or {}
    id = jel.get("id") or uuid.uuid4().hex
    obsidian_letrehozva = bool(jel.get("obsidian_letrehozva")) or not (v / OBSIDIAN).is_dir()
    var = install / "workspaces" / id / "var" if allapot == "telepites" else ws / "var"
    ws.mkdir(exist_ok=True)
    _var_keszit(var)
    jelolo = {"id": id, "obsidian_letrehozva": obsidian_letrehozva, "allapot": allapot,
              "kezdve": jel.get("kezdve") or _most()}
    # a jelölő a `{var}`-ban; szinkronizált mappában (a `{var}` a telepítés alatt) a `.manifold`-ban, a regiszterig
    _atomi_ir_nofollow(ws if allapot == "telepites" else var, LETREHOZAS, json.dumps(jelolo, ensure_ascii=False).encode("utf-8"))
    if not (v / OBSIDIAN).is_dir():
        (v / OBSIDIAN).mkdir()
    _ir_ha_mas(ws / ".gitignore", GITIGNORE)
    _ir_ha_mas(ws / "README.txt", README)

    # 4. a munkatér konfigurációja (a `workspace.toml` még nincs: az azonosító a környezetből)
    cfg = munkater_cfg(alap, v, id, var if allapot == "telepites" else None)

    # 5. a pillanatkép-tároló és az első, szinkron kézi commit (vegyes commit nem lehet: L13, L16)
    haladas({"lepes": "tarolo"})
    with frame.run_lock(cfg):
        repo = snapshot.repos(cfg)["vault"]
        repo.init()
        haladas({"lepes": "pillanatkep", "md_db": f.md_db})
        sha = repo.commit("munkatér létrehozva", {"Mos-Forras": "kezi"})

    # 6. véglegesítési pont
    haladas({"lepes": "beallitasok"})
    w = {"workspace": {"id": id, **ws_tabla, "obsidian_letrehozva": obsidian_letrehozva}}
    w.update(_w_mag(_obsidian_beallitasok(v), alap))
    munkater_mappa_ellenoriz(v)
    _atomi_ir_nofollow(ws, WS_TOML, _toml_ir(w).encode("utf-8"))

    # 7. regiszter
    haladas({"lepes": "regiszter"})
    reg.felvesz(**_bejegyzes(v, id=id, allapot=allapot, nev=w["workspace"]["nev"], demo=demo,
                             letrehozva=jelolo["kezdve"]))
    if allapot == "telepites":
        with contextlib.suppress(OSError):
            (ws / LETREHOZAS).unlink()
    haladas({"lepes": "kesz", "id": id})
    return {"id": id, "vault": str(v), "uj": True, "allapot": allapot, "var": str(var),
            "obsidian_letrehozva": obsidian_letrehozva, "commit": sha}


# ------------------------------------------------------------------ megnyitás


def _athelyezes_bizonyitek(e: dict, vault: Path) -> bool:
    """A regiszter-bejegyzés munkatere ez a (más helyen álló) mappa-e? A `workspace.toml` azonosítója a vaulttal utazik, ezért egy
    másolat vagy egy letöltött vault ugyanazt hordozhatja — az azonosság bizonyítéka a `.manifold` inode-ja (az átnevezés és az
    áthelyezés ugyanazon a köteten megtartja), és ha mindkét oldalon ismert, a kötet UUID-je (`kotet_uuid`). Bizonyíték nélkül a
    mappa nem a regisztrált munkatér áthelyezése: új azonosítót kap, a regiszter régi bejegyzése és a régi mentési mappa érintetlen."""
    try:
        inode = os.stat(vault / MAPPA).st_ino
    except OSError:
        return False
    regi = e.get("inode")
    if not isinstance(regi, int) or isinstance(regi, bool) or regi != inode:
        return False
    regi_uuid = e.get("kotet_uuid")
    if regi_uuid:
        st = _statfs(vault)
        uj_uuid = _kotet_uuid(st[2] if st else None)
        if uj_uuid and uj_uuid != regi_uuid:
            return False
    return True


def _uj_azonosito_ad(cfg: Config, reg: Regiszter, vault: Path, toml: Path, id: str, e: dict, nev: str, uzenetek: list[str],
                     uzenet: str, *, klonoz: bool = True) -> None:
    """A mappa új azonosítót kap (másolat, vagy nem bizonyított áthelyezés): a `workspace.toml` `id` sora atomi cserével, új
    regiszter-bejegyzés; másolatnál (`klonoz`) a szinkronizált munkatér állapota (`{install}/workspaces/<id>/var`) APFS-klónként
    indul az újnak. Nem bizonyított áthelyezésnél (idegen vault is hordozhatja az azonosítót) más munkatér története nem kerül át:
    az állapot üresen indul. A régi bejegyzés, a régi állapot és a régi mentési mappa érintetlen."""
    uj = uuid.uuid4().hex
    if klonoz and e.get("allapot") == "telepites":
        forras = cfg.path("install") / "workspaces" / id / "var"
        cel = cfg.path("install") / "workspaces" / uj / "var"
        if forras.is_dir() and not cel.exists():
            try:
                frame.apfs_clone(forras, cel)            # a másolat a saját (klónozott) történetével indul
            except (RuntimeError, OSError):
                uzenetek.append("The copied workspace state could not be cloned. Its snapshot history starts empty.")
    _uj_id_irasa(toml, id, uj)
    reg.felvesz(**_bejegyzes(vault, id=uj, allapot=str(e.get("allapot") or "vault"), nev=nev, demo=False))
    uzenetek.append(uzenet)


def _uj_id_irasa(toml: Path, regi: str, uj: str) -> None:
    """Az azonosító cseréje a `workspace.toml`-ban (csak az `id` sor; a többi tartalom és a megjegyzések maradnak), atomi."""
    munkater_mappa_ellenoriz(toml.parent.parent, toml.parent)       # közvetlenül az írás előtt is: link mögé nem írunk
    szoveg = toml.read_text(encoding="utf-8")
    uj_szoveg, n = _ID_SOR.subn(lambda m: f"{m.group(1)}{m.group(2)}{uj}{m.group(2)}" if m.group(3) == regi else m.group(0),
                                szoveg, count=1)
    if n != 1 or toml_azonosito_szovegbol(uj_szoveg) != uj:
        raise ConfigError(f"a workspace.toml azonosítója nem cserélhető: {toml}", kod="workspace_id_csere_hiba",
                          param={"ut": str(toml)})
    _atomi_ir_nofollow(toml.parent, toml.name, uj_szoveg.encode("utf-8"))


def toml_azonosito_szovegbol(szoveg: str) -> str | None:
    try:
        i = (tomllib.loads(szoveg).get("workspace") or {}).get("id")
    except tomllib.TOMLDecodeError:
        return None
    return i if isinstance(i, str) and config.ID_MINTA.match(i) else None


def _tarolo_biztosit(cfg: Config) -> None:
    """A pillanatkép-tároló megnyitáskor, a kör-zár alatt (foglaltnál a következő indulás pótolja):
    - megvan, de a `core.worktree`-je nem a vault (áthelyezett vagy másolt munkatér): az idempotens `init` újra (a git-hívások a
      `GIT_WORK_TREE`-t használják; az elavult érték csak a külső eszközöket vezetné félre);
    - nincs, vagy nincs még commitja (szinkronizált munkatér egy másik Macen, ahol a `{install}/workspaces/<id>/var` üres; elveszett
      állapot): `init`, és az első commit szinkron, kézi — mint a létrehozásnál (§3.3/5), hogy az első szerkesztői keret ne
      rögzítse a teljes vaultot a saját üzenetével (vegyes commit, L13/L16)."""
    repo = snapshot.repos(cfg).get("vault")
    if repo is None or not repo.work_tree.is_dir():
        return
    try:
        if repo.exists() and repo.has_head():
            if repo.git("config", "--get", "core.worktree", check=False).stdout.strip() == str(repo.work_tree):
                return
            with frame.indulasi_zar(cfg) as megvan:
                if megvan:
                    repo.init()
            return
        with frame.indulasi_zar(cfg) as megvan:
            if megvan:
                repo.init()
                repo.commit("munkatér megnyitva", {"Mos-Forras": "kezi"})
    except (snapshot.SnapshotError, OSError):
        pass


def _ujratoltes_kell(cfg: Config) -> bool:
    """A `cfg` elavult-e a `nyit` után: a `workspace.toml` már más azonosítót hordoz (másolat), vagy a regiszter szerint az
    állapot a telepítés alatt van (szinkronizált mappa; §3.7), a `cfg` `{var}`-ja mégsem az (a bejegyzés most jött létre)."""
    uj = toml_azonosito(cfg.path("workspace") / WS_TOML)
    if uj is not None and uj != cfg.workspace_id:
        return True
    if not cfg.workspace_id or "install" not in cfg.utak or "var" not in cfg.utak:
        return False
    e = Regiszter(cfg.path("install")).olvas()["munkaterek"].get(cfg.workspace_id) or {}
    return e.get("allapot") == "telepites" \
        and cfg.path("var") != cfg.path("install") / "workspaces" / cfg.workspace_id / "var"


def nyit(cfg: Config) -> list[str]:
    """Core-induláskor (termék; a zárak után, az `App()` helyreállítása ELŐTT; §3.4). → a felhasználónak szóló üzenetek.

    - formátum: `olvaso_min > FORMATUM_MAX` → `ConfigError(kod="workspace_ujabb")`; régebbi formátum → migráció (F3-ban nincs);
    - azonosság a regiszterrel: ugyanaz az azonosító ugyanott → rendben; az azonosító régi helye eltűnt (vagy a kötete nincs
      csatolva, vagy ott már más áll) ÉS a mappa bizonyíthatóan ugyanaz (`_athelyezes_bizonyitek`: a `.manifold` inode-ja és a
      kötet UUID-je egyezik) → **áthelyezett**: a regiszter frissül; a régi hely ugyanezt az azonosítót hordozza, vagy az áthelyezés
      nem bizonyítható (az azonosító a vaulttal utazik: idegen vault is hordozhatja) → **másolat**: új azonosító (a `workspace.toml`
      atomi átírása) és új regiszter-bejegyzés (a történet és a naplók maradnak, a másolaton állnak helyre; a régi bejegyzés és a régi
      mentési mappa érintetlen); ismeretlen azonosító → új bejegyzés (szinkronizált mappában `allapot = "telepites"`, §3.7);
    - a pillanatkép-tároló: `core.worktree` igazítása, hiányzó tároló esetén `init` és szinkron, kézi első commit.
    Másolatnál, és ha az új bejegyzés az állapotot a telepítés alá teszi, a `cfg` elavult (azonosító, `{backup}`, `{var}`): a
    tárolóval ilyenkor az `ujratolt(cfg, environ)` foglalkozik, amellyel a hívó újratölti a konfigurációt és újra rögzíti a
    gyökereket. Hordozható elrendezésben semmit nem tesz (a `.manifold` ott csak olvasott)."""
    if cfg.elrendezes != "termek":
        return []
    vault = cfg.path("vault")
    munkater_mappa_ellenoriz(vault, cfg.path("workspace"))          # link mögé nem nyitunk, és az azonosítót sem írjuk át
    toml = cfg.path("workspace") / WS_TOML
    w = _ws_tabla(toml)
    if w is None:
        raise ConfigError(f"a mappa nem Manifold-munkatér: {vault}", kod="nem_workspace", param={"vault": str(vault)})
    olvaso_min = w.get("olvaso_min") if isinstance(w.get("olvaso_min"), int) else 1
    if olvaso_min > FORMATUM_MAX:
        raise ConfigError(f"a munkatér egy újabb Manifold-változat formátumában van ({olvaso_min} > {FORMATUM_MAX})",
                          kod="workspace_ujabb", param={"olvaso_min": olvaso_min, "formatum_max": FORMATUM_MAX})
    id = toml_azonosito(toml)
    if id is None:
        raise ConfigError(f"hibás munkatér-azonosító: {toml}", kod="workspace_id_hibas", param={"ut": str(toml)})
    if cfg.workspace_id and cfg.workspace_id != id:
        raise ConfigError("a munkatér azonosítója megváltozott a konfiguráció betöltése óta", kod="workspace_csere",
                          param={"vart": cfg.workspace_id, "talalt": id})
    # formatum < FORMATUM: a migrációs lánc (§7.4) itt futna — F3-ban nincs migráció
    uzenetek: list[str] = []
    reg = Regiszter(cfg.path("install"))
    e = reg.olvas()["munkaterek"].get(id)
    nev = str(w.get("nev") or vault.name)
    # új bejegyzés (elveszett regiszter, vagy egy szinkronizált munkatér egy másik Macen): szinkronizált mappában az állapot a
    # telepítés alatt (§3.7), soha nem a felhőben — a `cfg` ilyenkor elavult, az `ujratolt` tölti újra
    szinkron = _szinkron(vault, Path(cfg.table["home"]))
    allapot = "telepites" if cfg.forras("utak", "var") == "regiszter" or szinkron else "vault"
    if e is None:
        reg.felvesz(**_bejegyzes(vault, id=id, allapot=allapot, nev=nev, demo=False))
    else:
        regi = Path(str(e.get("vault") or ""))
        ugyanaz = e.get("kanonikus") == kanonikus(vault)
        if not ugyanaz:
            with contextlib.suppress(OSError, TypeError):
                ugyanaz = os.path.samefile(regi, vault)
        if ugyanaz:
            frissites = {"vault": str(vault), "kanonikus": kanonikus(vault), "megnyitva": _most()}
            with contextlib.suppress(OSError):
                frissites["inode"] = os.stat(vault / MAPPA).st_ino      # az áthelyezés bizonyítéka naprakész marad
            if not e.get("kotet_uuid"):
                st = _statfs(vault)
                frissites["kotet_uuid"] = _kotet_uuid(st[2] if st else None)
            reg.frissit(id, **frissites)
            reg.felvesz(id=id)                           # a legutóbbi
        elif e.get("vault") and regi.is_dir() and azonosit(regi) == id:
            _uj_azonosito_ad(cfg, reg, vault, toml, id, e, nev, uzenetek,
                             f"This folder is a copy of another workspace ({regi}). It received a new ID; the original workspace is unchanged.")
        elif not _athelyezes_bizonyitek(e, vault):
            # az azonosító a vaulttal utazik, de a régi hely eltűnt, és a mappa nem bizonyíthatóan az: idegen vault is hordozhatja —
            # a regisztrált munkatér bejegyzését és mentéseit nem vehetjük át (K5)
            _uj_azonosito_ad(cfg, reg, vault, toml, id, e, nev, uzenetek,
                             f"This folder carries the ID of an earlier workspace ({regi}), but could not be verified as its moved instance. "
                             "It received a new ID and starts with empty state; the earlier registration is unchanged.",
                             klonoz=False)
        else:
            reg.frissit(id, **{k: x for k, x in _bejegyzes(vault, id=id, allapot=str(e.get("allapot") or allapot), nev=nev,
                                                           demo=bool(e.get("demo"))).items()
                               if k not in ("letrehozva", "id", "allapot", "demo")})
            reg.felvesz(id=id)
            uzenetek.append(f"The workspace opened at a new location ({regi} → {vault}).")
    if not _ujratoltes_kell(cfg):                        # különben a `cfg` állapota (`{var}`) nem ezé a munkatéré: az `ujratolt` dolga
        _tarolo_biztosit(cfg)
    return uzenetek


def ujratolt(cfg: Config, environ) -> Config | None:
    """A `nyit` után: ha a `cfg` elavult (`_ujratoltes_kell`: másolat új azonosítóval, vagy a regiszter szerint a telepítés alatti
    állapot), a munkatértől függő rögzített `MOS_*` kulcsok törlődnek az `environ`-ból, a `MOS_WORKSPACE_ID` a `workspace.toml`-é
    lesz, a konfiguráció újratöltődik, és a pillanatkép-tároló az új állapotban készül el (`_tarolo_biztosit`).
    → az új `Config` (a hívó a `gyokerek.rogzit`-tal újra rögzít), vagy None, ha nincs változás."""
    if cfg.elrendezes != "termek" or not _ujratoltes_kell(cfg):
        return None
    uj = toml_azonosito(cfg.path("workspace") / WS_TOML) or cfg.workspace_id
    for k in _munkater_fuggo(cfg.data.get("utak") or {}) - {"vault"}:
        environ.pop(f"MOS_{k.upper()}", None)
    environ["MOS_WORKSPACE_ID"] = uj
    ucfg = config.load(dict(environ))
    _tarolo_biztosit(ucfg)
    return ucfg


# ------------------------------------------------------------------ eltávolítás


def eltavolit(vault: Path, alap: Config, kuka) -> dict:
    """„Manifold-adatok eltávolítása” (§3.3): a `.manifold/` (és a regisztrált `{install}/workspaces/<id>`) a Kukába (`kuka(ut)`), a
    `.obsidian/` csak ha mi hoztuk létre ÉS még üres, a regiszter-bejegyzés törlődik. A vault fájljai érintetlenek (I7).
    Futó core-ral (foglalt `core.lock`) nem fut: `ConfigError(kod="munkater_hasznalatban")`.

    A telepítés alatti állapotmappához és a regiszter-bejegyzéshez csak az a bejegyzés ad jogot, amelynek az útja ez a vault
    (`Regiszter.keresek`: kanonikus út / fájlrendszer-azonosság) — a vault saját `workspace.toml`-ja és jelölője megbízhatatlan, az
    abban álló azonosító egy MÁSIK munkatér állapotmappáját és bejegyzését nem tüntetheti el."""
    v = _abs(vault)
    install = alap.utak.get("install")
    ws = v / MAPPA
    reg = Regiszter(install) if install is not None else None
    sajat = reg.keresek(v) if reg is not None and v.is_dir() else []          # a regiszter szerinti azonosítók: ezek a miénk
    link = ws.is_symlink()                                                      # link mögül (másik munkatér) semmit nem olvasunk
    jel = {} if link else (_jelolo_olvas(ws) or {})
    try:
        w = {} if link else (_ws_tabla(ws / WS_TOML) or {})
    except ConfigError:
        w = {}
    sajat_idk = [i for i, _ in sajat]
    id = sajat_idk[0] if sajat_idk else (azonosit(v) or jel.get("id"))
    telepek = [install / "workspaces" / i for i in sajat_idk if install is not None]
    sajat_zar = [] if link else [ws / "var" / "run" / "core.lock"]                 # link mögött egy másik munkatér zára áll: nem a miénk
    for zar in (*sajat_zar, *(t / "var" / "run" / "core.lock" for t in telepek)):
        if _core_zar_fut(zar):
            raise ConfigError(f"a munkatér használatban van (fut rajta a Manifold): {v}", kod="munkater_hasznalatban",
                              param={"vault": str(v)})
    kukaba: list[str] = []
    if ws.exists() or ws.is_symlink():
        kuka(ws)
        kukaba.append(str(ws))
    for telep in telepek:
        if telep.exists():
            kuka(telep)
            kukaba.append(str(telep))
    obs = v / OBSIDIAN
    obsidian_torolve = False
    if (w.get("obsidian_letrehozva") is True or jel.get("obsidian_letrehozva") is True) and obs.is_dir() \
            and not obs.is_symlink():
        with contextlib.suppress(OSError):
            if not os.listdir(obs):
                obs.rmdir()
                obsidian_torolve = True
    if reg is not None:
        for i in sajat_idk:
            reg.elfelejt(i)
    return {"ok": True, "id": id, "kukaba": kukaba, "obsidian_torolve": obsidian_torolve}


def _hej_kuka(alap: Config):
    """A héj Kuka-segedje (`<hej_cli> --kuka`, `shell/Sources/Kuka.swift`): a megadott elem a Kukába, a szülője mint gyökér."""
    def kuka(p: Path) -> None:
        seged = alap.utak.get("hej_cli")
        if seged is None:
            raise ConfigError("a Kuka-seged nem érhető el", kod="kuka_hiba")
        try:
            h = subprocess.run([str(seged), "--kuka"], input=json.dumps({"ut": str(p), "gyoker": str(Path(p).parent)}),
                               capture_output=True, text=True, timeout=60)
            valasz = json.loads(h.stdout or "{}")
        except (OSError, subprocess.TimeoutExpired, ValueError) as e:
            raise ConfigError(f"a Kukába helyezés nem sikerült: {p}", kod="kuka_hiba", param={"ut": str(p)}) from e
        if h.returncode != 0 or not isinstance(valasz, dict) or valasz.get("ok") is not True:
            raise ConfigError(f"a Kukába helyezés nem sikerült: {p}", kod="kuka_hiba", param={"ut": str(p)})
    return kuka


# ------------------------------------------------------------------ CLI


_PARANCSOK = ("felmer", "letrehoz", "lista", "elfelejt", "eltavolit")
_SZOVEG = {
    "hordozhato_elrendezes": "hordozható (fejlesztői) elrendezésben a Manifold nem hoz létre munkateret",
    "nem_mappa": "az út nem mappa", "nem_letezik": "a mappa nem létezik", "szulo_hianyzik": "a szülőmappa nem létezik",
    "nem_irhato": "a mappa nem írható", "kodfaban": "a mappa a Manifold programmappájában van",
    "telepitesben": "a mappa a Manifold telepítési mappájában van",
    "kodfat_tartalmaz": "a mappa tartalmazza a Manifold programmappáját",
    "telepitest_tartalmaz": "a mappa tartalmazza a Manifold telepítési mappáját",
    "munkateren_belul": "a mappa egy másik munkatér belsejében van", "munkateret_tartalmaz": "a mappa egy munkateret tartalmaz",
    "munkater_symlink": "a .manifold (vagy a var, a workspace.toml) szimbolikus link: ilyen munkatér nem nyitható",
    "workspace_toml_hibas": "a .manifold/workspace.toml hibás", "workspace_id_hibas": "a munkatér azonosítója hibás",
    "workspace_ujabb": "a munkatér egy újabb Manifold-változaté", "halozati_kotet": "hálózati kötet (a zárolás megbízhatatlan)",
    "masik_telepites_fut": "egy másik Manifold-telepítés fut ezen a mappán",
    "nem_apfs": "nem APFS-kötet: csökkentett mód (nincs próbaklón)", "szinkron_mappa": "szinkronizált mappa: az állapot gépenként",
    "allapot_mas_koteten": "az állapot mappája másik köteten van: csökkentett mód (nincs próbaklón)",
    "keves_hely": "kevés a szabad hely", "nagy_vault": "nagy vault: az első pillanatkép időbe telik",
}


def _alap_cfg() -> Config:
    env = {k: v for k, v in os.environ.items() if k not in ("MOS_VAULT", "MOS_WORKSPACE_ID", "MOS_WORKSPACE")}
    return config.load(env, munkater=False)


def _kiir(adat, json_mod: bool, szoveg: str = "") -> None:
    print(json.dumps(adat, ensure_ascii=False, indent=1) if json_mod else szoveg)


def main(argv: list[str] | None = None) -> int:
    import argparse
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in _PARANCSOK:
        argv = ["felmer", *argv]
    ap = argparse.ArgumentParser(prog="mos workspace", description="Munkaterek: felmérés, létrehozás, lista, eltávolítás")
    ap.add_argument("parancs", choices=_PARANCSOK)
    ap.add_argument("vault", nargs="?")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--igen", action="store_true", help="megerősítés (figyelmeztetésnél és eltávolításnál kötelező)")
    ap.add_argument("--nev")
    ap.add_argument("--nyelv", default="en")
    ap.add_argument("--preset", action="append", default=[])
    ap.add_argument("--uj-mappa", action="store_true")
    a = ap.parse_args(argv)
    try:
        alap = _alap_cfg()
        if a.parancs == "lista":
            r = Regiszter(alap.path("install")).olvas()
            _kiir(r, a.json, "\n".join(f"{i}  {e.get('nev', '')}  {e.get('vault', '')}" for i, e in r["munkaterek"].items())
                  or "nincs munkatér")
            return 0
        if not a.vault:
            ap.error("hiányzik a mappa")
        if a.parancs == "elfelejt":
            reg = Regiszter(alap.path("install"))
            cel = a.vault if config.ID_MINTA.match(a.vault) else ((reg.keres(_abs(a.vault)) or (None,))[0])
            volt = bool(cel) and reg.elfelejt(cel)
            _kiir({"ok": volt, "id": cel}, a.json, "elfelejtve" if volt else "nincs ilyen munkatér a regiszterben")
            return 0 if volt else 1
        if a.parancs == "felmer":
            f = felmer(_abs(a.vault), alap, uj=a.uj_mappa)
            _kiir(f.json(), a.json, f"{f.eredmeny}: " + "; ".join(_SZOVEG.get(k, k) for k in f.akadaly + f.figyelmeztetes))
            return 1 if f.eredmeny == "tilos" else 0
        if a.parancs == "letrehoz":
            f = felmer(_abs(a.vault), alap, uj=a.uj_mappa)
            if f.eredmeny == "figyelmeztet" and not a.igen:
                _kiir({"hiba": "megerosites_kell", "felmeres": f.json()}, a.json,
                      "figyelmeztetés: " + "; ".join(_SZOVEG.get(k, k) for k in f.figyelmeztetes) + " — futtasd újra --igen-nel")
                return 1
            def haladas(d):
                print(json.dumps({"haladas": d}, ensure_ascii=False) if a.json else f"[munkatér] {d.get('lepes')}",
                      file=sys.stderr, flush=True)
            r = letrehoz(_abs(a.vault), alap, nev=a.nev, nyelv=a.nyelv, presetek=a.preset, uj_mappa=a.uj_mappa,
                         haladas=haladas)
            _kiir(r, a.json, f"munkatér kész: {r['id']} ({r['vault']})")
            return 0
        # eltavolit
        if not a.igen:
            _kiir({"hiba": "megerosites_kell"}, a.json, "a .manifold a Kukába kerülne — futtasd újra --igen-nel")
            return 1
        r = eltavolit(_abs(a.vault), alap, _hej_kuka(alap))
        _kiir(r, a.json, "eltávolítva: " + ", ".join(r["kukaba"]))
        return 0
    except ConfigError as e:
        _kiir({"hiba": e.kod, "param": e.param, "uzenet": str(e)}, a.json,
              f"hiba ({e.kod}): {_SZOVEG.get(e.kod, str(e))}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
