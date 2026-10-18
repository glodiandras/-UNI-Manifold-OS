"""Import into Manifold (F8, PLAN §6): an Obsidian vault into a NEW workspace, and the developer's Manifold-OS v2 conventions into
the settings of the open workspace. Both share one frame: a read-only **preview** (dry-run), a **journal**, a resumable run, and a
complete **undo**.

Obsidian import (`obsidian_elonezet` → `obsidian_importal` → `visszafordit`)
----------------------------------------------------------------------------
- The **source is never written**: it is only walked (`os.walk`, `lstat`) and read (`open(O_RDONLY|O_NOFOLLOW)`, `clonefile` with the
  source as the read side). Nothing is created next to it, no timestamp is set on it.
- The **target** is a new (missing or empty) folder. Every file is copied **unchanged** (byte for byte; frontmatter, links,
  attachments, `.canvas`, `.base`, `.obsidian/` — there is no rewriting option in this version, the preview says so in `atiras: []`):
  APFS clone into a `.<name>.<hex>.manifold-tmp` next to the destination, or a hashed stream copy (fsync, mtime and birth time
  kept); then `rename_excl` — an existing destination is never overwritten. After the copy the folder becomes a workspace
  (`workspace.letrehoz`: `.manifold/`, snapshot store, first `Mos-Forras: kezi` commit, `templates.json`/`daily-notes.json` →
  `[sablon]`/`[naplo]`), and the mapped `.obsidian` settings are written into `workspace.toml` (`[beallitasok.*]`, `[sablon]`;
  the previous file is kept as `workspace.toml.elozo`). `.obsidian/app.json` (attachment and new-note folders) and
  `.obsidian/types.json` (property types) are read by Manifold directly from the copied `.obsidian/`.
- Skipped and reported: symlinks, special files, `.DS_Store`/`._*`, `*.manifold-tmp`, `.git/`, nested `.manifold/`, other hidden
  entries outside `.obsidian/`, Obsidian's `.trash/` (unless `opciok.kuka_mappa`), `.obsidian/` itself only with
  `opciok.obsidian_mappa = false`.
- **Journal**: `{install}/imports/<id>/` — `allapot.json` (state), `naplo.jsonl` (append-only, fsync per record: every created folder,
  every temporary file, every copied file with its sha256 BEFORE it is renamed into place, the workspace), `terv.json` (the full
  plan). The id is `obs-<16 hex>` from the canonical source and target paths, so a repeated run finds its own journal.
- **Cancel** (`POST /api/import/megszakit`): the running thread stops at the NEXT FILE BOUNDARY (a file in progress is finished and
  renamed into place, so no temporary file and no half file is left); the journal gets a `megszakitva` record and the state
  `megszakitva`. The source is untouched, the copied files are kept; the cancelled import is resumed or undone like a failed one.
- **Resume**: after a failure (`allapot: "hiba"`) or a cancel (`"megszakitva"`) the same call continues: own temporary files are removed, files already in place
  with the source's bytes are kept, nothing else is touched. **Idempotent**: after `kesz`, a new run writes nothing
  (`ismetles: true`).
- **Undo** (`visszafordit`): refused while a Manifold core runs on the target. The workspace data (`.manifold/`, the registry entry,
  the install-side state) goes to the Trash (`workspace.eltavolit`); every imported file that still has its imported bytes goes to
  the Trash (the whole target folder at once when the import created it and nothing else is left); files changed after the import
  and foreign files stay (`megtartva`). Nothing is deleted permanently; the source is untouched.

v2 import (`v2_elonezet` → `v2_importal` → `visszafordit`; Developer mode only)
------------------------------------------------------------------------------
Reads a Manifold-OS v2 folder (`config/os.toml`, `config/vault-sema.json`; read-only) and transfers the developer's own conventions
into the OPEN workspace — never into the code tree: only workspace-layer keys (`config.RETEG_JOG["munkater"]`, the same filter as
`workspace.toml`) that differ from the current effective value, and the schema to `{workspace}/schema.json` (`[sema] mod =
"szigoru"`). A key the workspace already sets to another value, or an existing different schema, is a conflict and is NOT
overwritten. Journal: `{state}/import/<id>/` (`v2-<16 hex>`), with the previous bytes of each written file; undo restores them
only if the file still holds the imported bytes (otherwise 409, nothing changes). A config change needs a core restart
(`ujrainditas: true`). Machine state (`var/*.sqlite`, `vault.git`, models, calibration) is not transferred by this tool.

HTTP / WS contract (registered in `core/server.py`)
---------------------------------------------------
- `POST /api/import/obsidian/elonezet` `{forras, cel, opciok?}` → the preview (below). Never writes.
- `POST /api/import/obsidian` `{forras, cel, opciok?, terv_hash}` → `202 {id, allapot: "fut"}`; the run is a background thread.
  409 `import.terv_valtozott` (the source or the target changed since the preview: preview again), 409 `import.tilos`
  (`param.akadaly`), 409 `import.fut`, 409 `import.utkozes`.
- `GET /api/import` → `{importok: [allapot…]}` (this install's Obsidian imports and this workspace's v2 imports, newest first).
- `POST /api/import/megszakit` `{id}` → cancels the running Obsidian import of this core (user's click only, never a machine step):
  `200 {id, allapot: "megszakitva"|"kesz"|"hiba", megszakitva: bool}` once the thread has stopped (the copy stops at the next file
  boundary; `kesz` when the import had already finished), `202 {id, allapot: "megszakitas"}` when the current file is still being
  copied after ~10 s (the WS event `allapot: "megszakitva"` follows), 409 `import.nem_fut` when no import with that ID runs here.
- `GET /api/import/allapot?id=` → the journal state: `{id, fajta, allapot: "fut"|"hiba"|"megszakitva"|"kesz"|"visszaforditva"|
  "reszben_visszaforditva", forras, cel, kezdve, frissitve, hiba?: {kod, uzenet, param}, eredmeny?}`.
- `POST /api/import/visszafordit` `{id}` → the undo result `{id, allapot, kukaba: [..], megtartva: [{ut, ok}], visszaallitva: [..]}`.
  409 `import.munkater_hasznalatban` (Obsidian: the imported workspace is open), 409 `import.visszafordit_utkozes` (v2).
- `POST /api/import/v2/elonezet` `{forras}` and `POST /api/import/v2` `{forras, terv_hash}` → Developer mode only
  (403 `import.fejleszto_mod`); the run is synchronous (small) and returns `{id, allapot: "kesz", valtozas, ujrainditas: true}`.
- WS: `{"tipus": "import", "id", "fajta": "obsidian", "lepes": "masolas"|"munkater"|"beallitasok", "kesz_db", "osszes_db",
  "bajt"}` while copying (at most ~4 per second), and once at the end `{"tipus": "import", "id", "fajta", "allapot": "kesz"|"hiba"|"megszakitva",
  "eredmeny"? , "hiba"?}`.

Preview (`elonezet`) fields: `verzio`, `id`, `fajta`, `forras`, `cel`, `eredmeny` (`"mehet"|"figyelmeztet"|"tilos"|"kesz"`),
`akadaly`, `figyelmeztetes` (stable codes), `allapot` (the journal's, or null), `opciok`, `osszesites` (`fajl_db`, `bajt`, `md_db`,
`canvas_db`, `base_db`, `csatolmany_db`, `obsidian_db`, `egyeb_db`, `mappa_db`, `kihagyott_db`, `masolando_db`, `megvan_db`),
`fajlok` (≤ `MAX_LISTA` rows `{ut, fajta, meret, muvelet: "masol"|"megvan"|"utkozes"}`, `fajlok_csonkitva`), `kihagyott`
(`{ut, ok}`), `utkozesek` (`{ut, ok: "kis_nagy"|"normalizalas"|"cel_elter"}`), `linkek` (`wikilink_db`, `markdown_link_db`,
`beagyazas_db`, `frontmatter_db`, `beallitas: {wikilinkek, link_formatum}`), `obsidian` (`beallitasok: [{kulcs, ertek, forras,
mod: "ir"|"azonos"|"munkater"|"kozvetlen"}]`, `nem_atvett: [{forras, kulcs?, ok}]`, `mag_pluginok`, `kozossegi_pluginok`,
`tipusok_db`), `atiras: []`, `letrehozando`, `szabad_bajt`, `terv_hash`.
Codes: akadaly `forras_nem_mappa`, `forras_nem_olvashato`, `cel_a_forrasban`, `forras_a_celban`, `cel_nem_ures`, `cel_munkater`,
`nev_utkozes`, `fajl_utkozes`, `keves_hely`, `nincs_install`, `import_fut`, plus every `workspace.felmer` akadaly of the target;
figyelmeztetes `forras_munkater`, `keves_hely`, `kihagyott_elemek`, `nem_tamogatott_pluginok`, plus `workspace.felmer`'s.

CLI: `python -m core.importalas obsidian elonezet|importal <forras> <cel> [--kuka-mappa] [--obsidian-nelkul] [--hash H]`,
`python -m core.importalas v2 elonezet|importal <v2-mappa> [--hash H]` (needs `MOS_VAULT`; Developer mode),
`python -m core.importalas visszafordit <id>`, `python -m core.importalas lista`. Output is JSON.
"""
from __future__ import annotations

import contextlib
import copy
import errno
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import sys
import threading
import time
import tomllib
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import config, importalas_billentyuk, kiserok, mediatipus, rejtett, tartos, termek_beallitasok, workspace
from .config import ConfigError
from .index.maszk import FM_RE, mask_code
from .utvonalak import HttpError, Valasz

VERZIO = 1
MAX_LISTA = 500                         # a preview's file rows (the full plan is in the journal's `terv.json`)
MAX_JSON_BAJT = 1 << 20                 # an `.obsidian/*.json` larger than this is not read
MAX_LINK_BAJT = 2 << 20                 # link counting reads Markdown files up to this size
ALLAPOT = "allapot.json"
NAPLO = "naplo.jsonl"
TERV = "terv.json"
ZAR = "zar.lock"
VISSZAVONAS_ELOTAG = ".manifold-import-visszavonas-"
_ID = re.compile(r"\A(obs|v2)-[0-9a-f]{16}\Z")
_HALADAS_MP = 0.25
_VEZERLO = re.compile("[\x00-\x1f\x7f]")

_BILLENTYU_TABLA = "beallitasok.billentyuk."

ALAP_OPCIOK = {"obsidian_mappa": True, "kuka_mappa": False, "nev": ""}

# Obsidian core plugin → Manifold module (`termek_beallitasok.MODULOK`) or a built-in feature. Anything else: not supported.
MAG_PLUGIN = {
    "backlink": "hivatkozasok", "outgoing-link": "hivatkozasok", "outline": "vazlat", "properties": "tulajdonsagok",
    "switcher": "gyorsvalto", "global-search": "kereses", "slash-command": "perjel", "tag-pane": "cimkek",
    "templates": "sablonok", "daily-notes": "napi", "canvas": "canvas", "bases": "bazis", "graph": "graf",
}
MAG_BEEPITETT = ("file-explorer", "command-palette", "file-recovery", "editor-status")

