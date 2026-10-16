"""The demo workspace ("Try the demo workspace"): a deterministic, fully synthetic sample library, its state and its reset.

**What it is.** About eighty invented notes (maths with LaTeX, science with pictures, code tasks in C++/Python/JavaScript,
study skills, fictional books with properties, projects with dated tasks, fourteen daily notes, meetings, reference pages),
companion cards and quizzes, a generated PDF with highlights, a canvas, two Bases, property types, sample calendar events and
sample AI-memory items. The content lives in `demo_tartalom` / `demo_tanulas` / `demo_fajlok`; nothing in it comes from a
real vault, and nothing is downloaded. AI features in the demo stay in **Trial** mode: no model is installed or requested.

**Safety rules.**
- The generator writes only inside the demo workspace folder (`{install}/demo/...`), which must be registered with the `demo`
  flag in the workspace registry and carry the generator marker `.manifold/demo-alap.json` with the same workspace id. A user
  workspace never satisfies all three (`ellenoriz_demo`).
- Files are created exclusively (`tartos.kizaro_ir`): opening the demo again never overwrites an edit and never brings back a
  note the user deleted. Every write goes through a path check that refuses links and escapes.
- **Reset** (`alaphelyzet`) needs an explicit confirmation. It first commits a local snapshot (so the previous state is one undo
  away), restores every generator file to its original bytes (atomic replacement), moves notes the user added to
  `.manifold/demo-reset/<time>/` (nothing is deleted), resets the sample state (calendar, assistant memory, learning progress),
  and takes a second snapshot. It refuses on any workspace that is not the demo.
- The seed (`SEED`) makes the sampled parts reproducible; the same seed always gives the same bytes. The calendar events are
  placed around "today" when they are written; the files themselves do not depend on the date.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

from . import config, demo_tanulas, demo_tartalom, doku, frame, kiserok, snapshot, tartos, workspace
from .utvonalak import HttpError

SEED = 20261001
VERZIO = 2                                    # the generator version written to the marker
JELOLO = "demo-alap.json"                     # inside `.manifold/`
VISSZA_MAPPA = "demo-reset"                   # inside `.manifold/`: where reset puts notes the user added
DEMO_NEV = "Manifold Demo"
FORRAS = {"Mos-Forras": "kezi"}
MAX_FAJL = 600


# ------------------------------------------------------------------ content

def tartalom(seed: int = SEED, cfg=None) -> dict[str, bytes]:
    """Every file of the demo library as `{vault-relative path: bytes}`. Pure and deterministic; `cfg` only names the companion
    folders (the neutral defaults when absent)."""
    kartya_mappa, kviz_mappa = kiserok.kisero_mappa(cfg, "kartya"), kiserok.kisero_mappa(cfg, "kviz")
    szoveg: dict[str, str] = demo_tartalom.jegyzetek(seed)
    szoveg.update(demo_tanulas.kod(seed))
    md_utak = sorted(u for u in szoveg if u.endswith(".md"))
    szoveg.update(demo_tanulas.kartyak(seed, kartya_mappa, md_utak))
    szoveg.update(demo_tanulas.kvizek(seed, kviz_mappa))
    szoveg.update(demo_tanulas.kiemeles_jegyzet(seed))
    szoveg.update(demo_tanulas.canvas(seed))
    szoveg.update(demo_tanulas.bazisok())
    szoveg.update(demo_tanulas.tipusok())
    ki = {rel: t.encode("utf-8") for rel, t in szoveg.items()}
    ki.update({rel: b for rel, b in demo_tanulas.kepek().items()})
    ki[demo_tanulas.PDF_UT] = demo_tanulas.pdf_bajtok()
    ki.update(utmutato_fajlok())
    return dict(sorted(ki.items()))


def utmutato_fajlok() -> dict[str, bytes]:
    """The built-in user documentation as the "Manifold Guide" folder (16 pages, wikilinks inside the workspace), from
    `core/doku.py`. Missing documentation sources (a stripped install) leave the demo without the folder, never broken."""
    try:
        return doku.munkater_fajlok()
    except OSError:
        return {}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def kivonat(seed: int = SEED, cfg=None) -> dict[str, str]:
    return {rel: _sha(b) for rel, b in tartalom(seed, cfg).items()}


def jegyzet_db(tart: dict[str, bytes]) -> int:
    """Sample notes (not templates, not companion cards/quizzes, not the guide pages)."""
    return sum(1 for u in tart if u.endswith(".md") and not u.startswith(("_Template/", "Manifold - ", doku.MUNKATER_MAPPA + "/")))


# ------------------------------------------------------------------ identification and safe paths

def _regiszter_bejegyzes(alap, id: str | None) -> dict | None:
    if not id:
        return None
    try:
        return workspace.Regiszter(alap.path("install")).olvas()["munkaterek"].get(id)
    except (OSError, config.ConfigError, KeyError):
        return None


def jelolo_olvas(vault: Path) -> dict | None:
    try:
        d = json.loads((Path(vault) / workspace.MAPPA / JELOLO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def demo_munkater(cfg) -> bool:
    """True only for the registered demo workspace of this installation: the folder is under `{install}/demo`, the registry entry
    carries the `demo` flag for exactly this workspace id and folder, and the generator marker names the same id."""
    try:
        vault, install = Path(cfg.path("vault")), Path(cfg.path("install"))
    except config.ConfigError:
        return False
    if not cfg.workspace_id or not workspace._alatt(vault, install / "demo"):
        return False
    e = _regiszter_bejegyzes(cfg, cfg.workspace_id)
    if not isinstance(e, dict) or e.get("demo") is not True or not isinstance(e.get("vault"), str):
        return False
    try:
        if not os.path.samefile(e["vault"], vault):
            return False
    except OSError:
        return False
    j = jelolo_olvas(vault)
    return bool(j and j.get("id") == cfg.workspace_id)


def ellenoriz_demo(cfg) -> None:
    if not demo_munkater(cfg):
        raise HttpError(403, "This is not the demo workspace. The demo can only be reset inside the demo workspace.",
                        kod="demo.nem_demo")


def _ut_biztos(vault: Path, rel: str) -> Path:
    """The absolute path of `rel` inside `vault`, without links: every existing component must be a real directory (or the file
    itself a regular file / absent) and the result must stay below the vault. Raises `ValueError` otherwise."""
    if not rel or rel.startswith("/") or any(p in ("", ".", "..") for p in rel.split("/")) or "\\" in rel or "\x00" in rel:
        raise ValueError(f"unsafe demo path: {rel!r}")
    p = Path(vault)
    for resz in rel.split("/")[:-1]:
        p = p / resz
        if p.is_symlink() or (p.exists() and not p.is_dir()):
            raise ValueError(f"unsafe demo path component: {rel!r}")
    cel = p / rel.split("/")[-1]
    if cel.is_symlink() or (cel.exists() and not cel.is_file()):
        raise ValueError(f"unsafe demo path: {rel!r}")
    return cel


# ------------------------------------------------------------------ state seeds (calendar, assistant memory, learning progress)

def _naptar_beir(cfg, most: dt.datetime) -> None:
    from . import naptar
    naptar.szinkron(cfg, seged=demo_tanulas.DemoNaptarSeged(most), most=most)


def _memoria_beir(cfg) -> None:
    from .asszisztens.allapot import Allapot
    m = demo_tanulas.asszisztens_memoria()
    Allapot(cfg).modosit(lambda d: d.update(kiegeszites_mintak=m["kiegeszites_mintak"], muveletek=m["muveletek"]))


def _tanulas_nulla(cfg) -> None:
    """Learning progress of the demo (cards, quiz attempts) back to the start. Only called for the demo workspace."""
    from . import tanulas_db
    with tanulas_db.olvaso(cfg) as c:
        van = c is not None
    if not van:
        return
    with tanulas_db.iro(cfg) as c:
        c.execute("UPDATE kartya SET allapot=0, lepes=NULL, stabilitas=NULL, nehezseg=NULL, esedekes=NULL, utolso=NULL")
        for t in ("valasz", "kviz_valasz", "kviz_kitoltes", "kviz_jeloles"):
            c.execute(f"DELETE FROM {t}")


def _allapot_beir(cfg, most: dt.datetime | None) -> None:
    most = most or dt.datetime.now().astimezone()
    _naptar_beir(cfg, most)
    _memoria_beir(cfg)


# ------------------------------------------------------------------ generation

def _jelolo_ir(vault: Path, id: str, seed: int, kiv: dict[str, str]) -> None:
    adat = {"verzio": VERZIO, "seed": seed, "id": id, "fajlok": kiv}
    workspace._atomi_ir_nofollow(Path(vault) / workspace.MAPPA, JELOLO,
                                 (json.dumps(adat, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8"))


def general(cfg, *, seed: int = SEED, most: dt.datetime | None = None, haladas=lambda d: None) -> dict:
    """Writes the demo library into the (already created and registered) demo workspace. Idempotent: files that exist are never
    touched, files the user deleted are not brought back (only a first run or an older generator version creates the rest).
    Returns `{"uj": files created, "volt": files left alone, "elso": bool}`."""
    ellenoriz_demo_vagy_uj(cfg)
    vault = Path(cfg.path("vault"))
    tart = tartalom(seed, cfg)
    if len(tart) > MAX_FAJL:
        raise RuntimeError("the demo library is larger than expected")
    j = jelolo_olvas(vault)
    elso = not j or j.get("verzio", 0) < 2
    uj = volt = 0
    with frame.run_lock(cfg):
        if elso:
            haladas({"lepes": "demo-fajlok", "osszes": len(tart)})
            for rel, adat in tart.items():
                cel = _ut_biztos(vault, rel)
                cel.parent.mkdir(parents=True, exist_ok=True)
                try:
                    tartos.kizaro_ir(cel, adat)
                    uj += 1
                except FileExistsError:
                    volt += 1
            snapshot.repos(cfg)["vault"].commit("Demo sample library", FORRAS)
            _allapot_beir(cfg, most)
            _jelolo_ir(vault, cfg.workspace_id, seed, {rel: _sha(b) for rel, b in tart.items()})
    return {"uj": uj, "volt": volt, "elso": elso, "fajl": len(tart), "jegyzet": jegyzet_db(tart)}


def ellenoriz_demo_vagy_uj(cfg) -> None:
    """During the first generation the marker does not exist yet: the folder and the registry entry must already be the demo's."""
    vault, install = Path(cfg.path("vault")), Path(cfg.path("install"))
    if not cfg.workspace_id or not workspace._alatt(vault, install / "demo"):
        raise HttpError(403, "The demo library can only be created inside the demo workspace.", kod="demo.nem_demo")
    e = _regiszter_bejegyzes(cfg, cfg.workspace_id)
    if not isinstance(e, dict) or e.get("demo") is not True:
        raise HttpError(403, "The demo library can only be created inside the demo workspace.", kod="demo.nem_demo")
    j = jelolo_olvas(vault)
    if j and j.get("id") not in (None, cfg.workspace_id):
        raise HttpError(403, "The demo marker belongs to another workspace.", kod="demo.nem_demo")


