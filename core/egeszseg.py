"""Health (F7): a termék állapota ellenőrzésenként — Diagnose / Fix / Learn more.

Minden ellenőrzés egy sor: stabil `kod` (index, pillanatkep, zarak, lemezhely, modellek, munkater, folyamatok), `allapot`
(ok | info | figyelem | hiba), `uzenet_kod` + `param` (a felület ezt fordítja: `egeszseg.uzenet.<uzenet_kod>`), az angol
tartalék `uzenet` (a `SZOVEG` sablonból), a `reszletek` (Diagnose: kulcs-érték párok, csak olvasva) és — ha van gépi javítása —
a `javitas` azonosítója. A `nyers` mező a doctor magyar, fejlesztői szövege: a felület csak Developer módban mutatja.

A „Fix automatically” (`javit`) KIZÁRÓLAG biztonságos, visszafordítható vagy magától újraépülő műveletet végez, és mindig
újra ellenőriz végrehajtás előtt (a javítás csak akkor fut, ha az ellenőrzés még most is ezt a javítást ajánlja):
  - `zar_takarit`: az elakadt `worker.pid` félretétele (átnevezés, nem törlés);
  - `git_zar_takarit`: egy elavult `index.lock` félretétele a pillanatkép-tárolóban (átnevezés);
  - `regiszter_takarit`: a regiszter mentése, majd a nem létező útra mutató bejegyzések elfelejtése (fájlokhoz nem nyúl);
  - `index_ujraepit`: a sérült index félretétele (a fájl megmarad) és újraépítése a vaultból;
  - `gyorsitotar_torles`: a kicsinyített képek gyorsítótára (bármikor újragenerálódik; jegyzethez nem nyúl).
A vaultba, a modellekbe és a letöltésekhez a Health soha nem nyúl; hálózat nincs.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import socket
import threading
import time
from pathlib import Path

from . import config, doctor, rejtett
from .utvonalak import HttpError

OK, INFO, FIGYELEM, HIBA = "ok", "info", "figyelem", "hiba"
ALLAPOTOK = (OK, INFO, FIGYELEM, HIBA)
ELAVULT_ZAR_MP = 600          # egy git-zár ennyi másodperc után számít elavultnak (ha a kör-zár szabad)

# Az angol tartalék-szövegek (a felület `egeszseg.uzenet.<kod>` kulcsa ugyanezt fordítja; a teszt őrzi az egyezést).
SZOVEG = {
    "ellenorzes.nem_futott": "This check could not run.",
    "index.nincs": "There is no search index yet. It is built the first time the workspace opens.",
    "index.ok": "The search index is healthy ({fajl} files).",
    "index.serult": "The search index cannot be read. It can be set aside and rebuilt from your notes.",
    "index.ujabb": "The search index was built by a newer version of Manifold.",
    "index.felretett": "{db} damaged index copies are kept aside. They are safe to remove by hand.",
    "pillanatkep.nincs": "There is no snapshot store yet. It is created with the first saved change.",
    "pillanatkep.ok": "Snapshots are working ({db} stores).",
    "pillanatkep.nincs_git": "Snapshots need Apple's Command Line Tools, which were not found, so changes cannot be snapshotted.",
    "pillanatkep.serult": "A snapshot store is incomplete: {tar}.",
    "pillanatkep.elavult_zar": "A snapshot store has a leftover lock from an interrupted save: {tar}.",
    "pillanatkep.mentes_regi": "The latest backup is older than your latest snapshot. It refreshes on quit.",
    "zarak.ok": "No leftover locks.",
    "zarak.elavult": "A leftover lock from a crashed AI engine can be set aside.",
    "zarak.foglalt": "The AI engine lock is still in use, so nothing can be cleaned up safely.",
    "lemezhely.ok": "There is enough free disk space.",
    "lemezhely.kevesebb": "Free disk space is low ({szabad_gb} GB left on the {kotet} volume).",
    "lemezhely.kritikus": "Free disk space is critically low ({szabad_gb} GB left on the {kotet} volume).",
    "modellek.nincs": "No AI models are installed. AI features are optional and stay off until you install one.",
    "modellek.reszleges": "{van} of {osszes} recommended models are installed.",
    "modellek.ok": "All {osszes} recommended models are installed.",
    "modellek.hianyos": "{db} models are incomplete or differ from the pinned version. Open Models to repair them.",
    "modellek.manifeszt": "The model list is missing or damaged. Reinstall Manifold.",
    "munkater.ok": "The workspace is healthy.",
    "munkater.vault_hianyzik": "The workspace folder cannot be found. If it is on an external drive, connect it.",
    "munkater.workspace_toml": "The workspace settings file is missing or damaged.",
    "munkater.workspace_ujabb": "This workspace was made by a newer version of Manifold. Update Manifold to open it.",
    "munkater.workspace_migracio": "This workspace uses an older format and will be upgraded.",
    "munkater.munkater_symlink": "The workspace data folder is a link, so it cannot be used safely.",
    "munkater.regiszter_ervenytelen_ut": "{db} saved workspaces point to folders that no longer exist. They can be forgotten (no files are touched).",
    "folyamatok.fut": "The background service is running. The AI engine is running.",
    "folyamatok.all": "The background service is running. The AI engine starts when an AI feature needs it.",
    "folyamatok.port_foglalt": "Another program is using the network port Manifold is configured to use ({port}).",
    "folyamatok.port_eltero": "The background service runs on port {port} instead of the configured port {beallitott}.",
    "telepites.ok": "The installed app is intact (version {verzio}).",
    "telepites.forras": "Manifold runs from a developer folder, so the installed-app check does not apply.",
    "telepites.hianyos": "The installed app has no build record, so it cannot be checked. Reinstall Manifold.",
    "telepites.alap": "This app has no detailed build record, so only a basic installation check is possible.",
    "telepites.modositott": "{db} files of the installed app were changed, added or removed after it was built. Reinstall Manifold.",
}
JAVITAS_KESZ = {
    "zar_takarit": "The leftover lock file was set aside.",
    "git_zar_takarit": "The leftover snapshot lock was set aside.",
    "regiszter_takarit": "{db} stale workspace entries were forgotten. A backup of the list was kept.",
    "index_ujraepit": "The search index is being rebuilt. The damaged file was kept aside.",
    "gyorsitotar_torles": "The image cache was cleared ({mb} MB freed). It rebuilds itself when needed.",
}
CIMEK = {"index": "Search index", "pillanatkep": "Snapshots", "zarak": "Locks", "lemezhely": "Disk space",
         "modellek": "AI models", "munkater": "Workspace", "folyamatok": "Background services", "telepites": "Installation"}


def _sor(kod: str, allapot: str, uzenet_kod: str, param: dict | None = None, *, javitas: str | None = None,
         reszletek: list | None = None, nyers: str | None = None) -> dict:
    param = {k: v for k, v in (param or {}).items()}
    szoveg = SZOVEG[uzenet_kod].format(**param) if param else SZOVEG[uzenet_kod]
    s = {"kod": kod, "allapot": allapot, "uzenet_kod": uzenet_kod, "param": param, "uzenet": szoveg, "javitas": javitas,
         "reszletek": [{"kulcs": k, "ertek": v} for k, v in (reszletek or [])]}
    if nyers:
        s["nyers"] = nyers
    return s


def _meret(p: Path, korlat: int = 300_000) -> int:
    """Egy mappa összmérete bájtban (szimlinket nem követ; korlátozott bejárás)."""
    ossz, n = 0, 0
    for gyoker, almappak, fajlok in os.walk(p, followlinks=False):
        rejtett.metsz_munkater(almappak)          # a munkatér állapota (`.manifold`, próbaklónok) nem a felhasználó adata
        for f in fajlok:
            n += 1
            if n > korlat:
                return ossz
            with contextlib.suppress(OSError):
                st = os.lstat(os.path.join(gyoker, f))
                ossz += st.st_size
    return ossz


# ------------------------------------------------------------------ ellenőrzések

def _index(cfg, app) -> list[dict]:
    import sqlite3
    from urllib.parse import quote
    from .index import tar
    d = cfg.path("index")
    db = d / "vault.sqlite"
    ki = []
    felretett = sorted(p.name for p in d.glob("serult-*.sqlite")) if d.is_dir() else []
    if not db.exists():
        ki.append(_sor("index", INFO, "index.nincs"))
    else:
        try:
            c = sqlite3.connect(f"file:{quote(str(db))}?mode=ro", uri=True, timeout=5)
            try:
                v = c.execute("PRAGMA user_version").fetchone()[0]
                ep = c.execute("PRAGMA quick_check").fetchone()[0]
                n = c.execute("SELECT count(*) FROM fajl WHERE torolve IS NULL").fetchone()[0] if v >= 1 else 0
            finally:
                c.close()
        except sqlite3.DatabaseError as e:
            ki.append(_sor("index", FIGYELEM, "index.serult", javitas="index_ujraepit",
                           reszletek=[("fajl", db.name), ("hiba", type(e).__name__)]))
        else:
            r = [("fajl", db.name), ("sema", v), ("fajlok", n)]
            if v > tar.VERZIO:
                ki.append(_sor("index", FIGYELEM, "index.ujabb", reszletek=r))
            elif ep != "ok":
                ki.append(_sor("index", FIGYELEM, "index.serult", javitas="index_ujraepit", reszletek=r + [("quick_check", ep)]))
            else:
                ki.append(_sor("index", OK, "index.ok", {"fajl": n}, reszletek=r))
    if felretett and ki:
        ki[0]["reszletek"].append({"kulcs": "felretett", "ertek": ", ".join(felretett)})
        if ki[0]["allapot"] == OK:
            ki[0].update(allapot=INFO, uzenet_kod="index.felretett", param={"db": len(felretett)},
                         uzenet=SZOVEG["index.felretett"].format(db=len(felretett)))
    return ki


def _git_elavult_zarak(cfg) -> list[tuple[str, Path]]:
    """Az elavult `index.lock`-ok a pillanatkép-tárolókban: elég régi, és a core kör-zárát senki nem tartja."""
    from . import snapshot
    run = cfg.utak.get("run")
    if run is not None and doctor._flock_szabad(run / "kor.lock") is False:
        return []
    ki = []
    for nev, repo in snapshot.repos(cfg).items():
        z = repo.git_dir / "index.lock"
        with contextlib.suppress(OSError):
            if z.is_file() and time.time() - z.stat().st_mtime > ELAVULT_ZAR_MP:
                ki.append((nev, z))
    return ki


def _pillanatkep(cfg, app) -> list[dict]:
    from . import mentes, snapshot
    tarak = {n: r for n, r in snapshot.repos(cfg).items() if r.exists()}
    if not tarak:
        return [_sor("pillanatkep", INFO, "pillanatkep.nincs")]
    if shutil.which("git") is None:
        return [_sor("pillanatkep", HIBA, "pillanatkep.nincs_git", reszletek=[("tarak", ", ".join(tarak))])]
    reszlet = [("tarak", ", ".join(sorted(tarak)))]
    elavult = _git_elavult_zarak(cfg)
    if elavult:
        return [_sor("pillanatkep", FIGYELEM, "pillanatkep.elavult_zar", {"tar": ", ".join(n for n, _ in elavult)},
                     javitas="git_zar_takarit", reszletek=reszlet + [("zar", z.name) for _, z in elavult])]
    for nev, r in tarak.items():
        if not (r.git_dir / "HEAD").read_text(errors="replace").strip():
            return [_sor("pillanatkep", FIGYELEM, "pillanatkep.serult", {"tar": nev}, reszletek=reszlet)]
    regi = []
    with contextlib.suppress(Exception):
        regi = [n for n, r in tarak.items() if r.live() and not mentes.friss(r, cfg.path("backup"), dirty=False)]
    if regi:
        return [_sor("pillanatkep", INFO, "pillanatkep.mentes_regi", reszletek=reszlet + [("mentes_regi", ", ".join(regi))])]
    return [_sor("pillanatkep", OK, "pillanatkep.ok", {"db": len(tarak)}, reszletek=reszlet)]


def _zarak(cfg, app) -> list[dict]:
    gyujto = []
    doctor._elavult_zarak(cfg, lambda allapot, nev, uzenet, kod=None, javitas=None, **_: gyujto.append((kod, javitas, uzenet)))
    if not gyujto:
        return [_sor("zarak", OK, "zarak.ok")]
    kod, javitas, uzenet = gyujto[0]
    if javitas:
        return [_sor("zarak", FIGYELEM, "zarak.elavult", javitas=javitas, nyers=uzenet)]
    return [_sor("zarak", FIGYELEM, "zarak.foglalt", nyers=uzenet)]


def _szabad(p: Path | None) -> int | None:
    return doctor._szabad_bajt(p) if p is not None else None


def _lemezhely(cfg, app) -> list[dict]:
    legrosszabb = None
    reszlet = []
    for nev, p in (("workspace", cfg.utak.get("vault")), ("app_data", cfg.utak.get("install"))):
        sz = _szabad(p)
        if sz is None:
            continue
        reszlet.append((nev + "_szabad_gb", round(sz / 1e9, 1)))
        if legrosszabb is None or sz < legrosszabb[0]:
            legrosszabb = (sz, nev)
    if legrosszabb is None:
        return []
    sz, nev = legrosszabb
    cache = cfg.utak.get("vault_kepek")
    meret = _meret(cache) if cache is not None and cache.is_dir() else 0
    param = {"szabad_gb": round(sz / 1e9, 1), "kotet": nev.replace("_", " ")}
    if sz < doctor.MIN_SZABAD_HIBA:
        allapot, kod = HIBA, "lemezhely.kritikus"
    elif sz < doctor.MIN_SZABAD_FIGYELEM:
        allapot, kod = FIGYELEM, "lemezhely.kevesebb"
    else:
        return [_sor("lemezhely", OK, "lemezhely.ok", reszletek=reszlet)]
    return [_sor("lemezhely", allapot, kod, param, javitas="gyorsitotar_torles" if meret else None,
                 reszletek=reszlet + [("kepek_gyorsitotara_mb", round(meret / 1e6, 1))])]


def telepitett_modellek(cfg) -> list[dict]:
    """A modell-manifeszt modelljei és a lemezen levő állapotuk (csak olvas): `{nev, repo, feladat, ajanlott, meret_gb, allapot,
    lemez_bajt, telepitve}`. `ManifesztHiba`, ha a manifeszt hiányzik vagy hibás."""
    from .modell import manifeszt
    man = manifeszt.betolt(cfg)
    models = cfg.path("models")
    ki = []
    for nev, m in sorted(man["modell"].items()):
        t = manifeszt.telepitettseg(models, nev, m)
        ki.append({"nev": nev, "repo": m["repo"], "feladat": m.get("feladat", []), "ajanlott": bool(m.get("ajanlott")),
                   "meret_gb": m.get("meret_gb"), "allapot": t["allapot"], "lemez_bajt": t["lemez_bajt"],
                   "telepitve": t["allapot"] in manifeszt.HASZNALHATO})
    return ki


_ALLAPOT_SZO = {"reszleges": "incomplete", "elter_revizio": "different version"}


def _modellek(cfg, app) -> list[dict]:
    from .modell import manifeszt
    try:
        lista = telepitett_modellek(cfg)
    except manifeszt.ManifesztHiba as e:
        return [_sor("modellek", HIBA, "modellek.manifeszt", reszletek=[("kod", e.kod)])]
    ajanlott = [m for m in lista if m["ajanlott"]] or lista
    van = [m for m in ajanlott if m["telepitve"]]
    reszlet = [("telepitve", ", ".join(m["nev"] for m in lista if m["telepitve"]) or "-")]
    hianyos = [m for m in lista if m["allapot"] in ("reszleges", "elter_revizio")]
    if hianyos:
        return [_sor("modellek", FIGYELEM, "modellek.hianyos", {"db": len(hianyos)},
                     reszletek=reszlet + [("hianyos", ", ".join(f"{m['nev']} ({_ALLAPOT_SZO.get(m['allapot'], 'unknown')})" for m in hianyos))])]
    if not any(m["telepitve"] for m in lista):
        return [_sor("modellek", INFO, "modellek.nincs", reszletek=reszlet)]
    if len(van) < len(ajanlott):
        return [_sor("modellek", INFO, "modellek.reszleges", {"van": len(van), "osszes": len(ajanlott)}, reszletek=reszlet)]
    return [_sor("modellek", OK, "modellek.ok", {"osszes": len(ajanlott)}, reszletek=reszlet)]


def _ervenytelen_regiszter(cfg) -> list[tuple[str, str]]:
    """A regiszter nem létező (és nem lecsatolt kötetre mutató) útú bejegyzései; a mostani munkatér sosem."""
    install = cfg.utak.get("install")
    if install is None:
        return []
    from .workspace import Regiszter
    mt = Regiszter(install).olvas()["munkaterek"]
    ki = []
    for az, e in sorted(mt.items()):
        if az == cfg.workspace_id or not isinstance(e, dict):
            continue
        p = e.get("vault")
        if isinstance(p, str) and p and not Path(p).exists() and not doctor._lecsatolt(p):
            ki.append((az, str(e.get("nev") or az[:8])))
    return ki


def _munkater(cfg, app) -> list[dict]:
    vault = cfg.utak.get("vault")
    if vault is None:
        return []
    if not vault.is_dir():
        return [_sor("munkater", HIBA, "munkater.vault_hianyzik", reszletek=[("kotet_lecsatolva", doctor._lecsatolt(str(vault)))])]
    gyujto = []
    doctor._munkater_sorok(cfg, cfg.elrendezes == "termek", lambda allapot, nev, uzenet, kod=None, javitas=None, **_: gyujto.append((allapot, kod, uzenet)))
    for allapot, kod, uzenet in gyujto:
        uzenet_kod = f"munkater.{kod}"
        if allapot in (doctor.HIBA, doctor.FIGYELEM) and uzenet_kod in SZOVEG:
            return [_sor("munkater", HIBA if allapot == doctor.HIBA else FIGYELEM, uzenet_kod, nyers=uzenet)]
        if allapot in (doctor.HIBA, doctor.FIGYELEM):
            return [_sor("munkater", allapot, "munkater.workspace_toml", nyers=uzenet)]
    rossz = _ervenytelen_regiszter(cfg)
    if rossz:
        return [_sor("munkater", FIGYELEM, "munkater.regiszter_ervenytelen_ut", {"db": len(rossz)}, javitas="regiszter_takarit",
                     reszletek=[("bejegyzes", n) for _, n in rossz])]
    return [_sor("munkater", OK, "munkater.ok")]


def _beallitott_port(cfg) -> int:
    try:
        return int(os.environ.get("MOS_CORE_PORT") or cfg.section("core").get("port", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _port_szabad(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _folyamatok(cfg, app) -> list[dict]:
    from .modell import kliens
    beallitott = _beallitott_port(cfg)
    port = getattr(app, "port", 0) if app is not None else 0
    url = (getattr(getattr(app, "worker", None), "url", None) if app is not None else None) or kliens.fut_url(cfg)
    worker = "running" if url else "idle"
    reszlet = [("core_port", port or "-"), ("beallitott_port", beallitott or "auto"), ("worker", worker)]
    if beallitott and app is not None and port and port != beallitott:
        return [_sor("folyamatok", FIGYELEM, "folyamatok.port_eltero", {"port": port, "beallitott": beallitott}, reszletek=reszlet)]
    if beallitott and app is None and doctor._flock_szabad(cfg.path("run") / "core.lock") is not False and not _port_szabad(beallitott):
        return [_sor("folyamatok", FIGYELEM, "folyamatok.port_foglalt", {"port": beallitott}, reszletek=reszlet)]
    return [_sor("folyamatok", OK, "folyamatok.fut" if url else "folyamatok.all", {"port": port or "-"}, reszletek=reszlet)]


def _telepites(cfg, app) -> list[dict]:
    """F9: a telepített csomag épsége a build befagyasztott jegyzékéhez mérve (`core.epites.csomag_ellenoriz`; csak olvas).
    Forrás-checkoutból futva nincs csomag: tájékoztató sor."""
    from . import epites
    from .gyoker_kereso import termek_gyoker
    if not termek_gyoker(cfg.root):
        return [_sor("telepites", INFO, "telepites.forras")]
    j = epites.fagyott(cfg.root)
    if j is None:
        try:                                 # a héj régi (v1, `csomag` nélküli) jegyzéke: csak alap-ellenőrzés (a doctor `mag`-sora)
            regi = json.loads(epites.fagyott_ut(cfg.root).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            regi = None
        if isinstance(regi, dict) and regi.get("verzio") == 1:
            return [_sor("telepites", INFO, "telepites.alap")]
        return [_sor("telepites", HIBA, "telepites.hianyos", reszletek=[("fajl", epites.fagyott_ut(cfg.root).name)])]
    cs = j["csomag"]
    ell = epites.csomag_ellenoriz(cfg.root, j)
    r = [("verzio", str(cs.get("termek_verzio") or "")), ("commit", str(cs.get("commit") or "")[:12]),
         ("epitve", str(cs.get("epitve") or "")), ("fajlok", ell["ellenorizve"])]
    if ell["ok"]:
        return [_sor("telepites", OK, "telepites.ok", {"verzio": str(cs.get("termek_verzio") or "?")}, reszletek=r)]
    db = len(ell["hianyzik"]) + len(ell["modositott"]) + len(ell["tobblet"])
    elso = lambda xs: ", ".join(xs[:5]) + (f" (+{len(xs) - 5})" if len(xs) > 5 else "")      # noqa: E731
    r += [(k, elso(ell[k])) for k in ("modositott", "hianyzik", "tobblet") if ell[k]]
    return [_sor("telepites", HIBA, "telepites.modositott", {"db": db}, reszletek=r)]


ELLENORZESEK = (("index", _index), ("pillanatkep", _pillanatkep), ("zarak", _zarak), ("lemezhely", _lemezhely),
                ("modellek", _modellek), ("munkater", _munkater), ("folyamatok", _folyamatok), ("telepites", _telepites))


def _futtat(kod: str, fn, cfg, app) -> list[dict]:
    try:
        return fn(cfg, app)
    except Exception as e:                     # egy ellenőrzés hibája nem viheti le a többit; a sor maga a jelzés
        return [{"kod": kod, "allapot": HIBA, "uzenet_kod": "ellenorzes.nem_futott", "param": {}, "javitas": None,
                 "uzenet": SZOVEG["ellenorzes.nem_futott"], "reszletek": [{"kulcs": "hiba", "ertek": type(e).__name__}]}]


def jelentes(cfg, app=None) -> dict:
    """Az összes ellenőrzés (csak olvas): `{verzio, osszesen, zold, ellenorzesek}`."""
    sorok = []
    for kod, fn in ELLENORZESEK:
        sorok += _futtat(kod, fn, cfg, app)
    for s in sorok:
        s["cim"] = CIMEK.get(s["kod"], s["kod"])
    szamok = {a: sum(1 for s in sorok if s["allapot"] == a) for a in ALLAPOTOK}
    return {"verzio": 1, "zold": szamok[HIBA] == 0 and szamok[FIGYELEM] == 0, "osszesen": szamok, "ellenorzesek": sorok}


def diagnosztika(cfg, app, kod: str) -> dict:
    """Egy ellenőrzés újrafuttatása részletekkel (Diagnose)."""
    fn = dict(ELLENORZESEK).get(kod)
    if fn is None:
        raise HttpError(404, "Unknown check.", kod="egeszseg.ismeretlen_ellenorzes")
    sorok = _futtat(kod, fn, cfg, app)
    for s in sorok:
        s["cim"] = CIMEK.get(kod, kod)
    return {"verzio": 1, "ellenorzesek": sorok}


# ------------------------------------------------------------------ javítások (csak biztonságos, visszafordítható)

def _ido() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _zar_takarit(cfg, app) -> dict:
    p = cfg.path("install_run") / "worker.pid"
    cel = p.with_name("worker.pid.elavult")
    os.replace(p, cel)
    return {"param": {}}


def _git_zar_takarit(cfg, app) -> dict:
    n = 0
    for nev, z in _git_elavult_zarak(cfg):
        os.replace(z, z.with_name(f"index.lock.elavult-{_ido()}"))
        n += 1
    return {"param": {"db": n}}


def _regiszter_takarit(cfg, app) -> dict:
    from .workspace import Regiszter
    install = cfg.utak["install"]
    reg = Regiszter(install)
    rossz = _ervenytelen_regiszter(cfg)
    if reg.ut.is_file():
        shutil.copy2(reg.ut, reg.ut.with_name(f"{reg.ut.name}.elozo-{_ido()}"))
    for az, _ in rossz:
        reg.elfelejt(az)
    return {"param": {"db": len(rossz)}}


def _index_ujraepit(cfg, app) -> dict:
    from .index import tar
    idx = getattr(app, "index", None)
    if idx is not None and hasattr(idx, "_serult_ujraepit"):
        t = threading.Thread(target=idx._serult_ujraepit, args=(RuntimeError("health"),), daemon=True, name="egeszseg-index")
        t.start()
        return {"param": {}, "szal": t}
    if doctor._flock_szabad(cfg.path("run") / "core.lock") is False:       # fut a core, de nem ez: nem nyúlunk az indexéhez
        raise HttpError(409, "The index is in use by a running core.", kod="egeszseg.nincs_mit_javitani")
    tar.felretesz(cfg.path("index") / "vault.sqlite")
    return {"param": {}}


def _gyorsitotar_torles(cfg, app) -> dict:
    cache = cfg.utak["vault_kepek"]
    meret = _meret(cache)
    for e in list(cache.iterdir()):
        if e.is_symlink() or e.is_file():
            e.unlink()
        else:
            shutil.rmtree(e, ignore_errors=True)
    return {"param": {"mb": round(meret / 1e6, 1)}}


JAVITASOK = {"zar_takarit": ("zarak", _zar_takarit), "git_zar_takarit": ("pillanatkep", _git_zar_takarit),
             "regiszter_takarit": ("munkater", _regiszter_takarit), "index_ujraepit": ("index", _index_ujraepit),
             "gyorsitotar_torles": ("lemezhely", _gyorsitotar_torles)}


def javit(cfg, app, javitas: str) -> dict:
    """„Fix automatically”: a megnevezett biztonságos javítás — csak ha az ellenőrzés most is ezt ajánlja. Az eredmény a friss sor."""
    if javitas not in JAVITASOK:
        raise HttpError(400, "Unknown fix.", kod="egeszseg.ismeretlen_javitas")
    ellenorzes, fn = JAVITASOK[javitas]
    ajanlott = any(s.get("javitas") == javitas for s in _futtat(ellenorzes, dict(ELLENORZESEK)[ellenorzes], cfg, app))
    if not ajanlott:
        raise HttpError(409, "Nothing to fix.", kod="egeszseg.nincs_mit_javitani")
    r = fn(cfg, app)
    ujra = _futtat(ellenorzes, dict(ELLENORZESEK)[ellenorzes], cfg, app)
    for s in ujra:
        s["cim"] = CIMEK.get(ellenorzes, ellenorzes)
    szal = r.pop("szal", None)
    if szal is not None and os.environ.get("MOS_EGESZSEG_SZINKRON") == "1":
        szal.join(30)
    return {"ok": True, "javitas": javitas, "uzenet_kod": javitas, "param": r["param"],
            "uzenet": JAVITAS_KESZ[javitas].format(**r["param"]) if r["param"] else JAVITAS_KESZ[javitas], "ellenorzesek": ujra}


def utvonalak(r) -> None:
    r.get("/api/egeszseg", lambda k: jelentes(k.app.cfg, k.app))

    def diag(k):
        return diagnosztika(k.app.cfg, k.app, (k.q.get("kod") or ""))

    def jav(k):
        d = k.torzs()
        return javit(k.app.cfg, k.app, d.get("javitas") if isinstance(d, dict) else None)
    r.get("/api/egeszseg/diagnosztika", diag)
    r.post("/api/egeszseg/javitas", jav)
