"""A videólánc felületi végpontjai (C20b, 7. pont: a Bevitel szakasz).

- `POST /api/video/bejovo` `{nev, csoport?, offset, adat (base64), vege}` — egy behúzott/kiválasztott videó darabja a
  `{video_bejovo}/<csoport>/` alá (a vaulton kívül). A darab a `.<nev>.part`-hoz fűződik, csak a pontos `offset`-en (folytatható,
  sorrendhelyes); a `vege` a kész fájlt a végleges nevére teszi, felülírás nélkül (ütközésnél `(2)`, `(3)` …). A feldolgozást a
  `video_integralas` feladat indítja (`POST /api/feladatok`, `{csoport}`): a fájl staging-forrásmappa lesz, majd a vaultba kerül.
- `GET /api/video/allapot` — a staging forrásai `integration_status` szerint, és a legutóbbi bevitelek riportjának összegzése; a
  86. döntés (javasolt) célmappás bevitelének: a várakozó forrásmappák (`fuggo`, staging-relatív út + cím) és a vault téma-mappái
  (`temamappak`, a „Célmappa (téma)” mező javaslatai).

A lépés-kapu (`core/lepes_kapu.py`) döntéstáblájában a feltöltés a lépés-folyamat számára tiltott (felületi művelet).
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import re
import secrets
import time
import unicodedata
from pathlib import Path

from .utvonalak import HttpError

MAX_DARAB_BAJT = 8 * 1024 * 1024            # a JSON-törzs 16 MiB-os korlátja alatt, base64-gyel
_NEV = re.compile(r'[\\/:*?"<>|#^\[\]\x00-\x1f]')
KITERJESZTESEK = (".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi")
CSOPORT = re.compile(r"[A-Za-z0-9_-]{1,64}")
FUGGO_MAX = 200                             # a `video_integralas` `mappak` korlátja is ennyi


def biztonsagos_nev(nev) -> str:
    nev = unicodedata.normalize("NFC", os.path.basename(str(nev or "")).strip())
    nev = _NEV.sub("_", nev).lstrip(".")
    if not nev or not nev.lower().endswith(KITERJESZTESEK) or len(nev.encode("utf-8")) > 200:
        raise HttpError(400, "csak videófájl tölthető fel (mp4, m4v, mov, mkv, webm, avi; legfeljebb 200 bájtos névvel)")
    return nev


def bejovo(app, body: dict) -> dict:
    if not isinstance(body, dict):
        raise HttpError(400, "a kérés JSON-objektum")
    nev = biztonsagos_nev(body.get("nev"))
    csoport = body.get("csoport") or time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3)
    if not isinstance(csoport, str) or not CSOPORT.fullmatch(csoport):
        raise HttpError(400, "érvénytelen csoport-azonosító")
    offset = body.get("offset", 0)
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise HttpError(400, "az `offset` nemnegatív egész")
    adat = body.get("adat", "")
    if not isinstance(adat, str) or len(adat) > MAX_DARAB_BAJT * 4 // 3 + 8:
        raise HttpError(413 if isinstance(adat, str) else 400, "a darab base64-kódolt `adat` mezőben jön, legfeljebb 8 MiB")
    try:
        b = base64.b64decode(adat, validate=True)
    except (binascii.Error, ValueError):
        raise HttpError(400, "az `adat` nem érvényes base64") from None
    max_bajt = int(float(app.cfg.section("video").get("bejovo_max_gb", 20)) * (1 << 30))
    if offset + len(b) > max_bajt:
        raise HttpError(413, f"a fájl nagyobb a megengedettnél ({max_bajt >> 30} GiB)")
    d = app.cfg.path("video_bejovo") / csoport
    d.mkdir(parents=True, exist_ok=True)
    part = d / f".{nev}.part"
    meglevo = part.stat().st_size if part.exists() else 0
    if offset != meglevo:
        raise HttpError(409, f"a darab helye ({offset}) nem a fájl jelenlegi vége ({meglevo})", offset=meglevo, csoport=csoport)
    with open(part, "ab") as fh:
        fh.write(b)
    meret = meglevo + len(b)
    if not body.get("vege"):
        return {"ok": True, "csoport": csoport, "offset": meret}
    if meret == 0:
        part.unlink(missing_ok=True)
        raise HttpError(400, "üres fájl")
    from . import tartos
    torzs, kit = os.path.splitext(nev)
    for i in range(1, 1000):
        cel = d / (nev if i == 1 else f"{torzs} ({i}){kit}")
        try:
            tartos.rename_excl(part, cel)
            break
        except FileExistsError:
            continue
    else:
        raise HttpError(409, "nincs szabad név a beérkező mappában")
    return {"ok": True, "csoport": csoport, "nev": cel.name, "meret": meret, "kesz": True}


def allapot(app) -> dict:
    gyoker = app.cfg.path("staging")
    db: dict[str, int] = {}
    fuggo: list[dict] = []
    if gyoker.is_dir():
        for dp, dn, fn in os.walk(gyoker):
            dn[:] = sorted(x for x in dn if not x.startswith("."))
            if "integration.json" in fn:
                try:
                    st = json.loads(Path(dp, "integration.json").read_text(encoding="utf-8")).get("integration_status") or "?"
                except (OSError, ValueError):
                    st = "hibás"
                db[st] = db.get(st, 0) + 1
                if st == "pending" and len(fuggo) < FUGGO_MAX:      # 86. d.: a célmappás bevitel kijelölhető forrásai
                    rel = unicodedata.normalize("NFC", os.path.relpath(dp, gyoker))
                    fuggo.append({"mappa": rel.replace(os.sep, "/"), "cim": unicodedata.normalize("NFC", os.path.basename(dp))})
                dn[:] = []
    riportok = []
    d = app.cfg.path("runs") / "video"
    for p in sorted(d.glob("VIDEOBE-*.json"), reverse=True)[:5] if d.is_dir() else []:
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        riportok.append({"kor": r.get("kor"), "eredmeny": r.get("eredmeny"),
                         "tetelek": [{k: t.get(k) for k in ("cim", "allapot", "uzenet", "commit")} | {"tema": (t.get("tema") or {}).get("tema"),
                                      "biztossag": (t.get("tema") or {}).get("biztossag"), "kotes_db": len(t.get("kotesek") or [])}
                                     for t in (r.get("tetelek") or [])[:20]]})
    from .videolanc import temamappak
    return {"staging": db, "varakozik": db.get("pending", 0), "legutobbi": riportok, "fuggo": fuggo,
            "temamappak": temamappak(app.cfg.path("vault"))}


# a tétel forrása (`kozvetlen` fájl vagy `beagyazott` lejátszó) és a közvetlen fájl adatai (84. d. javasolt kiegészítése); a diák csak metaadat
KOZVETLEN_MEZOK = ("forras", "beagyazott", "minoseg", "nyelv", "felirat", "diak")


def bejaras(app, url) -> dict:
    """A `video_bejaras` feladat eredménye (84. döntés, javasolt): a kezdőoldal alatti videóoldalak listája (cím, oldal, videó-link,
    „már megvan” jel). Csak olvas; ha még nincs eredmény (a feladat fut vagy nem indult), `{kesz: false}`."""
    from .videolanc import bejaras_fajl
    if not isinstance(url, str) or not url.strip() or len(url) > 2000:
        raise HttpError(400, "add meg a bejárt oldal linkjét (`url`)")
    p = bejaras_fajl(app.cfg, url)
    try:
        adat = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"kesz": False}
    except (OSError, ValueError):
        raise HttpError(500, "a bejárás eredménye nem olvasható; indítsd újra a bejárást") from None
    tetelek = [{k: t.get(k) for k in ("oldal", "cim", "video", "megvan")} | {k: t[k] for k in KOZVETLEN_MEZOK if t.get(k) is not None}
               for t in (adat.get("tetelek") or []) if isinstance(t, dict)]
    return {"kesz": True, "start": adat.get("start"), "ido": adat.get("ido"), "oldalak": adat.get("oldalak", 0),
            "megszakitva": bool(adat.get("megszakitva")), "max_db": int(adat.get("max_db") or app.cfg.section("video").get("bejaras_max", 50)),
            "tetelek": tetelek}


def utvonalak(r) -> None:
    r.get("/api/video/allapot", lambda k: allapot(k.app))
    r.get("/api/video/bejaras", lambda k: bejaras(k.app, k.q.get("url")))
    r.post("/api/video/bejovo", lambda k: bejovo(k.app, k.torzs()))