def inditas(alap, haladas=lambda d: None, *, seed: int = SEED, most: dt.datetime | None = None) -> tuple[Path, "config.Config", dict]:
    """"Try the demo workspace": creates (or reopens) the demo workspace, generates the library on the first run.
    → (folder, workspace config, generation result). No network, no model."""
    v = Path(alap.path("install")) / "demo" / DEMO_NEV
    workspace.letrehoz(v, alap, nev=DEMO_NEV, nyelv="", demo=True, haladas=haladas)
    cfg = config.load(workspace._env(alap, MOS_VAULT=str(v)))
    return v, cfg, general(cfg, seed=seed, most=most, haladas=haladas)


# ------------------------------------------------------------------ status

def _fajlok_lemezen(vault: Path) -> set[str]:
    ki = set()
    for d, mappak, fajlok in os.walk(vault):
        mappak[:] = [m for m in mappak if not m.startswith(".")]
        for f in fajlok:
            if f.startswith("."):
                continue
            ki.add(os.path.relpath(os.path.join(d, f), vault).replace(os.sep, "/"))
    return ki


def allapot(cfg) -> dict:
    """`{demo, verzio, seed, fajl, modositott, hianyzo, hozzaadott}`. For a user workspace only `{"demo": False}` (nothing is read)."""
    if not demo_munkater(cfg):
        return {"ok": True, "demo": False}
    vault = Path(cfg.path("vault"))
    j = jelolo_olvas(vault) or {}
    kiv = j.get("fajlok") if isinstance(j.get("fajlok"), dict) else {}
    modositott = hianyzo = 0
    for rel, h in kiv.items():
        try:
            cel = _ut_biztos(vault, rel)
            if not cel.exists():
                hianyzo += 1
            elif _sha(cel.read_bytes()) != h:
                modositott += 1
        except (OSError, ValueError):
            modositott += 1
    kiv_dot = {r for r in kiv if not r.startswith(".")}
    return {"ok": True, "demo": True, "verzio": j.get("verzio"), "seed": j.get("seed"), "fajl": len(kiv),
            "modositott": modositott, "hianyzo": hianyzo, "hozzaadott": len(_fajlok_lemezen(vault) - kiv_dot)}


