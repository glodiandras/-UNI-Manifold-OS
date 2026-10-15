"""A Manifold-OS vezérlő core-oldali része (C17): rendszerállapot, kapcsolók, a feladat változásai.

Mindhárom csak olvas vagy a saját állapotfájlt írja; a vaultba nem ír, modellt nem tölt be, workert nem indít
(az app megnyitása és a vezérlő megnyitása nem indít nehéz munkát, D8).

- `GET /api/vezerlo/rendszer`: memória, a modellzár birtokosa, a betöltött modell és a keret, az SSD, az utolsó mentés.
- `GET/PUT /api/vezerlo/kapcsolok`: az Asszisztens és a Tracker kapcsolója (10. döntés: alapból be). Az Asszisztens
  kapcsoló az asszisztenst kapcsolja (80(a): higiénia, linkjavaslat, szokásminta), a feladatsort nem; a tracker kapcsolót a C27 olvassa.
- `GET /api/feladatok/{id}/valtozasok`: a feladat gépi commitjai (`Mos-Feladat` trailer, `frame.snapshot_frame`),
  körönként csoportosítva; a visszavonás a meglévő `POST /api/pillanat/vault/visszavonas {kor}`.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil
import threading
from pathlib import Path

from . import frame, mentes, snapshot
from .config import Config
from .modell import kliens, memoria
from .tasks import _ps

KAPCSOLOK_ALAP = {"asszisztens": True, "tracker": True}
MAX_COMMIT = snapshot.Repo.TRAILER_MAX_COMMIT   # a feladat legfeljebb ennyi commitja listázódik (a teljes történetben keresünk, T144)
_zar = threading.Lock()
_ZAR_SOR = re.compile(r"pid\s+(\d+)\s*·\s*(.*?)\s*·\s*(\S+)$")


# ------------------------------------------------------------------ kapcsolók

def _kapcsolo_ut(cfg: Config) -> Path:
    return cfg.path("state") / "kapcsolok.json"


def kapcsolok(cfg: Config) -> dict[str, bool]:
    """A kapcsolók értéke; hiányzó vagy sérült fájlnál az alap (mindkettő be)."""
    ki = dict(KAPCSOLOK_ALAP)
    try:
        d = json.loads(_kapcsolo_ut(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ki
    if isinstance(d, dict):
        for k in ki:
            if isinstance(d.get(k), bool):
                ki[k] = d[k]
    return ki


def kapcsolo_ir(cfg: Config, uj: dict) -> dict[str, bool]:
    """Részleges módosítás (`{"asszisztens": false}`); ismeretlen kulcs vagy nem logikai érték hiba."""
    if not isinstance(uj, dict) or not uj:
        raise ValueError("a kapcsolók JSON-objektumként kellenek")
    for k, v in uj.items():
        if k not in KAPCSOLOK_ALAP:
            raise ValueError(f"ismeretlen kapcsoló: {k}")
        if not isinstance(v, bool):
            raise ValueError(f"a(z) {k} kapcsoló értéke igaz vagy hamis lehet")
    with _zar:
        ki = {**kapcsolok(cfg), **uj}
        cel = _kapcsolo_ut(cfg)
        cel.parent.mkdir(parents=True, exist_ok=True)
        tmp = cel.with_name(f".{cel.name}.manifold-tmp")
        with open(tmp, "wb") as f:
            f.write(json.dumps(ki, ensure_ascii=False, indent=1).encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, cel)
    return ki


def admit_lanc(cfg: Config, kapu):
    """A feladatsor `admit` horga. 80(a): az Asszisztens-kapcsoló az asszisztenst kapcsolja (higiénia, linkjavaslat, szokásminta), nem a
    feladatsort; az egyetlen automatikus feladat, a vektorindex, a saját `[kereses.hibrid] vektor` kulcsán fut. A kapu (D8, aktív
    használat, memóriaőr) minden feladatra változatlan."""
    def admit(t) -> bool:
        return kapu.admit(t)
    return admit


# ------------------------------------------------------------------ rendszerállapot

def _rss_mb(pid: int | None) -> float | None:
    try:
        return round(int(_ps("rss", pid)) / 1024, 1) if pid else None
    except ValueError:
        return None


def _modellzar(ut: Path) -> dict:
    """A gépszintű modellzár (L23): a tartalma `pid <pid> · <repo> · HH:MM:SS`, elengedéskor üres. Elavult bejegyzés
    (a folyamat már nem él) szabadnak számít."""
    try:
        szoveg = ut.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        szoveg = ""
    m = _ZAR_SOR.match(szoveg)
    if not szoveg or not m:
        return {"szabad": True, "tartalom": szoveg, "pid": None, "repo": None, "ido": None, "elavult": False}
    pid = int(m.group(1))
    try:
        os.kill(pid, 0)
        el = True
    except PermissionError:
        el = True
    except OSError:
        el = False
    return {"szabad": not el, "tartalom": szoveg, "pid": pid, "repo": m.group(2), "ido": m.group(3), "elavult": not el}


def _worker(app) -> dict:
    url = app.worker.url or kliens.fut_url(app.cfg)
    if not url:
        return {"fut": False}
    try:
        h = kliens.health(url, timeout=2)
    except kliens.KliensHiba:
        return {"fut": False}
    return {"fut": True, "pid": h.get("pid"), "rss_mb": _rss_mb(h.get("pid")), "modell": h.get("modell"),
            "repo": h.get("repo"), "keret_gb": h.get("keret_gb"), "szunetek": h.get("szunetek"),
            "aktivitas": (h.get("aktivitas") or {}).get("allapot"), "fut_kerés": h.get("fut")}


def _ssd(cfg: Config) -> dict:
    ut = cfg.path("work")
    try:
        du = shutil.disk_usage(ut)
    except OSError as e:
        return {"elerheto": False, "hiba": str(e)}
    resz = ut.resolve().parts
    return {"elerheto": True, "kotet": resz[2] if len(resz) > 2 and resz[1] == "Volumes" else "belső lemez",
            "osszes_gb": round(du.total / 1e9, 1), "szabad_gb": round(du.free / 1e9, 1)}


def _mentes(cfg: Config) -> dict:
    backup = cfg.path("backup")
    tarolok, legujabb = {}, None
    for nev, repo in frame.live_repos(cfg).items():
        try:
            b = mentes.legujabb(repo, backup)
            friss = mentes.friss(repo, backup, dirty=False)     # a drága `git status` nélkül (a vezérlő gyakran kérdez)
        except (OSError, snapshot.SnapshotError):
            b, friss = None, False
        ido = _dt.datetime.fromtimestamp(b.stat().st_mtime).isoformat(timespec="seconds") if b else None
        tarolok[nev] = {"fajl": b.name if b else None, "ido": ido, "friss": friss}
        if ido and (legujabb is None or ido > legujabb):
            legujabb = ido
    hiba = mentes.hiba_olvas(cfg)
    return {"utolso": legujabb, "friss": all(t["friss"] for t in tarolok.values()), "tarolok": tarolok,
            "mappa": str(backup),
            # T023: a HIBÁS mentés (nem sikerült) más, mint a „változott” (még nem mentett): külön mező
            "hiba": {"ido": hiba.get("ido"), "hibak": hiba["hibak"]} if hiba else None}


def rendszer(app) -> dict:
    return {
        "memoria": {"szabad_szazalek": memoria.szabad_szazalek(), "osszes_gb": round(memoria.osszes_gb(), 1),
                    "swap_mb": memoria.swap_mb(), "core_rss_mb": _rss_mb(os.getpid())},
        "modellzar": _modellzar(Path(app.mb.zar)),
        "worker": _worker(app),
        "ssd": _ssd(app.cfg),
        "mentes": _mentes(app.cfg),
        "kapcsolok": kapcsolok(app.cfg),
    }


# ------------------------------------------------------------------ a feladat változásai

def valtozasok(cfg: Config, fid: str) -> dict:
    """A feladat gépi commitjai körönként. Csak olvas. **A teljes történetben** keres a `Mos-Feladat` trailer szerint (T144:
    a régi „utolsó 500 commit” ablak a régebbi feladatra hamisan „nem írt a vaultba”-t mondott), a már visszavont kört a
    `Mos-Visszavon-Kor` trailer jelzi; a fájllisták egyetlen git-folyamatból jönnek. `levagva`: a feladatnak a plafonnál
    (`MAX_COMMIT`) több commitja van — a lista csonka (a felület ezt mondja ki)."""
    from .utvonalak import HttpError
    repo = frame.live_repos(cfg).get("vault")
    if repo is None:
        return {"feladat": fid, "korok": [], "nincs_tar": True, "levagva": False}
    try:
        sajat, levagva = repo.trailer_commitok(snapshot.TRAILER_TASK, fid, max_db=MAX_COMMIT)
        visszavonok, levagva_v = repo.trailer_commitok("Mos-Visszavon-Kor", max_db=MAX_COMMIT) if sajat else ([], False)
    except ValueError as e:
        raise HttpError(400, f"érvénytelen feladat-azonosító: {fid!r}") from e
    visszavont = {c.trailers["Mos-Visszavon-Kor"] for c in visszavonok}
    sajat.reverse()                                     # régebbi → újabb
    fajlok = repo.commitok_fajlok([c.sha for c in sajat])
    korok: dict[str, dict] = {}
    for c in sajat:
        kor = c.run or c.sha[:12]
        k = korok.setdefault(kor, {"kor": kor, "visszavonva": kor in visszavont,
                                   "visszavonhato": bool(c.run) and kor not in visszavont and "proba" not in kor,
                                   "commitok": []})
        k["commitok"].append({"sha": c.sha, "datum": c.date, "targy": c.subject, "tetel": c.item,
                              "fajlok": fajlok.get(c.sha, [])})
    return {"feladat": fid, "korok": list(korok.values()), "nincs_tar": False, "levagva": levagva or levagva_v}


# ------------------------------------------------------------------ végpontok

def utvonalak(r) -> None:
    """A vezérlő végpontjai az útvonal-regiszterben; a `tasks.utvonalak` hívja (egy hely a feladatsorral)."""
    from . import (fuzet_feladat, grafikon_feladat, kartya_feladat, kviz_feladat, matek_feladat, osszefoglalas_feladat,
                   probafeladat, vektorindex_feladat, videolanc)
    from .utvonalak import HttpError

    if os.environ.get("MOS_PROBA_FELADAT") == "1":
        probafeladat.regisztral()
    videolanc.regisztral()                  # a videólánc feladattípusa (C20a): kézzel indított, a vaultba nem ír
    grafikon_feladat.regisztral()           # a ```plot automatikus beírása (C35b-mag): automatikus, a kapu alatt, gépi írással
    vektorindex_feladat.regisztral()        # a keresés vektorindexe (C25b): automatikus, a kapu alatt, a vaultba nem ír
    matek_feladat.regisztral()              # a „Megoldás” (C24b): kézzel indított, modell + CAS-homokozó, gépi írással
    fuzet_feladat.regisztral()              # a füzetlánc (C21): kézi, automatikus (a figyelő küldi), ellenőrző kör
    kartya_feladat.regisztral()             # a kártyák (C23b): kézi „Kártyák ebből” és automatikus, modell + kapuk, gépi írással
    osszefoglalas_feladat.regisztral()      # az összefoglaló (C26b): kézi (jegyzet, mappa, videó) és automatikus, modell + kapuk, gépi írással
    kviz_feladat.regisztral()               # a kvíz (C22b): kézi „Kvíz ebből”, modell + kapuk, gépi írással (automatikus nincs)

    r.get("/api/vezerlo/rendszer", lambda k: rendszer(k.app))
    r.get("/api/vezerlo/kapcsolok", lambda k: {"kapcsolok": kapcsolok(k.app.cfg)})

    def kapcsolo_put(k):
        try:
            ki = kapcsolo_ir(k.app.cfg, k.torzs())
        except ValueError as e:
            raise HttpError(400, str(e)) from e
        k.app.bus.publish({"tipus": "kapcsolok", "kapcsolok": ki})
        return {"ok": True, "kapcsolok": ki}
    r.put("/api/vezerlo/kapcsolok", kapcsolo_put)
    r.get(re.compile(r"/api/feladatok/([\w.-]+)/valtozasok"), lambda k: valtozasok(k.app.cfg, k.m.group(1)))