# `.obsidian/<fájl>.json` key → (dotted Manifold key, conversion; `None` result: not transferable)
_TEMA = {"obsidian": "sotet", "moonstone": "vilagos", "system": "rendszer"}
_LINK = {"shortest": "rovid", "relative": "relativ", "absolute": "abszolut"}


def _bool(v):
    return v if type(v) is bool else None


def _int(v):
    return v if type(v) is int else None


def _str(v):
    return v if isinstance(v, str) and v.strip() else None


LEKEPEZES = {
    "app": {
        "useMarkdownLinks": ("beallitasok.fajlok.wikilinkek", lambda v: (not v) if type(v) is bool else None),
        "newLinkFormat": ("beallitasok.fajlok.link_formatum", lambda v: _LINK.get(v) if isinstance(v, str) else None),
        "readableLineLength": ("beallitasok.szerkeszto.olvashato_szelesseg", _bool),
        "spellcheck": ("beallitasok.szerkeszto.helyesiras", _bool),
        "tabSize": ("beallitasok.szerkeszto.tab_meret", _int),
        "livePreview": ("beallitasok.szerkeszto.mod", lambda v: ("elo" if v else "forras") if type(v) is bool else None),
    },
    "appearance": {
        "baseFontSize": ("beallitasok.megjelenes.betumeret", _int),
        "theme": ("beallitasok.megjelenes.tema", lambda v: _TEMA.get(v) if isinstance(v, str) else None),
    },
    "templates": {
        "dateFormat": ("sablon.datum", _str),
        "timeFormat": ("sablon.ido", _str),
    },
}
# read by Manifold straight from the copied `.obsidian/` (`core/csatolmany.py`, `termek_beallitasok._ertek`, `tulajdonsag_tipusok`)
KOZVETLEN = {
    "app": {"attachmentFolderPath": "beallitasok.fajlok.csatolmany_mappa", "newFileLocation": "beallitasok.fajlok.uj_mappa",
            "newFileFolderPath": "beallitasok.fajlok.uj_mappa"},
}
# written into `workspace.toml` by `workspace.letrehoz` (`_w_mag`) from the copied `.obsidian/`
MUNKATER_ALTAL = {"templates": {"folder": "sablon.mappa"},
                  "daily-notes": {"folder": "naplo.ut", "format": "naplo.ut", "template": "naplo.sablon"}}

# v2 keys never taken from the v2 file (identity and the code tree's own schema locations)
V2_KIHAGY = ("workspace.", "sema.vault", "sema.alap", "beallitasok.", "modulok.")

_WIKILINK = re.compile(r"(?<!!)\[\[[^\]\n]+\]\]")
_BEAGYAZAS = re.compile(r"!\[\[[^\]\n]+\]\]|!\[[^\]\n]*\]\((?![A-Za-z][A-Za-z0-9+.-]*:)[^)\n]+\)")
_MD_LINK = re.compile(r"(?<![!\]])\[[^\]\n]*\]\((?![A-Za-z][A-Za-z0-9+.-]*:)(?!#)[^)\n]+\)")


# ------------------------------------------------------------------ errors


def _tilos(akadaly: list[str]) -> HttpError:
    return HttpError(409, "The import cannot start: " + ", ".join(akadaly) + ".", kod="import.tilos",
                     param={"akadaly": ", ".join(akadaly)})


def _terv_valtozott() -> HttpError:
    return HttpError(409, "The folders changed since the preview. Run the preview again.", kod="import.terv_valtozott")


def _utkozes(ut: str) -> HttpError:
    return HttpError(409, f"A file already exists in the destination with different content: {ut}.", kod="import.utkozes",
                     param={"ut": ut})


# ------------------------------------------------------------------ small helpers


def _most() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _sha(b: bytes | None) -> str | None:
    return None if b is None else hashlib.sha256(b).hexdigest()