# ------------------------------------------------------------------ reset

def _felreteszi(vault: Path, extra: list[str], mikor: str) -> list[str]:
    """Moves `extra` files (not part of the generator) into `.manifold/demo-reset/<mikor>/`, keeping their relative paths."""
    cel_gyoker = vault / workspace.MAPPA / VISSZA_MAPPA / mikor
    athelyezve = []
    for rel in sorted(extra):
        try:
            forras = _ut_biztos(vault, rel)
        except ValueError:
            continue
        if not forras.is_file():
            continue
        cel = cel_gyoker / rel
        cel.parent.mkdir(parents=True, exist_ok=True)
        if cel.exists():
            continue
        os.rename(forras, cel)
        athelyezve.append(rel)
    return athelyezve


def _ures_mappak_takarit(vault: Path, kiv: set[str]) -> None:
    """Removes directories that became empty because their notes were moved away (never the generator's own folders)."""
    generator_mappak = {str(Path(r).parent) for r in kiv} | {""}
    for d, mappak, fajlok in os.walk(vault, topdown=False):
        mappak[:] = [m for m in mappak if not m.startswith(".")]
        p = Path(d)
        rel = str(p.relative_to(vault))
        if rel in (".",) or rel.startswith(".") or rel in generator_mappak:
            continue
        with contextlib.suppress(OSError):
            if not any(p.iterdir()):
                p.rmdir()


