"""Privacy Center (F7): a hálózat, a modellek, a tárolt adat, az AI-memória, a tracker, az integrációk és az engedélyek VALÓS állapota.

Egyetlen csak-olvasó végpont (`GET /api/adatvedelem`): semmit nem módosít, hálózatot nem használ, a jegyzetek tartalmához nem nyúl.
A törlések a meglévő végpontokon mennek (AI-memória: `POST /api/asszisztens/tanult/torles`; tracker: `POST /api/tracker/torles`).
A szövegek a felületen vannak (`privacy.*`); itt csak azonosítók, számok és utak vannak — az út a felhasználó saját adatának helye.
"""
from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from . import egeszseg, vezerlo

MAX_LETOLTES = 10
# Amit a Manifold csak kifejezett felhasználói kérésre (gombnyomásra) tölt le: a kód ezt valósítja meg, a szerződés a D3 döntés.
ENGEDETT_LETOLTESEK = ("models", "runtime_tools", "video_links")
TILTOTT_HALOZAT = ("telemetry", "background_sync", "cloud_ai", "update_ping")


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def _bajt(p: Path | None) -> int | None:
    if p is None or not p.exists():
        return None
    if p.is_file():
        with contextlib.suppress(OSError):
            return p.stat().st_size
        return None
    return egeszseg._meret(p)


def halozat(cfg, app=None, env: dict | None = None) -> dict:
    """A hálózati szabály és az utolsó kifejezett letöltések. Az `offline` a folyamat TÉNYLEGES környezete (nem a szándék)."""
    e = os.environ if env is None else env
    offline = e.get("HF_HUB_OFFLINE") == "1" and e.get("TRANSFORMERS_OFFLINE", "1") == "1"
    moduloff = {m for m in ("video",) if cfg.section("modulok").get(m, True) is False}
    engedett = [{"kod": k, "elerheto": not (k == "video_links" and "video" in moduloff)} for k in ENGEDETT_LETOLTESEK]
    return {"offline": offline, "engedett": engedett, "tiltott": list(TILTOTT_HALOZAT), "utolso_letoltesek": utolso_letoltesek(cfg)}


def utolso_letoltesek(cfg) -> list[dict]:
    """A legutóbbi kifejezett letöltések: a modell-letöltő naplói (`{runs}/letoltes-*.json`) és a befejezett videó-feladatok
    (csak a gazdagép neve — a teljes link nem kerül ide). Legfeljebb `MAX_LETOLTES`, legújabb elöl."""
    ki = []
    runs = cfg.utak.get("runs")
    if runs is not None and runs.is_dir():
        for p in runs.glob("letoltes-*.json"):
            with contextlib.suppress(OSError, ValueError):
                adat = json.loads(p.read_text(encoding="utf-8"))
                for nev, r in (adat.items() if isinstance(adat, dict) else []):
                    ki.append({"fajta": "models", "nev": str(nev), "mikor": _iso(p.stat().st_mtime),
                               "eredmeny": str((r or {}).get("eredmeny") or "") if isinstance(r, dict) else ""})
    db = cfg.utak.get("feladatok_db")
    if db is not None and db.is_file():
        with contextlib.suppress(sqlite3.Error, OSError, ValueError):
            c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
            try:
                for tipus, par, allapot, vegzett in c.execute(
                        "SELECT tipus, parameterek, allapot, vegzett FROM feladat WHERE tipus = 'video_letoltes' AND vegzett IS NOT NULL "
                        "ORDER BY sor DESC LIMIT 20"):
                    from urllib.parse import urlsplit
                    hosts = []
                    for u in (json.loads(par or "{}").get("urlek") or []):
                        with contextlib.suppress(ValueError, TypeError):
                            h = urlsplit(str(u)).hostname
                            if h:
                                hosts.append(h)
                    ki.append({"fajta": "video_links", "nev": ", ".join(sorted(set(hosts))) or tipus, "mikor": str(vegzett),
                               "eredmeny": str(allapot)})
            finally:
                c.close()
    ki.sort(key=lambda x: x["mikor"], reverse=True)
    return ki[:MAX_LETOLTES]


def modellek(cfg) -> dict:
    from .modell import manifeszt
    try:
        lista = [m for m in egeszseg.telepitett_modellek(cfg) if m["lemez_bajt"]]
        hiba = None
    except manifeszt.ManifesztHiba as e:
        lista, hiba = [], e.kod
    mappa = cfg.utak.get("models")
    return {"telepitve": [{"nev": m["nev"], "repo": m["repo"], "feladat": m["feladat"], "allapot": m["allapot"], "bajt": m["lemez_bajt"]}
                          for m in lista], "ut": str(mappa) if mappa else None, "bajt": sum(m["lemez_bajt"] for m in lista), "hiba": hiba}