def _sha_fajl(p: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    n = 0
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        while True:
            darab = os.read(fd, 1 << 20)
            if not darab:
                break
            h.update(darab)
            n += len(darab)
    finally:
        os.close(fd)
    return h.hexdigest(), n


def _olvas_opcionalis(p: Path, max_bajt: int = MAX_JSON_BAJT) -> bytes | None:
    try:
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        with os.fdopen(fd, "rb", closefd=False) as fh:
            adat = fh.read(max_bajt + 1)
    finally:
        os.close(fd)
    return None if len(adat) > max_bajt else adat


def _json_fajl(p: Path):
    """→ (adat, hiba-kód | None): `hianyzik`, `tul_nagy`, `hibas_json`."""
    if not p.exists() and not p.is_symlink():
        return None, "hianyzik"
    nyers = _olvas_opcionalis(p)
    if nyers is None:
        return None, "tul_nagy"
    try:
        return json.loads(nyers.decode("utf-8")), None
    except (ValueError, UnicodeDecodeError):
        return None, "hibas_json"


def _rel(p: str) -> str:
    return p.replace(os.sep, "/")


def _beagyaz(kulcs: str, ertek) -> dict:
    d: dict = {}
    node = d
    reszek = kulcs.split(".")
    for r in reszek[:-1]:
        node = node.setdefault(r, {})
    node[reszek[-1]] = ertek
    return d


def _keres(d: dict, kulcs: str, alap=None):
    node = d
    for r in kulcs.split("."):
        if not isinstance(node, dict) or r not in node:
            return alap
        node = node[r]
    return node


def _levelek(d: dict, elotag: str = ""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from _levelek(v, f"{elotag}{k}.")
        else:
            yield f"{elotag}{k}", v


def _melyegyesit(cel: dict, uj: dict) -> dict:
    return termek_beallitasok.egyesit(cel, uj)


def _terv_hash(adat) -> str:
    return hashlib.sha256(json.dumps(adat, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _abszolut(ut, mezo: str) -> Path:
    if not isinstance(ut, str) or not ut or len(ut) > 4096 or "\x00" in ut:
        raise HttpError(400, f"The `{mezo}` field must be a folder path.", kod="import.ervenytelen_keres",
                        param={"mezo": mezo})
    return workspace._abs(ut)


def _opciok(o) -> dict:
    if o is None:
        return dict(ALAP_OPCIOK)
    if not isinstance(o, dict) or set(o) - set(ALAP_OPCIOK):
        raise HttpError(400, "The import options are not valid.", kod="import.ervenytelen_keres", param={"mezo": "opciok"})
    ki = dict(ALAP_OPCIOK)
    for k, v in o.items():
        if type(v) is not type(ALAP_OPCIOK[k]):
            raise HttpError(400, "The import options are not valid.", kod="import.ervenytelen_keres", param={"mezo": "opciok"})
        ki[k] = v
    if len(ki["nev"]) > 100 or _VEZERLO.search(ki["nev"]):
        raise HttpError(400, "The import options are not valid.", kod="import.ervenytelen_keres", param={"mezo": "opciok"})
    return ki


# ------------------------------------------------------------------ the journal


class Naplo:
    """One import's journal folder: `allapot.json` (atomic), `naplo.jsonl` (append + fsync per record), `terv.json`, `zar.lock`."""

    def __init__(self, mappa: Path):
        self.mappa = Path(mappa)

    def _keszit(self) -> None:
        for a in (self.mappa.parent, self.mappa):
            if a.is_symlink():
                raise OSError(errno.ELOOP, "the import journal folder must not be a symbolic link", str(a))
        self.mappa.mkdir(parents=True, exist_ok=True)

    def allapot(self) -> dict | None:
        nyers = _olvas_opcionalis(self.mappa / ALLAPOT, 8 << 20)
        if nyers is None:
            return None
        try:
            d = json.loads(nyers.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
        return d if isinstance(d, dict) else None

    def allapot_ir(self, **e) -> dict:
        self._keszit()
        d = {**(self.allapot() or {}), **e, "frissitve": _most()}
        tartos.atomi_ir(self.mappa / ALLAPOT, (json.dumps(d, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
        return d

    def sor(self, d: dict) -> None:
        self._keszit()
        fd = os.open(self.mappa / NAPLO, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, (json.dumps({**d, "ido": _most()}, ensure_ascii=False) + "\n").encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)

    def sorok(self) -> list[dict]:
        try:
            nyers = (self.mappa / NAPLO).read_bytes()
        except OSError:
            return []
        ki = []
        for s in nyers.splitlines():
            try:
                d = json.loads(s.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue                    # a torn last record (crash during append) is ignored
            if isinstance(d, dict):
                ki.append(d)
        return ki

    def archival(self) -> None:
        """A new run after an undo: the old records are kept under a dated name, the new run starts a fresh journal."""
        for n in (NAPLO, TERV):
            p = self.mappa / n
            if p.exists():
                os.replace(p, self.mappa / f"{p.stem}-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}{p.suffix}")

    def fajl_ir(self, nev: str, adat: bytes) -> None:
        self._keszit()
        tartos.atomi_ir(self.mappa / nev, adat)

    @contextlib.contextmanager
    def zar(self):
        self._keszit()
        fd = os.open(self.mappa / ZAR, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise HttpError(409, "This import is already running.", kod="import.fut") from None
            yield self
        finally:
            os.close(fd)

    def foglalt(self) -> bool:
        try:
            fd = os.open(self.mappa / ZAR, os.O_RDONLY | os.O_NOFOLLOW)
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


def _install(alap) -> Path | None:
    return alap.utak.get("install") if hasattr(alap, "utak") else None


def _obsidian_naplo(alap, id: str) -> Naplo:
    install = _install(alap)
    if install is None:
        raise HttpError(409, "The import cannot start: nincs_install.", kod="import.tilos", param={"akadaly": "nincs_install"})
    return Naplo(Path(install) / "imports" / id)


def _v2_naplo(cfg, id: str) -> Naplo:
    return Naplo(cfg.path("state") / "import" / id)


def obsidian_id(forras: Path, cel: Path) -> str:
    """Deterministic from the canonical source and target (the target may not exist yet: its parent's canonical path + name)."""
    f = workspace.kanonikus(forras)
    c = workspace.kanonikus(cel) if cel.exists() else os.path.join(workspace.kanonikus(cel.parent), cel.name)
    return "obs-" + hashlib.sha256(f"{unicodedata.normalize('NFC', f)}\0{unicodedata.normalize('NFC', c)}".encode()).hexdigest()[:16]


# ------------------------------------------------------------------ Obsidian: the plan


@dataclass
class _Fajl:
    ut: str
    fajta: str
    meret: int
    mtime_ns: int
    muvelet: str = "masol"


@dataclass
class _Terv:
    id: str
    forras: Path
    cel: Path
    opciok: dict
    fajlok: list[_Fajl] = field(default_factory=list)
    mappak: list[str] = field(default_factory=list)
    kihagyott: list[dict] = field(default_factory=list)
    utkozesek: list[dict] = field(default_factory=list)
    w_valtozas: dict = field(default_factory=dict)
    json: dict = field(default_factory=dict)


def _fajta(rel: str) -> str:
    if rel == ".obsidian" or rel.startswith(".obsidian/"):
        return "obsidian"
    k = mediatipus.kiterjesztes(rel)
    if k == ".md":
        return "jegyzet"
    if k == ".canvas":
        return "canvas"
    if k == ".base":
        return "bazis"
    if mediatipus.binaris_e(rel):
        return "csatolmany"
    return "egyeb"


def _bejar(forras: Path, opciok: dict) -> tuple[list[_Fajl], list[str], list[dict]]:
    """The source tree (read-only): files to copy, folders to create (empty ones too), skipped entries with a reason."""
    fajlok: list[_Fajl] = []
    mappak: list[str] = []
    kihagy: list[dict] = []

    def hibas_nev(rel: str) -> bool:
        try:
            rel.encode("utf-8")
            return False
        except UnicodeEncodeError:
            return True

    def hiba(e: OSError):
        rel = _rel(os.path.relpath(e.filename, forras)) if getattr(e, "filename", None) else "."
        kihagy.append({"ut": rel, "ok": "olvashatatlan"})

    for dp, dn, fn in os.walk(forras, onerror=hiba, followlinks=False):
        rd = os.path.relpath(dp, forras)
        rd = "" if rd == "." else _rel(rd)
        obs = rd == ".obsidian" or rd.startswith(".obsidian/")
        tart = []
        for d in sorted(dn):
            rel = f"{rd}/{d}" if rd else d
            p = os.path.join(dp, d)
            if hibas_nev(rel):
                kihagy.append({"ut": rel.encode("utf-8", "replace").decode(), "ok": "nev_ervenytelen"})
            elif os.path.islink(p):
                kihagy.append({"ut": rel, "ok": "symlink"})
            elif d == workspace.MAPPA:
                kihagy.append({"ut": rel, "ok": "manifold"})
            elif d == ".git":
                kihagy.append({"ut": rel, "ok": "git"})
            elif not rd and d == workspace.OBSIDIAN:
                if opciok["obsidian_mappa"]:
                    tart.append(d)
                else:
                    kihagy.append({"ut": rel, "ok": "opcio"})
            elif not rd and d == ".trash":
                if opciok["kuka_mappa"]:
                    tart.append(d)
                else:
                    kihagy.append({"ut": rel, "ok": "obsidian_kuka"})
            elif d.startswith(".") and not obs:
                kihagy.append({"ut": rel, "ok": "rejtett"})
            else:
                tart.append(d)
        dn[:] = tart
        mappak += [f"{rd}/{d}" if rd else d for d in tart]
        for n in sorted(fn):
            rel = f"{rd}/{n}" if rd else n
            if hibas_nev(rel):
                kihagy.append({"ut": rel.encode("utf-8", "replace").decode(), "ok": "nev_ervenytelen"})
                continue
            if n == ".DS_Store" or n.startswith("._") or n.endswith(tartos.TMP_UTOTAG):
                kihagy.append({"ut": rel, "ok": "rendszer"})
                continue
            try:
                st = os.lstat(os.path.join(dp, n))
            except OSError:
                kihagy.append({"ut": rel, "ok": "olvashatatlan"})
                continue
            if stat.S_ISLNK(st.st_mode):
                kihagy.append({"ut": rel, "ok": "symlink"})
            elif not stat.S_ISREG(st.st_mode):
                kihagy.append({"ut": rel, "ok": "specialis"})
            elif n.startswith(".") and not obs:
                kihagy.append({"ut": rel, "ok": "rejtett"})
            elif not os.access(os.path.join(dp, n), os.R_OK):
                kihagy.append({"ut": rel, "ok": "olvashatatlan"})
            else:
                fajlok.append(_Fajl(rel, _fajta(rel), st.st_size, st.st_mtime_ns))
    return fajlok, mappak, kihagy


def _nev_utkozesek(fajlok: list[_Fajl], mappak: list[str], erzekeny: bool) -> list[dict]:
    """Two source names that would land on the same destination entry (normalization- and, on a case-insensitive target,
    case-insensitive file systems)."""
    lattuk: dict[str, str] = {}
    ki = []
    for rel in [*mappak, *(f.ut for f in fajlok)]:
        k = unicodedata.normalize("NFC", rel)
        k = k if erzekeny else k.casefold()
        if k in lattuk:
            elozo = lattuk[k]
            ok = "normalizalas" if unicodedata.normalize("NFC", elozo) == unicodedata.normalize("NFC", rel) else "kis_nagy"
            ki.append({"ut": rel, "masik": elozo, "ok": ok})
        else:
            lattuk[k] = rel
    return ki


def _linkek(forras: Path, fajlok: list[_Fajl]) -> dict:
    ki = {"wikilink_db": 0, "markdown_link_db": 0, "beagyazas_db": 0, "frontmatter_db": 0, "nem_olvasott_db": 0}
    for f in fajlok:
        if f.fajta != "jegyzet":
            continue
        nyers = _olvas_opcionalis(forras / f.ut, MAX_LINK_BAJT)
        if nyers is None:
            ki["nem_olvasott_db"] += 1
            continue
        txt = nyers.decode("utf-8", "replace")
        if FM_RE.match(txt):
            ki["frontmatter_db"] += 1
        m = mask_code(txt)
        ki["wikilink_db"] += len(_WIKILINK.findall(m))
        ki["beagyazas_db"] += len(_BEAGYAZAS.findall(m))
        ki["markdown_link_db"] += len(_MD_LINK.findall(m))
    return ki


def _alap_ertek(alap, kulcs: str):
    return _keres(alap.data, kulcs)


def _beallitas_ervenyes(alap, kulcs: str, ertek) -> bool:
    if kulcs.startswith("beallitasok."):
        _, tabla, k = kulcs.split(".", 2)
        try:
            termek_beallitasok.ellenoriz({tabla: {k: ertek}})
        except HttpError:
            return False
        return True
    return not config.reteg_ellenoriz("munkater", _beagyaz(kulcs, ertek), alap.data, alap.root)


def _obsidian_lekepezes(forras: Path, alap, opciok: dict) -> tuple[dict, dict]:
    """The `.obsidian` settings → (report, workspace.toml change). Only read from the source."""
    beallitasok: list[dict] = []
    nem_atvett: list[dict] = []
    w: dict = {}
    obs = forras / workspace.OBSIDIAN
    if not opciok["obsidian_mappa"] or not obs.is_dir() or obs.is_symlink():
        ok = "opcio" if not opciok["obsidian_mappa"] else "hianyzik"
        return ({"beallitasok": [], "nem_atvett": [{"forras": ".obsidian", "ok": ok}], "mag_pluginok": [],
                 "kozossegi_pluginok": [], "tipusok_db": 0}, {})
    olvasott: dict[str, dict] = {}
    for nev in ("app", "appearance", "templates", "daily-notes", "core-plugins", "community-plugins", "types", "hotkeys"):
        adat, h = _json_fajl(obs / f"{nev}.json")
        if h == "hianyzik":
            continue
        if h:
            nem_atvett.append({"forras": f".obsidian/{nev}.json", "ok": h})
            continue
        olvasott[nev] = adat
    for nev, tabla in LEKEPEZES.items():
        adat = olvasott.get(nev)
        if not isinstance(adat, dict):
            continue
        for k, v in adat.items():
            forras_kulcs = f".obsidian/{nev}.json#{k}"
            if k in tabla:
                kulcs, atalakit = tabla[k]
                ertek = atalakit(v)
                if ertek is None or not _beallitas_ervenyes(alap, kulcs, ertek):
                    nem_atvett.append({"forras": forras_kulcs, "kulcs": kulcs, "ok": "ervenytelen"})
                    continue
                mod = "azonos" if _alap_ertek(alap, kulcs) == ertek else "ir"
                beallitasok.append({"kulcs": kulcs, "ertek": ertek, "forras": forras_kulcs, "mod": mod})
                if mod == "ir":
                    w = _melyegyesit(w, _beagyaz(kulcs, ertek))
            elif k in KOZVETLEN.get(nev, {}):
                beallitasok.append({"kulcs": KOZVETLEN[nev][k], "ertek": v, "forras": forras_kulcs, "mod": "kozvetlen"})
            elif k in MUNKATER_ALTAL.get(nev, {}):
                pass                                         # reported below from `workspace._w_mag`
            else:
                nem_atvett.append({"forras": forras_kulcs, "ok": "nem_tamogatott"})
    adat = olvasott.get("daily-notes")
    if isinstance(adat, dict):
        for k in adat:
            if k not in MUNKATER_ALTAL["daily-notes"]:
                nem_atvett.append({"forras": f".obsidian/daily-notes.json#{k}", "ok": "nem_tamogatott"})
    w_mag = workspace._w_mag(workspace._obsidian_beallitasok(forras), alap, workspace._napi_engedelyezve(forras))
    napi = olvasott.get("daily-notes")
    if isinstance(napi, dict):                          # amit a rétegellenőrzés elutasít (pl. `..`, `{}` a mappában), nem tűnhet el némán
        for k, w_kulcs in (("folder", "ut"), ("format", "ut"), ("template", "sablon")):
            if isinstance(napi.get(k), str) and napi[k].strip() and w_kulcs not in w_mag.get("naplo", {}):
                nem_atvett.append({"forras": f".obsidian/daily-notes.json#{k}", "ok": "ervenytelen"})
    for kulcs, ertek in _levelek(w_mag):
        forras_nev = ".obsidian/templates.json" if kulcs.startswith("sablon.") else ".obsidian/daily-notes.json"
        beallitasok.append({"kulcs": kulcs, "ertek": ertek, "forras": forras_nev, "mod": "munkater"})
    billentyuk: dict = {}
    if "hotkeys" in olvasott:                                # 13-palette-01: carried over per command, every skip reported
        hk = importalas_billentyuk.lekepez(olvasott["hotkeys"])
        beallitasok.extend(hk["beallitasok"])
        nem_atvett.extend(hk["nem_atvett"])
        billentyuk = hk["billentyuk"]
        if billentyuk:
            w = _melyegyesit(w, {"beallitasok": {"billentyuk": billentyuk}})
    tipusok = olvasott.get("types")
    tipusok_db = len(tipusok.get("types") or {}) if isinstance(tipusok, dict) and isinstance(tipusok.get("types"), dict) else 0
    if tipusok_db:
        beallitasok.append({"kulcs": "tulajdonsag_tipusok", "ertek": tipusok_db, "forras": ".obsidian/types.json",
                            "mod": "kozvetlen"})
    mag = olvasott.get("core-plugins")
    if isinstance(mag, list):
        mag = {x: True for x in mag if isinstance(x, str)}
    mag_pluginok = []
    if isinstance(mag, dict):
        for pid, be in sorted(mag.items()):
            if not isinstance(pid, str):
                continue
            if pid in MAG_PLUGIN:
                allapot, modul = "tamogatott", MAG_PLUGIN[pid]
            elif pid in MAG_BEEPITETT:
                allapot, modul = "beepitett", None
            else:
                allapot, modul = "nem_tamogatott", None
            mag_pluginok.append({"id": pid, "be": be is True, "allapot": allapot, "modul": modul})
    kozossegi = []
    bekapcsolt = olvasott.get("community-plugins")
    bekapcsolt = {x for x in bekapcsolt if isinstance(x, str)} if isinstance(bekapcsolt, list) else set()
    telepitett = set()
    with contextlib.suppress(OSError):
        telepitett = {e.name for e in os.scandir(obs / "plugins") if e.is_dir(follow_symlinks=False)}
    for pid in sorted(bekapcsolt | telepitett):
        kozossegi.append({"id": pid, "be": pid in bekapcsolt, "allapot": "nem_tamogatott"})
    with contextlib.suppress(OSError):
        ismert = {f"{n}.json" for n in ("app", "appearance", "templates", "daily-notes", "core-plugins", "community-plugins",
                                         "types", "hotkeys")}
        for e in sorted(os.scandir(obs), key=lambda e: e.name):
            if e.name.endswith(".json") and e.name not in ismert and e.is_file(follow_symlinks=False):
                nem_atvett.append({"forras": f".obsidian/{e.name}", "ok": "masolva_nem_olvasott"})
    return ({"beallitasok": beallitasok, "nem_atvett": nem_atvett, "mag_pluginok": mag_pluginok,
             "kozossegi_pluginok": kozossegi, "tipusok_db": tipusok_db}, w)


def _cel_tartalom(cel: Path) -> list[str]:
    try:
        return [n for n in os.listdir(cel) if n != ".DS_Store"]
    except OSError:
        return []


def _sajat_fajlok(sorok: list[dict]) -> dict[str, dict]:
    """Journal records → {relative path: last `fajl` record} (the files this import put in place)."""
    ki: dict[str, dict] = {}
    for s in sorok:
        if s.get("m") == "fajl" and isinstance(s.get("ut"), str):
            ki[s["ut"]] = s
    return ki


def _terv(forras, cel, alap, opciok=None) -> _Terv:
    opciok = _opciok(opciok)
    f = workspace._abs(forras)
    c = workspace._abs(cel)
    akadaly: list[str] = []
    figy: list[str] = []
    if not f.is_dir() or f.is_symlink():
        akadaly.append("forras_nem_mappa")
    elif not os.access(f, os.R_OK | os.X_OK):
        akadaly.append("forras_nem_olvashato")
    if workspace._alatt(c, f):
        akadaly.append("cel_a_forrasban")
    if workspace._alatt(f, c):
        akadaly.append("forras_a_celban")
    id = obsidian_id(f, c)
    naplo = None
    allapot = None
    if _install(alap) is None:
        akadaly.append("nincs_install")
    else:
        naplo = _obsidian_naplo(alap, id)
        allapot = naplo.allapot()
        if naplo.foglalt():
            akadaly.append("import_fut")
    t = _Terv(id=id, forras=f, cel=c, opciok=opciok)
    if allapot and allapot.get("allapot") == "kesz":
        t.json = {"verzio": VERZIO, "id": id, "fajta": "obsidian", "forras": str(f), "cel": str(c), "eredmeny": "kesz",
                  "akadaly": [], "figyelmeztetes": [], "allapot": "kesz", "opciok": allapot.get("opciok") or opciok,
                  "osszegzes": allapot.get("eredmeny"), "terv_hash": allapot.get("terv_hash")}
        return t
    folytat = bool(allapot and allapot.get("allapot") in ("fut", "hiba", "megszakitva"))

    if "forras_nem_mappa" not in akadaly and "forras_nem_olvashato" not in akadaly:
        t.fajlok, t.mappak, t.kihagyott = _bejar(f, opciok)
    letezik = c.is_dir()
    if c.exists() and not letezik:
        akadaly.append("nem_mappa")
    felm = workspace.felmer(c, alap, uj=not c.exists())
    for a in felm.akadaly:
        if a not in akadaly:
            akadaly.append(a)
    for w_ in felm.figyelmeztetes:
        if w_ not in figy:
            figy.append(w_)
    if letezik and not folytat:
        if felm.meglevo_id or (c / workspace.MAPPA).exists():
            akadaly.append("cel_munkater")
        elif _cel_tartalom(c):
            akadaly.append("cel_nem_ures")
    if (f / workspace.MAPPA / workspace.WS_TOML).is_file():
        figy.append("forras_munkater")
    t.utkozesek = _nev_utkozesek(t.fajlok, t.mappak, felm.kis_nagy_erzekeny)
    if t.utkozesek:
        akadaly.append("nev_utkozes")
    if letezik:
        for fj in t.fajlok:
            p = c / fj.ut
            try:
                st = os.lstat(p)
            except OSError:
                continue
            try:
                azonos = stat.S_ISREG(st.st_mode) and st.st_size == fj.meret and _sha_fajl(p)[0] == _sha_fajl(f / fj.ut)[0]
            except OSError:
                azonos = False
            fj.muvelet = "megvan" if azonos else "utkozes"
            if fj.muvelet == "utkozes":
                t.utkozesek.append({"ut": fj.ut, "ok": "cel_elter"})
        if any(fj.muvelet == "utkozes" for fj in t.fajlok) and "fajl_utkozes" not in akadaly:
            akadaly.append("fajl_utkozes")
    obsidian, t.w_valtozas = _obsidian_lekepezes(f, alap, opciok) if f.is_dir() else ({}, {})
    if obsidian.get("kozossegi_pluginok") or any(p["allapot"] == "nem_tamogatott" for p in obsidian.get("mag_pluginok", ())):
        figy.append("nem_tamogatott_pluginok")
    if t.kihagyott:
        figy.append("kihagyott_elemek")
    masolando = [fj for fj in t.fajlok if fj.muvelet == "masol"]
    bajt = sum(fj.meret for fj in masolando)
    szabad = felm.szabad_bajt
    if bajt > szabad:
        ugyanott = False
        with contextlib.suppress(OSError):
            ugyanott = os.stat(f).st_dev == workspace._eszkoz(c) and felm.fajlrendszer == "apfs"
        if ugyanott:                                     # APFS clones need no extra space
            if "keves_hely" not in figy:
                figy.append("keves_hely")
        else:
            akadaly.append("keves_hely")
    osszesites = {"fajl_db": len(t.fajlok), "bajt": sum(fj.meret for fj in t.fajlok), "mappa_db": len(t.mappak),
                  "kihagyott_db": len(t.kihagyott), "masolando_db": len(masolando),
                  "megvan_db": sum(fj.muvelet == "megvan" for fj in t.fajlok)}
    for fajta, kulcs in (("jegyzet", "md_db"), ("canvas", "canvas_db"), ("bazis", "base_db"), ("csatolmany", "csatolmany_db"),
                         ("obsidian", "obsidian_db"), ("egyeb", "egyeb_db")):
        osszesites[kulcs] = sum(fj.fajta == fajta for fj in t.fajlok)
    linkek = _linkek(f, t.fajlok) if f.is_dir() else {}
    linkek["beallitas"] = {"wikilinkek": _keres(_melyegyesit(alap.data, t.w_valtozas), "beallitasok.fajlok.wikilinkek"),
                           "link_formatum": _keres(_melyegyesit(alap.data, t.w_valtozas), "beallitasok.fajlok.link_formatum")}
    letre = list(felm.letrehozando)
    if "obsidian" in letre and opciok["obsidian_mappa"] and any(fj.fajta == "obsidian" for fj in t.fajlok):
        letre.remove("obsidian")
    hash_adat = {"id": id, "opciok": opciok, "fajlok": [(fj.ut, fj.meret, fj.mtime_ns, fj.muvelet) for fj in t.fajlok],
                 "mappak": t.mappak, "kihagyott": t.kihagyott, "w": t.w_valtozas,
                 "akadaly": [a for a in akadaly if a != "import_fut"]}
    eredmeny = "tilos" if akadaly else ("figyelmeztet" if figy else "mehet")
    t.json = {
        "verzio": VERZIO, "id": id, "fajta": "obsidian", "forras": str(f), "cel": str(c), "eredmeny": eredmeny,
        "akadaly": akadaly, "figyelmeztetes": figy, "allapot": (allapot or {}).get("allapot"), "opciok": opciok,
        "osszesites": osszesites,
        "fajlok": [{"ut": fj.ut, "fajta": fj.fajta, "meret": fj.meret, "muvelet": fj.muvelet} for fj in t.fajlok[:MAX_LISTA]],
        "fajlok_csonkitva": len(t.fajlok) > MAX_LISTA,
        "kihagyott": t.kihagyott[:MAX_LISTA], "utkozesek": t.utkozesek[:MAX_LISTA], "linkek": linkek, "obsidian": obsidian,
        "atiras": [], "letrehozando": letre, "szabad_bajt": szabad, "terv_hash": _terv_hash(hash_adat),
    }
    return t


def obsidian_elonezet(forras, cel, alap, opciok=None) -> dict:
    """The read-only preview of an Obsidian import (module docstring). Writes nothing — neither the source nor the target nor
    the journal."""
    return _terv(forras, cel, alap, opciok).json


# ------------------------------------------------------------------ Obsidian: the run


class _ForrasValtozott(Exception):
    pass


class Megszakitva(Exception):
    """The user cancelled the running import; raised only at a file boundary (nothing half-done is left behind)."""
    kod = "import.megszakitva"

    def __init__(self, kesz_db: int = 0, osszes_db: int = 0):
        super().__init__("The import was cancelled. Run the import again to continue, or undo it.")
        self.kesz_db = kesz_db
        self.osszes_db = osszes_db


def _idok_masol(tmp: Path, st: os.stat_result) -> None:
    """mtime/atime of the source, and its birth time (pulling mtime back first moves the birth time back, see `tartos`)."""
    with contextlib.suppress(OSError):
        szuletes = getattr(st, "st_birthtime", None)
        if szuletes is not None and int(szuletes * 1e9) < st.st_mtime_ns:
            os.utime(tmp, ns=(st.st_atime_ns, int(szuletes * 1e9)), follow_symlinks=False)
        os.utime(tmp, ns=(st.st_atime_ns, st.st_mtime_ns), follow_symlinks=False)


def _folyam_masol(fd: int, tmp: Path, st: os.stat_result) -> tuple[str, int]:
    h = hashlib.sha256()
    n = 0
    os.lseek(fd, 0, os.SEEK_SET)
    cfd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, stat.S_IMODE(st.st_mode) | 0o600)
    try:
        while True:
            darab = os.read(fd, 1 << 20)
            if not darab:
                break
            h.update(darab)
            n += len(darab)
            mv = memoryview(darab)
            while mv:
                k = os.write(cfd, mv)
                mv = mv[k:]
        os.fsync(cfd)
    finally:
        os.close(cfd)
    _idok_masol(tmp, st)
    return h.hexdigest(), n


def _mappa_biztosit(cel: Path, rel: str, naplo: Naplo) -> None:
    """The folder `cel/rel`, component by component; an existing component must be a real folder (never a link)."""
    p = cel
    reszek = [r for r in rel.split("/") if r]
    for i, r in enumerate(reszek):
        p = p / r
        try:
            st = os.lstat(p)
        except FileNotFoundError:
            naplo.sor({"m": "mappa", "ut": "/".join(reszek[:i + 1])})
            os.mkdir(p)
            continue
        if not stat.S_ISDIR(st.st_mode):
            raise _utkozes("/".join(reszek[:i + 1]))


def _fajl_masol(forras: Path, cel: Path, fj: _Fajl, naplo: Naplo, sajat: dict) -> str:
    """One file → `"masolt"` | `"megvan"`. Never overwrites; a destination with other bytes is a conflict."""
    src, dst = forras / fj.ut, cel / fj.ut
    for _ in range(3):
        fd = os.open(src, os.O_RDONLY | os.O_NOFOLLOW)
        tmp: Path | None = None
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise HttpError(409, f"A source file kept changing during the import: {fj.ut}. Try again.",
                                kod="import.forras_valtozik", param={"ut": fj.ut})
            try:
                dst_st = os.lstat(dst)
            except FileNotFoundError:
                dst_st = None
            if dst_st is not None:
                if stat.S_ISREG(dst_st.st_mode) and dst_st.st_size == st.st_size:
                    d_sha = _sha_fajl(dst)[0]
                    os.lseek(fd, 0, os.SEEK_SET)
                    h = hashlib.sha256()
                    while darab := os.read(fd, 1 << 20):
                        h.update(darab)
                    if d_sha == h.hexdigest():
                        if fj.ut not in sajat:
                            naplo.sor({"m": "megvan", "ut": fj.ut, "sha256": d_sha})
                        return "megvan"
                raise _utkozes(fj.ut)
            tmp = tartos.tmp_ut(dst)
            naplo.sor({"m": "tmp", "ut": _rel(os.path.relpath(tmp, cel))})
            klon = False
            try:
                tartos.klon_excl(src, tmp)
                klon = True
            except OSError as e:
                if e.errno not in (errno.EXDEV, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EINVAL, errno.ENOSYS, errno.EPERM):
                    raise
            if klon:
                sha, meret = _sha_fajl(tmp)
                cfd = os.open(tmp, os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    os.fsync(cfd)
                finally:
                    os.close(cfd)
            else:
                sha, meret = _folyam_masol(fd, tmp, st)
            st2 = os.fstat(fd)
            if meret != st.st_size or (st2.st_size, st2.st_mtime_ns) != (st.st_size, st.st_mtime_ns):
                raise _ForrasValtozott(fj.ut)
            naplo.sor({"m": "fajl", "ut": fj.ut, "sha256": sha, "meret": meret})   # BEFORE it is in place: the undo knows it
            tartos.rename_excl(tmp, dst)
            tmp = None
            return "masolt"
        except _ForrasValtozott:
            continue
        except FileExistsError:
            raise _utkozes(fj.ut) from None
        finally:
            if tmp is not None:
                with contextlib.suppress(FileNotFoundError):
                    os.remove(tmp)                       # our own temporary file
            os.close(fd)
    raise HttpError(409, f"A source file kept changing during the import: {fj.ut}. Try again.", kod="import.forras_valtozik",
                    param={"ut": fj.ut})


def _tmp_takarit(cel: Path, sorok: list[dict]) -> None:
    for s in sorok:
        if s.get("m") == "tmp" and isinstance(s.get("ut"), str) and s["ut"].endswith(tartos.TMP_UTOTAG):
            p = cel / s["ut"]
            with contextlib.suppress(OSError):
                if stat.S_ISREG(os.lstat(p).st_mode):
                    os.remove(p)                         # a temporary file of an interrupted run of this import


def _w_ir(cfg, valtozas: dict, *, elvart_sha: str | None = None, naplozo=None) -> tuple[bytes, bytes]:
    """A workspace-layer change into `workspace.toml` (the F5 settings writer's lock, identity and link checks; the previous file
    as `workspace.toml.elozo`). `naplozo(elotte, utana)` runs under the lock BEFORE the write (the journal's intent record).
    → (previous bytes, new bytes); equal when there was nothing to change."""
    p, reteg = termek_beallitasok.cel(cfg)
    if reteg != "munkater":
        raise HttpError(409, "The import cannot start: hordozhato_elrendezes.", kod="import.tilos",
                        param={"akadaly": "hordozhato_elrendezes"})
    with termek_beallitasok._zar(p):
        termek_beallitasok.cel(cfg)
        nyers = termek_beallitasok._nyers(p)
        if elvart_sha is not None and _sha(nyers) != elvart_sha:
            raise _terv_valtozott()
        regi = termek_beallitasok._adat(nyers)
        rossz = config.reteg_ellenoriz("munkater", valtozas, cfg.data, cfg.root)
        if rossz:
            raise HttpError(400, f"This setting is not valid: {rossz[0][0]}.", kod="import.beallitas_hibas",
                            param={"kulcs": rossz[0][0]})
        uj = termek_beallitasok.egyesit(regi, valtozas)
        szoveg = termek_beallitasok.toml_ir(uj).encode("utf-8")
        tomllib.loads(szoveg.decode("utf-8"))
        if workspace.toml_azonosito_szovegbol(szoveg.decode("utf-8")) != cfg.workspace_id:
            raise HttpError(409, "The workspace changed on disk. Reopen it before importing.", kod="import.munkater_csere")
        if termek_beallitasok.toml_ir(regi).encode("utf-8") == szoveg:
            return nyers, nyers
        if naplozo is not None:
            naplozo(nyers, szoveg)
        workspace._atomi_ir_nofollow(p.parent, "workspace.toml.elozo", nyers)
        workspace._atomi_ir_nofollow(p.parent, p.name, szoveg)
        return nyers, szoveg


def _w_valtozas_szukseges(tcfg, w: dict) -> dict:
    """Only what differs from the new workspace's effective value."""
    ki: dict = {}
    for kulcs, ertek in _levelek(w):
        if kulcs.startswith(_BILLENTYU_TABLA):          # hotkey ids contain dots: ONE key under the table, not a path
            azonosito = kulcs[len(_BILLENTYU_TABLA):]
            if (tcfg.data.get("beallitasok", {}).get("billentyuk", {}) or {}).get(azonosito) != ertek:
                ki = _melyegyesit(ki, {"beallitasok": {"billentyuk": {azonosito: ertek}}})
        elif _keres(tcfg.data, kulcs) != ertek:
            ki = _melyegyesit(ki, _beagyaz(kulcs, ertek))
    return ki


def obsidian_importal(forras, cel, alap, opciok=None, *, terv_hash: str | None = None, haladas=lambda d: None,
                      megszakit: threading.Event | None = None) -> dict:
    """The import (module docstring). Resumes an interrupted run; after a finished one it writes nothing (`ismetles: true`).
    `terv_hash`: the preview's hash — when given and different, 409 `import.terv_valtozott` and nothing is written.
    `megszakit`: when set, the run stops at the next file boundary and raises `Megszakitva` (state `megszakitva`, resumable)."""
    _opciok(opciok)
    naplo = _obsidian_naplo(alap, obsidian_id(workspace._abs(forras), workspace._abs(cel)))
    with naplo.zar():
        t = _terv(forras, cel, alap, opciok)               # again, under the lock
        if t.json["eredmeny"] == "kesz":
            return {**(naplo.allapot() or {}).get("eredmeny", {}), "id": t.id, "allapot": "kesz", "ismetles": True}
        akadaly = [a for a in t.json["akadaly"] if a != "import_fut"]
        if terv_hash is not None and terv_hash != t.json["terv_hash"]:
            raise _terv_valtozott()
        if "fajl_utkozes" in akadaly:
            elso = next(u["ut"] for u in t.utkozesek if u.get("ok") == "cel_elter")
            raise _utkozes(elso)
        if akadaly:
            raise _tilos(akadaly)
        elozo = naplo.allapot() or {}
        if elozo.get("allapot") in ("visszaforditva", "reszben_visszaforditva"):
            naplo.archival()
            elozo = {}
        folytat = elozo.get("allapot") in ("fut", "hiba", "megszakitva")
        sorok = naplo.sorok() if folytat else []
        cel_letrehozva = bool(elozo.get("cel_letrehozva")) if folytat else not t.cel.exists()
        naplo.fajl_ir(TERV, json.dumps({"opciok": t.opciok, "fajlok": [fj.__dict__ for fj in t.fajlok],
                                        "mappak": t.mappak, "kihagyott": t.kihagyott, "w": t.w_valtozas},
                                       ensure_ascii=False).encode("utf-8"))
        naplo.allapot_ir(id=t.id, fajta="obsidian", allapot="fut", forras=str(t.forras), cel=str(t.cel), opciok=t.opciok,
                         terv_hash=t.json["terv_hash"], cel_letrehozva=cel_letrehozva,
                         kezdve=elozo.get("kezdve") if folytat else _most(), hiba=None, eredmeny=None,
                         munkater_id=elozo.get("munkater_id") if folytat else None,
                         munkater_letrehozva=bool(elozo.get("munkater_letrehozva")) if folytat else False)
        naplo.sor({"m": "kezd", "folytatas": folytat})
        try:
            return _obsidian_fut(t, naplo, alap, sorok, cel_letrehozva, haladas, megszakit)
        except Megszakitva as e:
            naplo.sor({"m": "megszakitva", "kesz_db": e.kesz_db, "osszes_db": e.osszes_db})
            naplo.allapot_ir(allapot="megszakitva", hiba=None)
            raise
        except BaseException as e:
            kod = getattr(e, "kod", None) or "import.masolas_hiba"
            param = getattr(e, "param", None) or {}
            naplo.allapot_ir(allapot="hiba", hiba={"kod": kod, "uzenet": str(e), "param": param})
            naplo.sor({"m": "hiba", "kod": kod})
            if isinstance(e, (HttpError, ConfigError)) or not isinstance(e, Exception):
                raise
            raise HttpError(503, f"The import stopped: {e}. Run the import again to continue, or undo it.",
                            kod="import.masolas_hiba", param={"ok": str(e)}) from e


def _megszakitva(megszakit: threading.Event | None, kesz_db: int, osszes_db: int) -> None:
    if megszakit is not None and megszakit.is_set():
        raise Megszakitva(kesz_db, osszes_db)


def _obsidian_fut(t: _Terv, naplo: Naplo, alap, sorok, cel_letrehozva, haladas, megszakit=None) -> dict:
    if not t.cel.exists():
        t.cel.mkdir()
    _tmp_takarit(t.cel, sorok)
    sajat = _sajat_fajlok(sorok)
    for d in t.mappak:
        _mappa_biztosit(t.cel, d, naplo)
    osszes = len(t.fajlok)
    masolt = megvolt = bajt = 0
    utolso = 0.0
    mappak_erintett: set[str] = set()
    for i, fj in enumerate(t.fajlok, 1):
        _megszakitva(megszakit, i - 1, osszes)           # only BETWEEN files: the previous one is complete and journaled
        mappa = fj.ut.rsplit("/", 1)[0] if "/" in fj.ut else ""
        if mappa:
            _mappa_biztosit(t.cel, mappa, naplo)
        r = _fajl_masol(t.forras, t.cel, fj, naplo, sajat)
        if r == "masolt":
            masolt += 1
            bajt += fj.meret
            mappak_erintett.add(mappa)
        else:
            megvolt += 1
        most = time.monotonic()
        if most - utolso >= _HALADAS_MP or i == osszes:
            utolso = most
            haladas({"lepes": "masolas", "kesz_db": i, "osszes_db": osszes, "bajt": bajt})
    for m in sorted(mappak_erintett | {""}):
        with contextlib.suppress(OSError):
            tartos.fsync_mappa(t.cel / m if m else t.cel)

    # the workspace (idempotent: a finished `letrehoz` returns the existing ID)
    _megszakitva(megszakit, osszes, osszes)
    haladas({"lepes": "munkater"})
    nev = t.opciok.get("nev") or t.cel.name
    if not (t.cel / workspace.MAPPA).exists() and not os.path.islink(t.cel / workspace.MAPPA):
        naplo.sor({"m": "munkater_kezd"})                # the target was new or empty: any `.manifold` there is ours
        naplo.allapot_ir(munkater_letrehozva=True)
    ws = workspace.letrehoz(t.cel, alap, nev=nev, haladas=lambda d: haladas({"lepes": "munkater", "reszlet": d.get("lepes")}))
    elozo = naplo.allapot() or {}
    letrehozva = bool(elozo.get("munkater_letrehozva")) or bool(ws.get("uj"))
    naplo.sor({"m": "munkater", "id": ws["id"], "uj": bool(ws.get("uj"))})
    naplo.allapot_ir(munkater_id=ws["id"], munkater_letrehozva=letrehozva)

    # the mapped `.obsidian` settings
    haladas({"lepes": "beallitasok"})
    tcfg = workspace.munkater_cfg(alap, t.cel, ws["id"])
    w = _w_valtozas_szukseges(tcfg, t.w_valtozas)
    irt: list[str] = []
    if w:
        def naplozo(elotte, utana):
            naplo.sor({"m": "beallitas", "fajl": workspace.WS_TOML, "elotte_sha": _sha(elotte), "utana_sha": _sha(utana)})
        _w_ir(tcfg, w, naplozo=naplozo)
        irt = [k for k, _ in _levelek(w)]

    # the source must still be what was copied (it was never written by us; a concurrent edit by the user is reported)
    valtozott = []
    for fj in t.fajlok:
        try:
            st = os.lstat(t.forras / fj.ut)
        except OSError:
            valtozott.append(fj.ut)
            continue
        if (st.st_size, st.st_mtime_ns) != (fj.meret, fj.mtime_ns):
            valtozott.append(fj.ut)
    with contextlib.suppress(OSError):
        fd = os.open(t.cel, os.O_RDONLY)
        try:
            tartos.fsync_teljes(fd)
        finally:
            os.close(fd)
    eredmeny = {"id": t.id, "allapot": "kesz", "cel": str(t.cel), "munkater_id": ws["id"], "masolt_db": masolt,
                "megvolt_db": megvolt, "bajt": bajt, "kihagyott_db": len(t.kihagyott), "beallitasok_irva": irt,
                "forras_valtozott": valtozott[:MAX_LISTA], "naplo": str(naplo.mappa), "ismetles": False}
    naplo.sor({"m": "kesz", "masolt_db": masolt, "megvolt_db": megvolt})
    naplo.allapot_ir(allapot="kesz", eredmeny=eredmeny, hiba=None)
    return eredmeny


# ------------------------------------------------------------------ Obsidian: undo


def _obsidian_visszafordit(id: str, alap, kuka) -> dict:
    naplo = _obsidian_naplo(alap, id)
    with naplo.zar():
        a = naplo.allapot()
        if not a:
            raise HttpError(404, "There is no such import.", kod="import.nincs")
        if a.get("allapot") == "visszaforditva":
            return {"id": id, "allapot": "visszaforditva", "kukaba": [], "megtartva": [], "ismetles": True}
        cel = Path(a["cel"])
        sorok = naplo.sorok()
        sajat = _sajat_fajlok(sorok)
        sajat_mappak = [s["ut"] for s in sorok if s.get("m") == "mappa" and isinstance(s.get("ut"), str)]
        kukaba: list[str] = []
        megtartva: list[dict] = []
        if cel.is_symlink():
            raise HttpError(409, "The import cannot be undone: the destination is a symbolic link.",
                            kod="import.visszafordit_utkozes", param={"ut": str(cel)})
        # 1. the workspace data (refused while a core runs on it)
        if a.get("munkater_letrehozva") and cel.is_dir():
            try:
                r = workspace.eltavolit(cel, alap, kuka)
            except ConfigError as e:
                if getattr(e, "kod", None) == "munkater_hasznalatban":
                    raise HttpError(409, "Close the imported workspace before undoing the import.",
                                    kod="import.munkater_hasznalatban") from e
                raise
            kukaba += r.get("kukaba", [])
        naplo.allapot_ir(allapot="visszafordit_fut")
        _tmp_takarit(cel, sorok)
        if not cel.is_dir():
            eredmeny = {"id": id, "allapot": "visszaforditva", "kukaba": kukaba, "megtartva": []}
            naplo.allapot_ir(allapot="visszaforditva", visszaforditas=eredmeny)
            return eredmeny
        # 2. what is in the target now
        torolheto: list[str] = []
        egyeb = False
        for dp, dn, fn in os.walk(cel):
            rd = os.path.relpath(dp, cel)
            rd = "" if rd == "." else _rel(rd)
            # `.manifold` is the workspace's (handled by `workspace.eltavolit` above), never an imported file
            dn[:] = [d for d in rejtett.metsz_munkater(dn) if not (not rd and d.startswith(VISSZAVONAS_ELOTAG))]
            for d in list(dn):
                if os.path.islink(os.path.join(dp, d)):
                    megtartva.append({"ut": f"{rd}/{d}" if rd else d, "ok": "idegen"})
                    egyeb = True
                    dn.remove(d)
            for n in fn:
                rel = f"{rd}/{n}" if rd else n
                p = Path(dp) / n
                if n == ".DS_Store":
                    continue
                rec = sajat.get(rel)
                try:
                    st = os.lstat(p)
                except OSError:
                    continue
                if rec and stat.S_ISREG(st.st_mode) and st.st_size == rec.get("meret") and _sha_fajl(p)[0] == rec.get("sha256"):
                    torolheto.append(rel)
                else:
                    megtartva.append({"ut": rel, "ok": "modositott" if rec else "idegen"})
                    egyeb = True
        regi_tartok = [cel / n for n in os.listdir(cel) if n.startswith(VISSZAVONAS_ELOTAG)]
        # 3. into the Trash: the whole folder when this import created it and nothing else is in it
        if a.get("cel_letrehozva") and not egyeb:
            kuka(cel)
            kukaba.append(str(cel))
        else:
            for tarto in regi_tartok:                    # a holder left by an interrupted undo
                kuka(tarto)
                kukaba.append(str(tarto))
            if torolheto:
                tarto = cel / f"{VISSZAVONAS_ELOTAG}{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"
                tarto.mkdir()
                naplo.sor({"m": "visszavonas_tarto", "ut": tarto.name})
                for rel in torolheto:
                    cel_ut = tarto / rel
                    cel_ut.parent.mkdir(parents=True, exist_ok=True)
                    os.rename(cel / rel, cel_ut)
                kuka(tarto)
                kukaba.append(str(tarto))
            for rel in sorted(set(sajat_mappak), key=lambda x: x.count("/"), reverse=True):
                with contextlib.suppress(OSError):
                    os.rmdir(cel / rel)                  # only an empty folder this import created
        allapot = "reszben_visszaforditva" if megtartva else "visszaforditva"
        eredmeny = {"id": id, "allapot": allapot, "kukaba": kukaba, "megtartva": megtartva[:MAX_LISTA]}
        naplo.sor({"m": "visszaforditva", "allapot": allapot, "kukaba_db": len(kukaba), "megtartva_db": len(megtartva)})
        naplo.allapot_ir(allapot=allapot, visszaforditas=eredmeny)
        return eredmeny


# ------------------------------------------------------------------ v2 import


def _friss_cfg(cfg):
    """The open workspace's configuration as it is on disk now (not the core's loaded copy)."""
    return workspace.munkater_cfg(cfg, cfg.path("vault"), cfg.workspace_id)


def v2_id(forras: Path, cfg) -> str:
    return "v2-" + hashlib.sha256(f"{workspace.kanonikus(forras)}\0{cfg.workspace_id}".encode()).hexdigest()[:16]


def _v2_terv(forras, cfg) -> dict:
    f = _abszolut(forras, "forras") if not isinstance(forras, Path) else workspace._abs(forras)
    akadaly: list[str] = []
    figy: list[str] = []
    if cfg.elrendezes != "termek":
        akadaly.append("hordozhato_elrendezes")
    if not cfg.workspace_id:
        akadaly.append("nincs_munkater")
    v2_toml = f / "config" / "os.toml"
    v2: dict = {}
    if not v2_toml.is_file() or v2_toml.is_symlink():
        akadaly.append("v2_nincs_konfig")
    else:
        try:
            v2 = config.toml_megbizhatatlan(v2_toml, "workspace_toml_hibas")
        except (ConfigError, OSError):
            akadaly.append("v2_toml_hibas")
    id = v2_id(f, cfg) if cfg.workspace_id else "v2-" + "0" * 16
    if akadaly:
        return {"verzio": VERZIO, "id": id, "fajta": "v2", "forras": str(f), "eredmeny": "tilos", "akadaly": akadaly,
                "figyelmeztetes": figy, "kulcsok": [], "utkozesek": [], "nem_atvett": [], "sema": None, "valtozas_db": 0,
                "terv_hash": None, "ujrainditas": False}
    fris = _friss_cfg(cfg)
    ws = fris.path("workspace")
    if workspace._alatt(ws, fris.root):
        akadaly.append("kodfaban")
    ws_nyers = _olvas_opcionalis(ws / workspace.WS_TOML, config.MAX_TOML_BAJT) or b""
    kulcsok: list[dict] = []
    utkozesek: list[dict] = []
    nem_atvett: list[dict] = []
    tiltott_db = azonos_db = 0
    for kulcs, ertek in _levelek(v2):
        if kulcs.startswith(V2_KIHAGY) or kulcs.startswith("_"):
            continue
        rossz = config.reteg_ellenoriz("munkater", _beagyaz(kulcs, ertek), fris.data, fris.root)
        if rossz:
            if rossz[0][1] == "reteg_tiltott":
                tiltott_db += 1                          # machine/model/install keys: not a workspace convention
            else:
                nem_atvett.append({"kulcs": kulcs, "ok": rossz[0][1]})
            continue
        jelen = _keres(fris.data, kulcs)
        if jelen == ertek:
            azonos_db += 1
            continue
        if fris.forras(*kulcs.split(".")) == "munkater":
            utkozesek.append({"kulcs": kulcs, "jelen": jelen, "v2": ertek})
            continue
        kulcsok.append({"kulcs": kulcs, "jelen": jelen, "uj": ertek})
    # the schema
    sema = None
    v2_sema = f / "config" / "vault-sema.json"
    if v2_sema.is_file() and not v2_sema.is_symlink():
        adat, h = _json_fajl(v2_sema)
        hibak = [h] if h else kiserok.sema_hibak(adat)
        cel_sema = Path(fris.expand(str(fris.section("sema").get("vault") or "{workspace}/schema.json")))
        if hibak:
            nem_atvett.append({"kulcs": "schema.json", "ok": "sema_hibas"})
        elif not workspace._alatt(cel_sema, ws) or workspace._alatt(cel_sema, fris.root):
            akadaly.append("sema_cel_kivul")
        else:
            uj = (json.dumps(adat, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            jelen_b = _olvas_opcionalis(cel_sema, kiserok.SEMA_MAX_BAJT + 1)
            if jelen_b is not None:
                try:
                    jelen_adat = json.loads(jelen_b.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    jelen_adat = None
            if jelen_b is None and cel_sema.exists():
                utkozesek.append({"kulcs": "schema.json", "ok": "olvashatatlan"})
            elif jelen_b is not None and jelen_adat == adat:
                sema = {"cel": str(cel_sema), "muvelet": "azonos"}
            elif jelen_b is not None:
                utkozesek.append({"kulcs": "schema.json", "ok": "sema_elter"})
                sema = {"cel": str(cel_sema), "muvelet": "utkozes"}
            else:
                sema = {"cel": str(cel_sema), "muvelet": "ir", "sha256": _sha(uj), "bajt": uj.decode("utf-8")}
            if sema and sema["muvelet"] == "ir" and _keres(fris.data, "sema.mod") != "szigoru" \
                    and not any(k["kulcs"] == "sema.mod" for k in kulcsok):
                if fris.forras("sema", "mod") == "munkater":
                    utkozesek.append({"kulcs": "sema.mod", "jelen": _keres(fris.data, "sema.mod"), "v2": "szigoru"})
                else:
                    kulcsok.append({"kulcs": "sema.mod", "jelen": _keres(fris.data, "sema.mod"), "uj": "szigoru"})
    if utkozesek:
        figy.append("utkozes_kihagyva")
    valtozas_db = len(kulcsok) + (1 if sema and sema["muvelet"] == "ir" else 0)
    sema_ki = None if sema is None else {k: v for k, v in sema.items() if k != "bajt"}
    hash_adat = {"id": id, "kulcsok": kulcsok, "sema": sema_ki, "ws": _sha(ws_nyers), "akadaly": akadaly}
    return {"verzio": VERZIO, "id": id, "fajta": "v2", "forras": str(f),
            "eredmeny": "tilos" if akadaly else ("figyelmeztet" if figy else "mehet"), "akadaly": akadaly,
            "figyelmeztetes": figy, "kulcsok": kulcsok, "utkozesek": utkozesek, "nem_atvett": nem_atvett,
            "nem_munkater_kulcs_db": tiltott_db, "azonos_db": azonos_db, "sema": sema_ki, "valtozas_db": valtozas_db,
            "ujrainditas": valtozas_db > 0, "terv_hash": _terv_hash(hash_adat),
            "_sema_bajt": sema.get("bajt") if sema else None, "_ws_sha": _sha(ws_nyers)}


def v2_elonezet(forras, cfg) -> dict:
    """The read-only preview of a v2 import into the open workspace (module docstring)."""
    return {k: v for k, v in _v2_terv(forras, cfg).items() if not k.startswith("_")}


def v2_importal(forras, cfg, *, terv_hash: str | None = None) -> dict:
    t = _v2_terv(forras, cfg)
    if t["akadaly"]:
        raise _tilos(t["akadaly"])
    if terv_hash is not None and terv_hash != t["terv_hash"]:
        raise _terv_valtozott()
    naplo = _v2_naplo(cfg, t["id"])
    with naplo.zar():
        t = _v2_terv(forras, cfg)
        if terv_hash is not None and terv_hash != t["terv_hash"]:
            raise _terv_valtozott()
        if t["valtozas_db"] == 0:
            a = naplo.allapot() or {}
            return {"id": t["id"], "allapot": a.get("allapot") or "kesz", "valtozas": 0, "ujrainditas": False,
                    "ismetles": True}
        elozo = naplo.allapot() or {}
        if elozo:
            naplo.archival()
        fris = _friss_cfg(cfg)
        ws = fris.path("workspace")
        naplo.allapot_ir(id=t["id"], fajta="v2", allapot="fut", forras=t["forras"], cel=str(ws), kezdve=_most(),
                         terv_hash=t["terv_hash"], hiba=None, eredmeny=None, visszaforditas=None)
        try:
            valtozas: dict = {}
            for k in t["kulcsok"]:
                valtozas = _melyegyesit(valtozas, _beagyaz(k["kulcs"], k["uj"]))
            irt = []
            if valtozas:
                def naplozo(elotte, utana):
                    naplo.fajl_ir("elozo-workspace.toml", elotte)
                    naplo.sor({"m": "ir", "fajl": workspace.WS_TOML, "elotte_sha": _sha(elotte), "utana_sha": _sha(utana),
                               "elozo": "elozo-workspace.toml"})
                _w_ir(fris, valtozas, elvart_sha=t["_ws_sha"], naplozo=naplozo)
                irt.append(workspace.WS_TOML)
            if t["sema"] and t["sema"]["muvelet"] == "ir":
                cel_sema = Path(t["sema"]["cel"])
                uj = t["_sema_bajt"].encode("utf-8")
                workspace.munkater_mappa_ellenoriz(fris.path("vault"), ws)
                jelen = _olvas_opcionalis(cel_sema, kiserok.SEMA_MAX_BAJT + 1)
                if jelen is not None or cel_sema.exists():
                    raise _terv_valtozott()
                naplo.sor({"m": "ir", "fajl": cel_sema.name, "elotte_sha": None, "utana_sha": _sha(uj), "elozo": None})
                workspace._atomi_ir_nofollow(cel_sema.parent, cel_sema.name, uj)
                irt.append(cel_sema.name)
            eredmeny = {"id": t["id"], "allapot": "kesz", "valtozas": t["valtozas_db"], "irt": irt,
                        "kulcsok": [k["kulcs"] for k in t["kulcsok"]], "ujrainditas": True, "ismetles": False,
                        "naplo": str(naplo.mappa)}
            naplo.sor({"m": "kesz"})
            naplo.allapot_ir(allapot="kesz", eredmeny=eredmeny)
            return eredmeny
        except BaseException as e:
            naplo.allapot_ir(allapot="hiba", hiba={"kod": getattr(e, "kod", None) or "import.masolas_hiba", "uzenet": str(e),
                                                  "param": getattr(e, "param", None) or {}})
            raise


def _v2_visszafordit(id: str, cfg) -> dict:
    naplo = _v2_naplo(cfg, id)
    with naplo.zar():
        a = naplo.allapot()
        if not a:
            raise HttpError(404, "There is no such import.", kod="import.nincs")
        if a.get("allapot") == "visszaforditva":
            return {"id": id, "allapot": "visszaforditva", "visszaallitva": [], "kukaba": [], "megtartva": [], "ismetles": True}
        fris = _friss_cfg(cfg)
        ws = fris.path("workspace")
        workspace.munkater_mappa_ellenoriz(fris.path("vault"), ws)
        irasok = [s for s in naplo.sorok() if s.get("m") == "ir" and isinstance(s.get("fajl"), str)]
        teendo = []
        for s in reversed(irasok):
            if "/" in s["fajl"] or s["fajl"].startswith("."):
                continue
            p = ws / s["fajl"]
            jelen = _olvas_opcionalis(p, 16 << 20)
            if jelen is None and p.exists():
                raise HttpError(409, f"The file {s['fajl']} changed after the import. Nothing was undone.",
                                kod="import.visszafordit_utkozes", param={"ut": s["fajl"]})
            if _sha(jelen) == s.get("utana_sha"):
                teendo.append((s, p))
            elif _sha(jelen) == s.get("elotte_sha"):
                continue                                 # never written, or already restored
            else:
                raise HttpError(409, f"The file {s['fajl']} changed after the import. Nothing was undone.",
                                kod="import.visszafordit_utkozes", param={"ut": s["fajl"]})
        visszaallitva = []
        for s, p in teendo:
            if s.get("elozo"):
                regi = (naplo.mappa / s["elozo"]).read_bytes()
                if _sha(regi) != s.get("elotte_sha"):
                    raise HttpError(409, f"The journal copy of {s['fajl']} is damaged. Nothing more was undone.",
                                    kod="import.visszafordit_utkozes", param={"ut": s["fajl"]})
                if p.name == workspace.WS_TOML:
                    with termek_beallitasok._zar(p):
                        workspace._atomi_ir_nofollow(p.parent, p.name, regi)
                else:
                    workspace._atomi_ir_nofollow(p.parent, p.name, regi)
            else:
                # a file the import created: its bytes are kept in the journal, then it leaves the workspace
                naplo.fajl_ir(f"visszavont-{p.name}", p.read_bytes())
                os.remove(p)
            visszaallitva.append(s["fajl"])
        eredmeny = {"id": id, "allapot": "visszaforditva", "visszaallitva": visszaallitva, "kukaba": [], "megtartva": [],
                    "ujrainditas": bool(visszaallitva)}
        naplo.sor({"m": "visszaforditva", "visszaallitva": visszaallitva})
        naplo.allapot_ir(allapot="visszaforditva", visszaforditas=eredmeny)
        return eredmeny


# ------------------------------------------------------------------ common: undo, list, state


def _ellenoriz_id(id) -> str:
    if not isinstance(id, str) or not _ID.match(id):
        raise HttpError(400, "The import ID is not valid.", kod="import.ervenytelen_keres", param={"mezo": "id"})
    return id


def visszafordit(id, alap, *, kuka=None, cfg=None) -> dict:
    """Undo an import by ID (`obs-…`: the Obsidian import, `kuka(path)` moves to the Trash; `v2-…`: the v2 import in `cfg`)."""
    id = _ellenoriz_id(id)
    if id.startswith("obs-"):
        if kuka is None:
            kuka = workspace._hej_kuka(alap)
        return _obsidian_visszafordit(id, alap, kuka)
    if cfg is None or not getattr(cfg, "workspace_id", None):
        raise HttpError(404, "There is no such import.", kod="import.nincs")
    return _v2_visszafordit(id, cfg)


def _naplok(alap, cfg=None) -> list[Naplo]:
    ki = []
    install = _install(alap)
    gyokerek = [Path(install) / "imports"] if install is not None else []
    if cfg is not None and getattr(cfg, "workspace_id", None):
        with contextlib.suppress(ConfigError, KeyError):
            gyokerek.append(cfg.path("state") / "import")
    for g in gyokerek:
        with contextlib.suppress(OSError):
            for e in os.scandir(g):
                if _ID.match(e.name) and e.is_dir(follow_symlinks=False):
                    ki.append(Naplo(Path(e.path)))
    return ki


def lista(alap, cfg=None) -> list[dict]:
    ki = []
    for n in _naplok(alap, cfg):
        a = n.allapot()
        if a:
            ki.append({**a, "fut": n.foglalt()})
    return sorted(ki, key=lambda a: str(a.get("frissitve") or ""), reverse=True)


def allapot(id, alap, cfg=None) -> dict:
    id = _ellenoriz_id(id)
    for n in _naplok(alap, cfg):
        if n.mappa.name == id:
            a = n.allapot()
            if a:
                return {**a, "fut": n.foglalt()}
    raise HttpError(404, "There is no such import.", kod="import.nincs")


# ------------------------------------------------------------------ HTTP


_FUTO: dict[str, threading.Thread] = {}
_MEGSZAKIT: dict[str, threading.Event] = {}      # the cancel flag of each running thread (same keys as `_FUTO`)
_FUTO_ZAR = threading.Lock()
_MEGSZAKIT_VARAKOZAS_MP = 10.0                   # how long the cancel request waits for the thread to reach a file boundary


def _kuka_gyar(cfg):
    """The Trash helper of the shell (`workspace._hej_kuka`); tests replace this."""
    return workspace._hej_kuka(cfg)


def _fejleszto_mod(cfg) -> bool:
    try:
        return bool(termek_beallitasok.olvas(cfg)["ertek"]["fejleszto"]["mod"])
    except (HttpError, ConfigError, OSError, KeyError):
        return False


def _fejleszto_kell(cfg) -> None:
    if not _fejleszto_mod(cfg):
        raise HttpError(403, "This import is available in Developer mode only.", kod="import.fejleszto_mod")


def _torzs(k, kulcsok: set[str], kotelezo: set[str]) -> dict:
    d = k.torzs()
    if not isinstance(d, dict) or set(d) - kulcsok or kotelezo - set(d):
        raise HttpError(400, "The import request is not valid.", kod="import.ervenytelen_keres", param={"mezo": "torzs"})
    return d


def _publikal(app, e: dict) -> None:
    with contextlib.suppress(Exception):
        app.bus.publish({"tipus": "import", **e})


def _obsidian_hatter(app, forras, cel, opciok, terv_hash, id, megszakit=None) -> None:
    def haladas(d):
        _publikal(app, {"id": id, "fajta": "obsidian", **d})
    try:
        r = obsidian_importal(forras, cel, app.cfg, opciok, terv_hash=terv_hash, haladas=haladas, megszakit=megszakit)
        _publikal(app, {"id": id, "fajta": "obsidian", "allapot": "kesz", "eredmeny": r})
    except Megszakitva as e:
        _publikal(app, {"id": id, "fajta": "obsidian", "allapot": "megszakitva", "kesz_db": e.kesz_db, "osszes_db": e.osszes_db})
    except BaseException as e:  # noqa: BLE001 — the journal has the error; the client gets it on the bus
        _publikal(app, {"id": id, "fajta": "obsidian", "allapot": "hiba",
                        "hiba": {"kod": getattr(e, "kod", None) or "import.masolas_hiba", "uzenet": str(e)}})
    finally:
        with _FUTO_ZAR:
            _FUTO.pop(id, None)
            _MEGSZAKIT.pop(id, None)


def utvonalak(r) -> None:
    def elonezet(k):
        d = _torzs(k, {"forras", "cel", "opciok"}, {"forras", "cel"})
        return obsidian_elonezet(_abszolut(d["forras"], "forras"), _abszolut(d["cel"], "cel"), k.app.cfg, d.get("opciok"))

    def importal(k):
        d = _torzs(k, {"forras", "cel", "opciok", "terv_hash"}, {"forras", "cel", "terv_hash"})
        if not isinstance(d["terv_hash"], str):
            raise HttpError(400, "The import request is not valid.", kod="import.ervenytelen_keres", param={"mezo": "terv_hash"})
        forras, cel = _abszolut(d["forras"], "forras"), _abszolut(d["cel"], "cel")
        t = obsidian_elonezet(forras, cel, k.app.cfg, d.get("opciok"))
        if t["eredmeny"] == "kesz":
            return {"id": t["id"], "allapot": "kesz", "ismetles": True}
        if d["terv_hash"] != t["terv_hash"]:
            raise _terv_valtozott()
        if "import_fut" in t["akadaly"]:
            raise HttpError(409, "This import is already running.", kod="import.fut")
        if t["akadaly"]:
            raise _tilos(t["akadaly"])
        with _FUTO_ZAR:
            if t["id"] in _FUTO:
                raise HttpError(409, "This import is already running.", kod="import.fut")
            megszakit = threading.Event()
            szal = threading.Thread(target=_obsidian_hatter, name=f"import-{t['id']}", daemon=True,
                                    args=(k.app, forras, cel, d.get("opciok"), d["terv_hash"], t["id"], megszakit))
            _FUTO[t["id"]] = szal
            _MEGSZAKIT[t["id"]] = megszakit
            szal.start()
        return Valasz(202, {"id": t["id"], "allapot": "fut"})

    def visszafordit_h(k):
        d = _torzs(k, {"id"}, {"id"})
        id = _ellenoriz_id(d["id"])
        if id.startswith("v2-"):
            _fejleszto_kell(k.app.cfg)
        with _FUTO_ZAR:
            if id in _FUTO:
                raise HttpError(409, "This import is already running.", kod="import.fut")
        r = visszafordit(id, k.app.cfg, kuka=_kuka_gyar(k.app.cfg) if id.startswith("obs-") else None, cfg=k.app.cfg)
        _publikal(k.app, {"id": id, "allapot": r["allapot"], "visszaforditas": r})
        return r

    def megszakit_h(k):
        d = _torzs(k, {"id"}, {"id"})
        id = _ellenoriz_id(d["id"])
        with _FUTO_ZAR:
            szal, jel = _FUTO.get(id), _MEGSZAKIT.get(id)
        if szal is None or jel is None:
            raise HttpError(409, "This import is not running.", kod="import.nem_fut")
        jel.set()                                        # the thread stops at the next file boundary
        szal.join(_MEGSZAKIT_VARAKOZAS_MP)
        if szal.is_alive():
            return Valasz(202, {"id": id, "allapot": "megszakitas"})
        a = allapot(id, k.app.cfg, k.app.cfg)
        return {"id": id, "allapot": a["allapot"], "megszakitva": a["allapot"] == "megszakitva"}

    def v2_elonezet_h(k):
        d = _torzs(k, {"forras"}, {"forras"})
        _fejleszto_kell(k.app.cfg)
        return v2_elonezet(_abszolut(d["forras"], "forras"), k.app.cfg)

    def v2_importal_h(k):
        d = _torzs(k, {"forras", "terv_hash"}, {"forras", "terv_hash"})
        _fejleszto_kell(k.app.cfg)
        if not isinstance(d["terv_hash"], str):
            raise HttpError(400, "The import request is not valid.", kod="import.ervenytelen_keres", param={"mezo": "terv_hash"})
        r = v2_importal(_abszolut(d["forras"], "forras"), k.app.cfg, terv_hash=d["terv_hash"])
        _publikal(k.app, {"id": r["id"], "fajta": "v2", "allapot": r["allapot"], "eredmeny": r})
        return r

    r.post("/api/import/obsidian/elonezet", elonezet)
    r.post("/api/import/obsidian", importal)
    r.get("/api/import", lambda k: {"importok": lista(k.app.cfg, k.app.cfg)})
    r.get("/api/import/allapot", lambda k: allapot(k.q.get("id"), k.app.cfg, k.app.cfg))
    r.post("/api/import/visszafordit", visszafordit_h)
    r.post("/api/import/megszakit", megszakit_h)
    r.post("/api/import/v2/elonezet", v2_elonezet_h)
    r.post("/api/import/v2", v2_importal_h)


# ------------------------------------------------------------------ CLI


def main(argv: list[str] | None = None) -> int:
    import argparse
    from . import fejleszto
    p = argparse.ArgumentParser(prog="python -m core.importalas", description="Import an Obsidian vault or Manifold-OS v2 settings.")
    al = p.add_subparsers(dest="fajta", required=True)
    o = al.add_parser("obsidian")
    o.add_argument("muvelet", choices=["elonezet", "importal"])
    o.add_argument("forras")
    o.add_argument("cel")
    o.add_argument("--kuka-mappa", action="store_true", help="also copy Obsidian's .trash/ folder")
    o.add_argument("--obsidian-nelkul", action="store_true", help="do not copy the .obsidian/ folder")
    o.add_argument("--nev", default="")
    o.add_argument("--hash", default=None)
    v = al.add_parser("v2")
    v.add_argument("muvelet", choices=["elonezet", "importal"])
    v.add_argument("forras")
    v.add_argument("--hash", default=None)
    vf = al.add_parser("visszafordit")
    vf.add_argument("id")
    al.add_parser("lista")
    a = p.parse_args(argv)
    try:
        if a.fajta == "obsidian":
            alap = config.load(munkater=False)
            opciok = {"obsidian_mappa": not a.obsidian_nelkul, "kuka_mappa": a.kuka_mappa, "nev": a.nev}
            if a.muvelet == "elonezet":
                ki = obsidian_elonezet(workspace._abs(a.forras), workspace._abs(a.cel), alap, opciok)
            else:
                ki = obsidian_importal(workspace._abs(a.forras), workspace._abs(a.cel), alap, opciok, terv_hash=a.hash)
        elif a.fajta == "v2":
            cfg = config.load()
            if not (fejleszto.aktiv() or _fejleszto_mod(cfg)):
                raise HttpError(403, "This import is available in Developer mode only.", kod="import.fejleszto_mod")
            ki = v2_elonezet(workspace._abs(a.forras), cfg) if a.muvelet == "elonezet" \
                else v2_importal(workspace._abs(a.forras), cfg, terv_hash=a.hash)
        elif a.fajta == "visszafordit":
            if a.id.startswith("v2-"):
                cfg = config.load()
                ki = visszafordit(a.id, cfg, cfg=cfg)
            else:
                alap = config.load(munkater=False)
                ki = visszafordit(a.id, alap)
        else:
            alap = config.load(munkater=False)
            ki = {"importok": lista(alap)}
    except (HttpError, ConfigError) as e:
        print(json.dumps({"ok": False, "kod": getattr(e, "kod", None), "hiba": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(ki, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