def alaphelyzet(cfg, *, megerosit=False, seed: int = SEED, most: dt.datetime | None = None, haladas=lambda d: None) -> dict:
    """Restores the demo workspace to its original state (see the module note). Refuses without `megerosit is True`, and on any
    workspace that is not the registered demo workspace. → `{"ok", "visszaallitva", "ujra_letrehozva", "felretett", "pillanatkep"}`."""
    if megerosit is not True:
        raise HttpError(400, "Confirm the reset: it restores the demo notes and sets the demo's sample data back.", kod="demo.megerosites")
    ellenoriz_demo(cfg)
    vault = Path(cfg.path("vault"))
    tart = tartalom(seed, cfg)
    mikor = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    visszaallitva = ujra = 0
    veszelyes = []
    for rel in tart:                                  # everything is checked before anything is touched
        try:
            _ut_biztos(vault, rel)
        except ValueError:
            veszelyes.append(rel)
    if veszelyes:
        raise HttpError(409, "A folder of the demo workspace is a link or not a normal folder, so it cannot be reset safely.",
                        kod="demo.nem_biztonsagos_ut", param={"db": len(veszelyes)})
    with frame.run_lock(cfg):
        haladas({"lepes": "pillanatkep"})
        elotte = snapshot.repos(cfg)["vault"].commit("Before demo reset", FORRAS)
        haladas({"lepes": "fajlok", "osszes": len(tart)})
        for rel, adat in tart.items():
            cel = _ut_biztos(vault, rel)
            if cel.exists():
                if cel.read_bytes() == adat:
                    continue
                visszaallitva += 1
            else:
                ujra += 1
            cel.parent.mkdir(parents=True, exist_ok=True)
            tartos.atomi_ir(cel, adat)
        extra = sorted(_fajlok_lemezen(vault) - set(tart))
        felretett = _felreteszi(vault, extra, mikor)
        _ures_mappak_takarit(vault, set(tart))
        haladas({"lepes": "allapot"})
        _tanulas_nulla(cfg)
        _allapot_beir(cfg, most)
        _jelolo_ir(vault, cfg.workspace_id, seed, {rel: _sha(b) for rel, b in tart.items()})
        utana = snapshot.repos(cfg)["vault"].commit("Demo workspace reset", FORRAS)
    return {"ok": True, "visszaallitva": visszaallitva, "ujra_letrehozva": ujra, "felretett": felretett,
            "pillanatkep": {"elotte": elotte, "utana": utana}, "visszahelye": f"{workspace.MAPPA}/{VISSZA_MAPPA}/{mikor}" if felretett else None}


# ------------------------------------------------------------------ HTTP

def utvonalak(r) -> None:
    def torzs(k):
        d = k.torzs()
        if not isinstance(d, dict) or set(d) - {"megerosit"}:
            raise HttpError(400, "The reset request takes only a confirmation.", kod="demo.hibas_keres")
        return d

    r.get("/api/demo/allapot", lambda k: allapot(k.app.cfg))
    r.post("/api/demo/alaphelyzet", lambda k: alaphelyzet(k.app.cfg, megerosit=torzs(k).get("megerosit")))