def adat_helyek(cfg) -> list[dict]:
    """Hol van a felhasználó adata és mennyi (bájt): minden hely a konfigurált útból, kontrollált bejárással."""
    def hely(kod, p, torolheto=False):
        return {"kod": kod, "ut": str(p) if p else None, "bajt": _bajt(p), "van": bool(p and p.exists()), "torolheto": torolheto}
    snap = [Path(cfg.expand(s["git_dir"])) for s in cfg.section("pillanat").values() if isinstance(s, dict) and "git_dir" in s]
    szem = cfg.utak.get("szemelyes")
    return [hely("workspace", cfg.utak.get("vault")), hely("snapshots", snap[0] if snap else None), hely("index", cfg.utak.get("index"), True),
            hely("personal", szem), hely("models", cfg.utak.get("models")), hely("backup", cfg.utak.get("backup")),
            hely("caches", cfg.utak.get("cache"), True), hely("logs", cfg.utak.get("runs"))]


def memoria(cfg, app=None) -> dict:
    kapcsolo = bool(vezerlo.kapcsolok(cfg)["asszisztens"])
    tetelek = {"mintak": 0, "muveletek": 0, "elutasitott": 0, "hangolas": 0}
    a = getattr(app, "asszisztens", None)
    if a is not None:
        with contextlib.suppress(Exception):
            t = a.tanult()
            for k in tetelek:
                v = t.get(k)
                tetelek[k] = len(v) if isinstance(v, (list, dict)) else 0
    return {"kapcsolo": kapcsolo, "tetelek": tetelek, "osszes": sum(tetelek.values())}


def tracker(cfg, app=None) -> dict:
    t = getattr(app, "tracker", None)
    be = bool(vezerlo.kapcsolok(cfg)["tracker"])
    ut = t.ut() if t is not None else cfg.path("szemelyes") / "szemelyes.sqlite"
    return {"be": be, "ut": str(ut), "bajt": _bajt(ut) or 0, "van": ut.exists(),
            "tarol": ["active_time", "edit_counts", "command_usage", "latency"], "nem_tarol": ["note_text"]}


def integraciok(cfg, app=None) -> list[dict]:
    from . import termek_beallitasok
    b = termek_beallitasok.olvas(cfg)["ertek"]["adatvedelem"]
    n = getattr(app, "naptar", None)
    nap = {}
    if n is not None:
        with contextlib.suppress(Exception):
            nap = dict(n.d)
    return [{"kod": "calendar", "be": bool(b["naptar"]), "elerheto": nap.get("seged"), "utolso": nap.get("utolso")},
            {"kod": "notifications", "be": bool(b["ertesitesek"]), "elerheto": True, "utolso": None},
            {"kod": "assistant", "be": bool(b["asszisztens"]), "elerheto": True, "utolso": None},
            {"kod": "tracker", "be": bool(b["tracker"]), "elerheto": True, "utolso": None}]


def engedelyek(cfg, app=None) -> dict:
    """Az operációs rendszer engedélyei: a naptáré a segéd utolsó mért állapota (`granted`/`denied`/…), az értesítésé a felületé
    (a böngésző/WebKit állapota nem a core-é, ezért itt csak a kapcsoló látszik)."""
    from . import termek_beallitasok
    b = termek_beallitasok.olvas(cfg)["ertek"]["adatvedelem"]
    n = getattr(app, "naptar", None)
    d = {}
    if n is not None:
        with contextlib.suppress(Exception):
            d = dict(n.d)
    return {"naptar": {"kapcsolo": bool(b["naptar"]), "esemeny": d.get("esemeny_engedely"), "emlekezteto": d.get("emlekezteto_engedely")},
            "ertesitesek": {"kapcsolo": bool(b["ertesitesek"])}}


def allapot(cfg, app=None, env: dict | None = None) -> dict:
    return {"verzio": 1, "mikor": _iso(time.time()), "halozat": halozat(cfg, app, env), "modellek": modellek(cfg),
            "adat": adat_helyek(cfg), "memoria": memoria(cfg, app), "tracker": tracker(cfg, app),
            "integraciok": integraciok(cfg, app), "engedelyek": engedelyek(cfg, app)}


def utvonalak(r) -> None:
    r.get("/api/adatvedelem", lambda k: allapot(k.app.cfg, k.app))
